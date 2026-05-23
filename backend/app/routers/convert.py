"""POST /convert, POST /convert/batch, GET /download/{token}."""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..config import Settings, get_settings
from ..converter import ConversionError, convert_pdf_to_djvu, inspect_pdf
from ..schemas import (
    BatchItemResult,
    BatchResult,
    BornDigitalDetail,
    CompareResult,
    Preset,
    ProgressEvent,
)
from ..security import (
    assert_pdf_or_raise,
    assert_size_or_raise,
    limiter,
    safe_filename,
)
from ..storage import ShareStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/convert", tags=["convert"])


def _store(request: Request) -> ShareStore:
    return request.app.state.share_store


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    """Read at most max_upload_bytes from the upload, raising 413 if it exceeds the limit."""
    chunks: list[bytes] = []
    total = 0
    limit = settings.max_upload_bytes
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload exceeds the {settings.max_upload_mb} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _build_compare_result(
    *,
    pdf_bytes: int,
    djvu_bytes: int,
    pages: int,
    preset: Preset,
    ocr: bool,
    duration_ms: int,
    share_url: Optional[str] = None,
) -> CompareResult:
    ratio = (pdf_bytes / djvu_bytes) if djvu_bytes > 0 else 0.0
    reduction = (1 - (djvu_bytes / pdf_bytes)) * 100 if pdf_bytes > 0 else 0.0
    return CompareResult(
        pdf_bytes=pdf_bytes,
        djvu_bytes=djvu_bytes,
        compression_ratio=round(ratio, 2),
        size_reduction_pct=round(reduction, 2),
        pages=pages,
        preset=preset,
        ocr=ocr,
        duration_ms=duration_ms,
        share_url=share_url,
    )


# --------------------------------------------------------------------------- #
# Single-file conversion — streams ndjson progress events, with born-digital
# gatekeeping. The client follows up with GET /api/download/{token} to fetch
# the actual DjVu bytes.
# --------------------------------------------------------------------------- #
@router.post(
    "",
    summary="Convert a single PDF to DjVu (streams ndjson progress).",
    description=(
        "Accepts a PDF as multipart upload, runs the auto-selected DjVu "
        "conversion pipeline, and **streams newline-delimited JSON** progress "
        "events as it goes.\n\n"
        "Each line is one [`ProgressEvent`](#model/ProgressEvent). The terminal "
        "event has `stage=\"done\"` and includes a `share_token` — fetch the "
        "actual DjVu bytes with [`GET /api/download/{token}`]"
        "(#tag/share/operation/download_api_download__token__get) afterwards.\n\n"
        "Returns **409 Conflict** if the input looks born-digital "
        "(vector text, low bytes-per-page). Resubmit with "
        "`force_born_digital=true` to override the gate."
    ),
    responses={
        200: {
            "description": (
                "Newline-delimited JSON progress stream. Each line is a "
                "`ProgressEvent` object. The final event has `stage=\"done\"` "
                "with `share_token` + `result`."
            ),
            "content": {
                "application/x-ndjson": {
                    "schema": ProgressEvent.model_json_schema(),
                    "example": (
                        '{"stage":"preflight","message":"Using converter: pdftoppm+c44"}\n'
                        '{"stage":"ocr","engine":"easyocr","message":"Running OCR with easyocr…"}\n'
                        '{"stage":"ocr_done","engine":"easyocr","pages":166,"message":"OCR finished — 166 pages processed"}\n'
                        '{"stage":"render","message":"Rendering pages…"}\n'
                        '{"stage":"encode","current":1,"total":166,"codec":"cjb2","message":"Encoded page 1 of 166 (cjb2)"}\n'
                        '... 165 more encode events ...\n'
                        '{"stage":"assemble","message":"Assembling DjVu document…"}\n'
                        '{"stage":"textlayer","message":"Embedding OCR text layer…"}\n'
                        '{"stage":"done","share_token":"abc123","filename":"scan.djvu","result":{...}}\n'
                    ),
                }
            },
        },
        409: {
            "description": (
                "PDF appears born-digital. The response body's `detail` field "
                "is a `BornDigitalDetail`. Resubmit with "
                "`force_born_digital=true` to override."
            ),
            "model": BornDigitalDetail,
        },
        413: {"description": "Upload exceeds `MAX_UPLOAD_MB`."},
        415: {"description": "File is not a valid PDF (failed magic-byte / MIME check)."},
        429: {"description": "Rate limit exceeded; retry after `Retry-After` seconds."},
    },
)
@limiter.limit(lambda: get_settings().rate_limit_convert)
async def convert(
    request: Request,
    file: UploadFile = File(..., description="PDF file to convert."),
    preset: Preset = Form(Preset.balanced),
    ocr: bool = Form(False),
    force_born_digital: bool = Form(
        False,
        description="When false (default), reject born-digital PDFs with 409. "
                    "Set true to override the gate and convert anyway.",
    ),
    settings: Settings = Depends(get_settings),
):
    declared_name = safe_filename(file.filename or "document.pdf")
    data = await _read_upload(file, settings)
    assert_size_or_raise(len(data), settings.max_upload_bytes)
    assert_pdf_or_raise(data, declared_name)

    # We write the upload to disk now (small cost) so we can both inspect it
    # synchronously here and pass the path into the background streamer below.
    tmp_dir = tempfile.TemporaryDirectory(prefix="pdf2djvu-work-")
    tmp_path = Path(tmp_dir.name)
    pdf_in = tmp_path / "input.pdf"
    pdf_in.write_bytes(data)

    inspection = await inspect_pdf(pdf_in, timeout=min(settings.conversion_timeout, 60))
    if inspection.is_likely_born_digital and not force_born_digital:
        # Make sure to clean up before bailing — the streamer below would
        # otherwise be the only thing freeing tmp_dir.
        tmp_dir.cleanup()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "BORN_DIGITAL_PDF",
                "message": (
                    "This PDF appears to be born-digital (vector text, not a "
                    "scan). Converting to DjVu will almost certainly INCREASE "
                    "the file size and lose vector quality."
                ),
                "inspection": {
                    "pages": inspection.pages,
                    "bytes_per_page": round(inspection.bytes_per_page, 1),
                    "text_chars_per_page": round(inspection.text_chars_per_page, 1),
                    "reason": inspection.reason,
                },
                "hint": "Resubmit with force_born_digital=true to override.",
            },
        )

    # All clear — kick off the streaming conversion. The temp dir is cleaned
    # inside the generator's finally block.
    return StreamingResponse(
        _stream_convert(
            request=request,
            tmp_dir=tmp_dir,
            tmp_path=tmp_path,
            pdf_in=pdf_in,
            declared_name=declared_name,
            preset=preset,
            ocr=ocr,
            pdf_bytes_total=len(data),
            settings=settings,
        ),
        media_type="application/x-ndjson",
    )


async def _stream_convert(
    *,
    request: Request,
    tmp_dir: tempfile.TemporaryDirectory,
    tmp_path: Path,
    pdf_in: Path,
    declared_name: str,
    preset: Preset,
    ocr: bool,
    pdf_bytes_total: int,
    settings: Settings,
):
    """Async generator: runs the conversion, yields ndjson progress events,
    cleans up the working dir at the end.
    """
    progress: asyncio.Queue = asyncio.Queue()

    async def runner():
        try:
            outcome = await convert_pdf_to_djvu(
                pdf_path=pdf_in,
                work_dir=tmp_path,
                preset=preset,
                ocr=ocr,
                ocr_language=settings.ocr_language,
                ocr_engine_preference=settings.ocr_engine,
                timeout=settings.conversion_timeout,
                progress=progress,
            )
            stored = _store(request).put(
                outcome.djvu_path,
                _djvu_name(declared_name),
                ocr_text_pages=outcome.ocr_text,
            )
            djvu_bytes = outcome.djvu_path.stat().st_size
            base = str(request.base_url).rstrip("/")
            result = _build_compare_result(
                pdf_bytes=pdf_bytes_total,
                djvu_bytes=djvu_bytes,
                pages=outcome.pages,
                preset=preset,
                ocr=ocr,
                duration_ms=outcome.duration_ms,
                share_url=f"{base}/api/download/{stored.token}",
            )
            await progress.put({
                "stage": "done",
                "share_token": stored.token,
                "filename": stored.filename,
                "result": result.model_dump(),
                "ocr_engine": outcome.ocr_engine,
            })
        except ConversionError as e:
            logger.warning("conversion failed: %s", e)
            await progress.put({"stage": "error", "error": str(e)})
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("conversion crashed")
            await progress.put({"stage": "error", "error": str(e)})
        finally:
            await progress.put(None)  # sentinel

    task = asyncio.create_task(runner())
    try:
        while True:
            event = await progress.get()
            if event is None:
                break
            yield (json.dumps(event) + "\n").encode("utf-8")
    finally:
        # Make sure the worker is done before we delete its working files.
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        tmp_dir.cleanup()


# --------------------------------------------------------------------------- #
# Batch conversion
# --------------------------------------------------------------------------- #
@router.post(
    "/batch",
    response_model=BatchResult,
    summary="Convert multiple PDFs in one request.",
    description=(
        "Multipart upload with one or more `files` fields. Up to 20 PDFs are "
        "processed serially; each result is summarised in the `items` array "
        "with its own success flag, error message (if any), and "
        "`CompareResult` (on success).\n\n"
        "Every successful conversion is also stored under a share token "
        "and a `share_url` is included in each item — fetch with "
        "[`GET /api/download/{token}`]"
        "(#tag/share/operation/download_api_download__token__get).\n\n"
        "Born-digital gate is **not** applied to batch uploads — the "
        "assumption is you know what you're doing."
    ),
    responses={
        400: {"description": "No files, or more than 20 files."},
        413: {"description": "An individual file exceeds `MAX_UPLOAD_MB`."},
        415: {"description": "An individual file is not a valid PDF."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(lambda: get_settings().rate_limit_convert)
async def convert_batch(
    request: Request,
    files: list[UploadFile] = File(..., description="One or more PDF files."),
    preset: Preset = Form(Preset.balanced),
    ocr: bool = Form(False),
    settings: Settings = Depends(get_settings),
) -> BatchResult:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Batch is limited to 20 files.")

    items: list[BatchItemResult] = []
    base = str(request.base_url).rstrip("/")

    for upload in files:
        declared_name = safe_filename(upload.filename or "document.pdf")
        try:
            data = await _read_upload(upload, settings)
            assert_size_or_raise(len(data), settings.max_upload_bytes)
            assert_pdf_or_raise(data, declared_name)
        except HTTPException as e:
            items.append(BatchItemResult(filename=declared_name, success=False, error=e.detail))
            continue

        with tempfile.TemporaryDirectory(prefix="pdf2djvu-work-") as tmp:
            tmp_path = Path(tmp)
            pdf_in = tmp_path / "input.pdf"
            pdf_in.write_bytes(data)
            try:
                outcome = await convert_pdf_to_djvu(
                    pdf_path=pdf_in,
                    work_dir=tmp_path,
                    preset=preset,
                    ocr=ocr,
                    ocr_language=settings.ocr_language,
                    ocr_engine_preference=settings.ocr_engine,
                    timeout=settings.conversion_timeout,
                )
            except ConversionError as e:
                items.append(BatchItemResult(filename=declared_name, success=False, error=str(e)))
                continue

            djvu_bytes = outcome.djvu_path.stat().st_size
            stored = _store(request).put(
                outcome.djvu_path,
                _djvu_name(declared_name),
                ocr_text_pages=outcome.ocr_text,
            )
            result = _build_compare_result(
                pdf_bytes=len(data),
                djvu_bytes=djvu_bytes,
                pages=outcome.pages,
                preset=preset,
                ocr=ocr,
                duration_ms=outcome.duration_ms,
                share_url=f"{base}/api/download/{stored.token}",
            )
            items.append(BatchItemResult(filename=declared_name, success=True, result=result))

    return BatchResult(items=items)


# --------------------------------------------------------------------------- #
# Download a previously stored conversion
# --------------------------------------------------------------------------- #
download_router = APIRouter(tags=["share"])


@download_router.get(
    "/download/{token}",
    summary="Stream a previously stored DjVu by share token.",
    description=(
        "Tokens are issued by `POST /api/convert` (in the terminal `done` "
        "event) and `POST /api/compare` / `POST /api/convert/batch` (in the "
        "`share_url` field). Stored files live for `STORAGE_TTL_SECONDS` "
        "(default 1 hour) and are purged by a background sweeper.\n\n"
        "Returns the raw DjVu bytes with `Content-Type: image/vnd.djvu` "
        "and a `Content-Disposition: attachment; filename=...` header."
    ),
    responses={
        200: {"content": {"image/vnd.djvu": {}}},
        404: {"description": "Token is unknown or has expired."},
    },
)
async def download(token: str, request: Request) -> FileResponse:
    stored = _store(request).get(token)
    if stored is None:
        raise HTTPException(status_code=404, detail="Share link not found or expired.")
    return FileResponse(
        path=stored.djvu_path,
        media_type="image/vnd.djvu",
        filename=stored.filename,
    )


def _djvu_name(pdf_name: str) -> str:
    stem = pdf_name[:-4] if pdf_name.lower().endswith(".pdf") else pdf_name
    return f"{stem}.djvu"

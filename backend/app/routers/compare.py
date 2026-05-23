"""POST /compare — convert and return metadata only (no file body)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..config import Settings, get_settings
from ..converter import ConversionError, convert_pdf_to_djvu
from ..schemas import CompareResult, Preset
from ..security import assert_pdf_or_raise, assert_size_or_raise, limiter, safe_filename
from .convert import _build_compare_result, _djvu_name, _read_upload, _store

router = APIRouter(tags=["compare"])


@router.post(
    "/compare",
    response_model=CompareResult,
    summary="Convert a PDF to DjVu and return metadata only (no file body).",
    description=(
        "Runs the same pipeline as [`POST /api/convert`]"
        "(#tag/convert/operation/convert_api_convert_post) but returns JSON "
        "metadata instead of streaming a file — useful for headless tools that "
        "just want compression statistics, OCR engine info, or a share URL.\n\n"
        "When `share=true` (default), the converted DjVu is also stored under "
        "a token and the URL is returned in `share_url`; download with "
        "[`GET /api/download/{token}`]"
        "(#tag/share/operation/download_api_download__token__get).\n\n"
        "**No born-digital gate** — this endpoint always runs."
    ),
    responses={
        200: {"description": "Conversion metadata; `share_url` populated when `share=true`."},
        413: {"description": "Upload exceeds `MAX_UPLOAD_MB`."},
        415: {"description": "File is not a valid PDF."},
        429: {"description": "Rate limit exceeded."},
        500: {"description": "Conversion failed (see `detail`)."},
    },
)
@limiter.limit(lambda: get_settings().rate_limit_compare)
async def compare(
    request: Request,
    file: UploadFile = File(...),
    preset: Preset = Form(Preset.balanced),
    ocr: bool = Form(False),
    share: bool = Form(True),
    settings: Settings = Depends(get_settings),
) -> CompareResult:
    declared_name = safe_filename(file.filename or "document.pdf")
    data = await _read_upload(file, settings)
    assert_size_or_raise(len(data), settings.max_upload_bytes)
    assert_pdf_or_raise(data, declared_name)

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
            raise HTTPException(status_code=500, detail=str(e))

        djvu_bytes = outcome.djvu_path.stat().st_size
        share_url = None
        if share:
            stored = _store(request).put(
                outcome.djvu_path,
                _djvu_name(declared_name),
                ocr_text_pages=outcome.ocr_text,
            )
            base = str(request.base_url).rstrip("/")
            share_url = f"{base}/api/download/{stored.token}"

        return _build_compare_result(
            pdf_bytes=len(data),
            djvu_bytes=djvu_bytes,
            pages=outcome.pages,
            preset=preset,
            ocr=ocr,
            duration_ms=outcome.duration_ms,
            share_url=share_url,
        )

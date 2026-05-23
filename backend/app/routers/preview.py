"""GET /preview/{token}/page/{n}.png — server-side DjVu page rendering."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..converter import ConversionError, count_djvu_pages, render_djvu_page_png

router = APIRouter(tags=["preview"])


def _store(request: Request):
    return request.app.state.share_store


@router.get(
    "/preview/{token}/page-count",
    summary="Return the number of pages in a stored DjVu.",
    description="Counts pages via `djvused FILE -e n`. Cheap; no rasterisation.",
    responses={404: {"description": "Token unknown or expired."}},
)
async def page_count(token: str, request: Request) -> dict:
    stored = _store(request).get(token)
    if stored is None:
        raise HTTPException(status_code=404, detail="Share link not found or expired.")
    return {"pages": await count_djvu_pages(stored.djvu_path)}


@router.get(
    "/preview/{token}/has-text",
    summary="Whether the stored conversion has an OCR text layer available.",
    description=(
        "Returns `{\"has_text\": true}` only when the conversion ran with "
        "OCR enabled AND the engine produced extractable text. Frontends use "
        "this to gate the 'Image / OCR text' toggle."
    ),
    responses={404: {"description": "Token unknown or expired."}},
)
async def has_text(token: str, request: Request) -> dict:
    store = _store(request)
    if store.get(token) is None:
        raise HTTPException(status_code=404, detail="Share link not found or expired.")
    return {"has_text": store.has_ocr_text(token)}


@router.get(
    "/preview/{token}/page/{n}/text",
    summary="Extracted OCR text for a single page.",
    description=(
        "Returns the layout-preserved text the OCR engine produced for page "
        "`n`. Useful for spot-checking OCR quality. Note: this is independent "
        "of the DjVu's embedded text layer — the file itself is still "
        "searchable in desktop viewers via `djvused`-injected hidden text."
    ),
    responses={
        404: {"description": "No OCR text for this page (engine didn't run, page out of range, or token expired)."},
    },
)
async def page_text(token: str, n: int, request: Request) -> dict:
    store = _store(request)
    if store.get(token) is None:
        raise HTTPException(status_code=404, detail="Share link not found or expired.")
    text = store.get_ocr_text_page(token, n)
    if text is None:
        raise HTTPException(status_code=404, detail="No OCR text for this page.")
    return {"page": n, "text": text}


@router.get(
    "/preview/{token}/page/{n}.png",
    summary="Render a single DjVu page to PNG.",
    description=(
        "Renders page `n` of the stored DjVu to a PNG at most `width` pixels "
        "wide (aspect preserved). Uses `ddjvu -format=ppm` + Pillow for "
        "PPM→PNG. Browsers can cache the result for 5 minutes "
        "(`Cache-Control: private, max-age=300`)."
    ),
    responses={
        200: {"content": {"image/png": {}}},
        400: {"description": "Page number is < 1."},
        404: {"description": "Token unknown or expired."},
        500: {"description": "ddjvu / Pillow conversion failed."},
    },
)
async def page_png(
    token: str,
    n: int,
    request: Request,
    width: int = Query(900, ge=100, le=3000),
) -> Response:
    if n < 1:
        raise HTTPException(status_code=400, detail="Page number must be >= 1.")
    stored = _store(request).get(token)
    if stored is None:
        raise HTTPException(status_code=404, detail="Share link not found or expired.")
    try:
        png = await render_djvu_page_png(stored.djvu_path, page=n, width=width)
    except ConversionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )

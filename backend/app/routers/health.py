"""Liveness + tool-availability probe."""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import get_settings
from ..converter import active_converter, list_converters, tool_available
from ..ocr import easyocr_importable, gpu_available, gpu_info, select_engine
from ..schemas import HealthResult

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResult,
    tags=["meta"],
    summary="Liveness probe + runtime capability snapshot.",
    description=(
        "Returns:\n"
        "* **status** — always `ok` once the app has started.\n"
        "* **active_converter** — which of `pdf2djvu` / `djvudigital` / "
        "`pdftoppm+c44` will be used for the next conversion.\n"
        "* **available_converters** — full list of installed converters.\n"
        "* **ocr_engine_active** — `tesseract` or `easyocr`, resolved from "
        "the `OCR_ENGINE` env var.\n"
        "* **gpu_available** / **gpu_info** — CUDA detection from torch.\n\n"
        "Safe to poll at any frequency; the underlying checks are all cached "
        "with `lru_cache` after first invocation."
    ),
)
async def health() -> HealthResult:
    available = list_converters()
    settings = get_settings()
    return HealthResult(
        status="ok",
        version=__version__,
        pdf2djvu_available=tool_available("pdf2djvu"),
        djvudigital_available=tool_available("djvudigital"),
        img2djvu_available="pdftoppm+c44" in available,
        ocrmypdf_available=tool_available("ocrmypdf"),
        active_converter=active_converter(),
        available_converters=available,
        ocr_engine_preference=settings.ocr_engine,
        ocr_engine_active=select_engine(settings.ocr_engine),
        easyocr_available=easyocr_importable(),
        gpu_available=gpu_available(),
        gpu_info=gpu_info(),
    )

"""OCR engine abstraction.

Two engines:
  - tesseract: CPU-only via ocrmypdf. Always available.
  - easyocr:   GPU-accelerated via PyTorch+CUDA. Optional install.

`detect.select_engine()` resolves a preference into the engine that actually
runs, falling back to tesseract when easyocr / GPU isn't available.
"""

from .detect import (
    easyocr_importable,
    gpu_available,
    gpu_info,
    select_engine,
)
from .types import LineWords, OcrEngineResult, PageWords, WordBox

__all__ = [
    "LineWords",
    "OcrEngineResult",
    "PageWords",
    "WordBox",
    "easyocr_importable",
    "gpu_available",
    "gpu_info",
    "select_engine",
]

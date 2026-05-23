"""Detect available OCR engines and pick the active one.

All detection results are cached for the process lifetime — they don't change
without a restart, and import-checking torch is non-trivial.
"""
from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def easyocr_importable() -> bool:
    """True if `import easyocr` succeeds (and therefore torch is importable too)."""
    try:
        import easyocr  # noqa: F401
        return True
    except Exception as e:
        logger.debug("easyocr not importable: %s", e)
        return False


@lru_cache(maxsize=1)
def gpu_available() -> bool:
    """True if torch detects a CUDA-capable device."""
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception as e:
        logger.debug("torch not importable or no CUDA: %s", e)
        return False


@lru_cache(maxsize=1)
def gpu_info() -> str | None:
    """Human-readable description of the active CUDA device, e.g. 'NVIDIA RTX 3050 (6 GB)'."""
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            return None
        idx = torch.cuda.current_device()
        name = torch.cuda.get_device_name(idx)
        props = torch.cuda.get_device_properties(idx)
        gb = props.total_memory // (1024 ** 3)
        return f"{name} ({gb} GB)"
    except Exception:
        return None


def select_engine(preference: str = "auto") -> str:
    """Resolve a user preference into the engine that will actually run.

    Returns "tesseract" or "easyocr". The fallback is always tesseract.
    """
    pref = (preference or "auto").lower().strip()
    if pref == "tesseract":
        return "tesseract"
    if pref == "easyocr":
        # Force easyocr if requested, but only if it's actually installed.
        return "easyocr" if easyocr_importable() else "tesseract"
    # Auto: prefer easyocr only when GPU-capable.
    if easyocr_importable() and gpu_available():
        return "easyocr"
    return "tesseract"

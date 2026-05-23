"""Input validation, MIME sniffing and rate-limit setup."""
from __future__ import annotations

import re

from fastapi import HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

try:  # python-magic is optional at import time so tests can import without libmagic
    import magic  # type: ignore
    _MAGIC: "magic.Magic | None" = magic.Magic(mime=True)
except Exception:  # pragma: no cover - fallback
    _MAGIC = None


PDF_MAGIC_BYTES = b"%PDF-"
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

limiter = Limiter(key_func=get_remote_address)


def safe_filename(name: str, fallback: str = "document.pdf") -> str:
    """Return a filename safe for use on disk, stripped of any path elements."""
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    name = SAFE_NAME_RE.sub("_", name)
    if not name or name in {".", ".."}:
        return fallback
    # Cap length to avoid filesystem oddities.
    return name[:200]


def assert_pdf_or_raise(data: bytes, declared_name: str = "") -> None:
    """Reject anything that doesn't look like a real PDF."""
    if len(data) < 5 or not data.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File '{declared_name or 'upload'}' is not a valid PDF (missing %PDF- header).",
        )
    if _MAGIC is not None:
        sniffed = _MAGIC.from_buffer(data[:8192])
        if sniffed != "application/pdf":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File '{declared_name or 'upload'}' detected as {sniffed!r}, not PDF.",
            )


def assert_size_or_raise(size: int, limit: int) -> None:
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if size > limit:
        mb = limit / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds the {mb:.0f} MB limit.",
        )

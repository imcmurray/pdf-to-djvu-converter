"""Shared OCR data structures.

Both Tesseract and EasyOCR engines normalise their output into these structures
so the rest of the conversion pipeline (text-panel display, DjVu text-layer
injection) is engine-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WordBox:
    """A single OCR'd word with its bounding box in PDF user-space points
    (1/72 inch), origin top-left.
    """
    text: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class LineWords:
    """Words grouped into a visual line."""
    words: list[WordBox]


@dataclass
class PageWords:
    """All OCR output for a single page."""
    width_pts: float
    height_pts: float
    lines: list[LineWords] = field(default_factory=list)


@dataclass
class OcrEngineResult:
    """Output of running an OCR engine over a PDF."""

    # PDF that should be fed into the visual conversion pipeline. For Tesseract
    # this is ocrmypdf's output (deskewed/rotated, text-layer added). For
    # EasyOCR this is the original PDF (engine doesn't modify the source).
    pdf_for_conversion: Path

    # Per-page structured OCR output, used for the in-UI text panel and for
    # DjVu text-layer injection.
    pages: list[PageWords]

    # Engine actually used: "tesseract" or "easyocr".
    engine: str

    @property
    def plain_text_per_page(self) -> list[str]:
        """One plain-text string per page (words joined by spaces, lines by newlines)."""
        out: list[str] = []
        for page in self.pages:
            page_lines: list[str] = []
            for line in page.lines:
                page_lines.append(" ".join(w.text for w in line.words))
            out.append("\n".join(page_lines))
        return out

"""Tesseract OCR engine, wrapped via ocrmypdf + pdftotext.

Flow:
  1. ocrmypdf rewrites the input PDF, deskewing/rotating each page and adding
     a Tesseract-generated invisible text layer.
  2. pdftotext -bbox-layout extracts the word-level positions from that text
     layer into structured XHTML.
  3. We parse the XHTML into PageWords for the rest of the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from .types import LineWords, OcrEngineResult, PageWords, WordBox

logger = logging.getLogger(__name__)


class OcrError(RuntimeError):
    pass


async def run(
    *,
    pdf_path: Path,
    work_dir: Path,
    language: str,
    timeout: int,
    run_subprocess,
    tool_available,
    progress=None,
) -> OcrEngineResult:
    """Run the Tesseract pipeline. `run_subprocess` and `tool_available` are passed
    in from converter.py so we don't form an import cycle.

    ocrmypdf is a single subprocess that owns the whole multi-page run; we
    can't peek at its per-page progress. Instead, while it's running, a
    heartbeat task emits "still working" events every few seconds so the UI
    isn't silent.
    """
    if not tool_available("ocrmypdf"):
        raise OcrError("ocrmypdf is not installed.")

    async def emit(event: dict) -> None:
        if progress is not None:
            await progress.put(event)

    ocr_pdf = work_dir / "ocr.pdf"
    cmd = [
        "ocrmypdf",
        "--force-ocr",
        "--deskew",
        "--rotate-pages",
        "--jobs", str(max(1, (os.cpu_count() or 2) - 1)),
        "--optimize", "1",
        "--language", language,
        "--invalidate-digital-signatures",
        "--quiet",
        str(pdf_path),
        str(ocr_pdf),
    ]

    started = asyncio.get_event_loop().time()
    heartbeat_task: asyncio.Task | None = None

    async def heartbeat():
        # First message at t=0 so the UI shows we're alive.
        n = 0
        while True:
            n += 1
            await emit({
                "stage": "ocr",
                "engine": "tesseract",
                "message": (
                    f"Running ocrmypdf (Tesseract) — "
                    f"{int(asyncio.get_event_loop().time() - started)}s elapsed"
                ),
            })
            await asyncio.sleep(5 if n < 6 else 10)

    if progress is not None:
        heartbeat_task = asyncio.create_task(heartbeat())

    try:
        rc, _o, err = await run_subprocess(cmd, timeout=timeout)
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass

    if rc != 0 or not ocr_pdf.exists():
        raise OcrError(f"ocrmypdf failed: {err.strip()[:500]}")

    await emit({"stage": "ocr", "engine": "tesseract",
                "message": "Extracting word boxes from OCR'd PDF…"})
    pages = await _extract_word_boxes(ocr_pdf, work_dir, timeout, run_subprocess, tool_available)
    return OcrEngineResult(pdf_for_conversion=ocr_pdf, pages=pages, engine="tesseract")


# --------------------------------------------------------------------------- #
# pdftotext -bbox-layout parsing
# --------------------------------------------------------------------------- #
async def _extract_word_boxes(
    pdf: Path, work_dir: Path, timeout: int, run_subprocess, tool_available,
) -> list[PageWords]:
    if not tool_available("pdftotext"):
        return []
    html_path = work_dir / "words.html"
    rc, _o, err = await run_subprocess(
        ["pdftotext", "-bbox-layout", str(pdf), str(html_path)],
        timeout=timeout,
    )
    if rc != 0 or not html_path.exists():
        logger.warning("pdftotext -bbox-layout failed: %s", err.strip()[:200])
        return []
    return await asyncio.to_thread(_parse_bbox_html, html_path)


def _parse_bbox_html(path: Path) -> list[PageWords]:
    from xml.etree import ElementTree as ET

    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r' xmlns="[^"]+"', "", raw, count=1)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logger.warning("Failed to parse pdftotext bbox HTML: %s", e)
        return []

    pages: list[PageWords] = []
    for page_el in root.iter("page"):
        try:
            w = float(page_el.get("width", "0"))
            h = float(page_el.get("height", "0"))
        except ValueError:
            continue
        page_lines: list[LineWords] = []
        for line_el in page_el.iter("line"):
            words: list[WordBox] = []
            for w_el in line_el.iter("word"):
                try:
                    x_min = float(w_el.get("xMin", ""))
                    y_min = float(w_el.get("yMin", ""))
                    x_max = float(w_el.get("xMax", ""))
                    y_max = float(w_el.get("yMax", ""))
                except ValueError:
                    continue
                txt = (w_el.text or "").strip()
                if not txt:
                    continue
                words.append(WordBox(text=txt, x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max))
            if words:
                page_lines.append(LineWords(words=words))
        pages.append(PageWords(width_pts=w, height_pts=h, lines=page_lines))
    return pages

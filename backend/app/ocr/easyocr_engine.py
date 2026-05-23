"""EasyOCR engine — GPU-accelerated via PyTorch + CUDA.

Flow:
  1. Render each page of the input PDF to a PNG at known DPI (pdftoppm).
  2. Run easyocr.Reader.readtext() on each PNG. Each result is a
     (bbox, text, confidence) triple where bbox is a 4-point quad.
  3. Convert pixel-space bboxes back to PDF user-space points so they
     interop with the rest of the pipeline (text-layer injection, etc.).
  4. Group words into visual lines via Y-overlap.

The Reader is constructed lazily on first use and cached for the process —
the model weights live in GPU memory and re-instantiating per request would
add ~3 s/conversion.

The original PDF is returned as `pdf_for_conversion`; EasyOCR doesn't rewrite
the source. This means the img2djvu visual conversion uses the input as-is
(no upstream deskew). The DjVu text layer is still positionally correct
because we inject word boxes derived from the OCR pass.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .types import LineWords, OcrEngineResult, PageWords, WordBox

logger = logging.getLogger(__name__)

# OCR is done at this DPI. Higher → better accuracy on small text but slower.
_OCR_RENDER_DPI = 300

# Lazy singleton Reader to avoid re-loading model weights per conversion.
_reader_cache: dict[tuple, object] = {}


def _get_reader(language: str, use_gpu: bool):
    """Return a cached easyocr.Reader for the given language(s) and device."""
    import easyocr  # type: ignore

    # Map a tesseract-style language code ("eng", "eng+fra") to easyocr codes
    # (["en"], ["en", "fr"]). EasyOCR uses 2-letter ISO codes.
    langs = _normalize_languages(language)
    key = (tuple(langs), use_gpu)
    reader = _reader_cache.get(key)
    if reader is None:
        logger.info("Loading EasyOCR reader (langs=%s, gpu=%s)…", langs, use_gpu)
        reader = easyocr.Reader(langs, gpu=use_gpu, verbose=False)
        _reader_cache[key] = reader
    return reader


# Tesseract-language → EasyOCR-language code mapping for the common cases.
_LANG_MAP = {
    "eng": "en", "fra": "fr", "deu": "de", "spa": "es", "ita": "it",
    "por": "pt", "rus": "ru", "ukr": "uk", "pol": "pl", "ces": "cs",
    "tur": "tr", "ara": "ar", "jpn": "ja", "chi_sim": "ch_sim",
    "chi_tra": "ch_tra", "kor": "ko", "nld": "nl", "swe": "sv",
    "dan": "da", "fin": "fi", "nor": "no", "ron": "ro", "hun": "hu",
    "ell": "el", "heb": "he", "tha": "th", "vie": "vi", "ind": "id",
}


def _normalize_languages(lang: str) -> list[str]:
    """Convert "eng+fra" → ["en", "fr"]. Unknown codes default to "en"."""
    parts = [p.strip() for p in lang.replace(",", "+").split("+") if p.strip()]
    out = []
    for p in parts:
        out.append(_LANG_MAP.get(p, p[:2].lower()))
    return out or ["en"]


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
    from .detect import gpu_available

    if not tool_available("pdftoppm"):
        raise RuntimeError("pdftoppm is not installed (need poppler).")

    use_gpu = gpu_available()

    async def emit(event: dict) -> None:
        if progress is not None:
            await progress.put(event)

    # 1. PDF → page PNGs at _OCR_RENDER_DPI.
    await emit({"stage": "ocr", "engine": "easyocr",
                "message": "Rendering pages for OCR…"})
    page_prefix = work_dir / "ocrpage"
    rc, _o, err = await run_subprocess(
        ["pdftoppm", "-r", str(_OCR_RENDER_DPI), "-png", str(pdf_path), str(page_prefix)],
        timeout=timeout,
    )
    if rc != 0:
        raise RuntimeError(f"pdftoppm failed: {err.strip()[:300]}")

    images = sorted(work_dir.glob("ocrpage-*.png"))
    if not images:
        return OcrEngineResult(pdf_for_conversion=pdf_path, pages=[], engine="easyocr")

    # 2. Load reader once. The first call downloads model weights, so surface
    # that explicitly — it can take ~3 s and would otherwise look like a stall.
    await emit({"stage": "ocr", "engine": "easyocr",
                "message": "Loading EasyOCR model into GPU…"})
    reader = await asyncio.to_thread(_get_reader, language, use_gpu)

    # 3. OCR each page. Run in a thread executor since easyocr is sync.
    pages: list[PageWords] = []
    total = len(images)
    for idx, img_path in enumerate(images, start=1):
        page = await asyncio.to_thread(_ocr_one_page, reader, img_path)
        pages.append(page)
        await emit({
            "stage": "ocr",
            "engine": "easyocr",
            "current": idx,
            "total": total,
            "message": f"OCR'd page {idx} of {total}",
        })

    return OcrEngineResult(pdf_for_conversion=pdf_path, pages=pages, engine="easyocr")


def _ocr_one_page(reader, image_path: Path) -> PageWords:
    """Run EasyOCR on one page image and produce a PageWords in PDF-points."""
    from PIL import Image

    # Image dimensions in pixels (at _OCR_RENDER_DPI).
    with Image.open(image_path) as im:
        width_px, height_px = im.size

    # Convert pixel-space → PDF points (1/72 inch).
    px_to_pt = 72.0 / _OCR_RENDER_DPI
    width_pts = width_px * px_to_pt
    height_pts = height_px * px_to_pt

    # readtext returns [(bbox, text, conf), ...]
    raw = reader.readtext(str(image_path))
    words: list[WordBox] = []
    for bbox, text, conf in raw:
        if conf < 0.2 or not text.strip():
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x_min = min(xs) * px_to_pt
        x_max = max(xs) * px_to_pt
        y_min = min(ys) * px_to_pt
        y_max = max(ys) * px_to_pt
        words.append(WordBox(text=str(text).strip(), x_min=x_min, y_min=y_min,
                             x_max=x_max, y_max=y_max))

    # Group into visual lines via Y proximity.
    lines = _group_into_lines(words)
    return PageWords(width_pts=width_pts, height_pts=height_pts, lines=lines)


def _group_into_lines(words: list[WordBox], y_tolerance: float = 0.5) -> list[LineWords]:
    """Cluster words into visual lines by Y-centre distance.

    Words whose vertical centre is within `y_tolerance * line_height` of the
    current line's centre are joined to it; otherwise a new line starts.
    """
    if not words:
        return []
    # Sort by Y-centre then X.
    by_y = sorted(words, key=lambda w: ((w.y_min + w.y_max) / 2, w.x_min))
    lines: list[list[WordBox]] = []
    current = [by_y[0]]
    cur_centre = (by_y[0].y_min + by_y[0].y_max) / 2
    cur_height = max(1.0, by_y[0].y_max - by_y[0].y_min)
    for w in by_y[1:]:
        centre = (w.y_min + w.y_max) / 2
        if abs(centre - cur_centre) <= cur_height * y_tolerance:
            current.append(w)
        else:
            current.sort(key=lambda x: x.x_min)
            lines.append(current)
            current = [w]
            cur_centre = centre
            cur_height = max(1.0, w.y_max - w.y_min)
    current.sort(key=lambda x: x.x_min)
    lines.append(current)
    return [LineWords(words=line) for line in lines]

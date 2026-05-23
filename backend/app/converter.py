"""PDF → DjVu conversion pipeline.

Supports three backend converters, picked automatically based on what's installed:

  1. `pdf2djvu`   — preferred. Uses Poppler under the hood, preserves text layer,
                    metadata, outlines and hyperlinks faithfully.
  2. `djvudigital` — secondary. Uses Ghostscript + a custom djvu device
                    (gsdjvu). Requires AUR packages on Arch.
  3. `pdftoppm+c44` — universal fallback. Rasterises each PDF page with
                    pdftoppm (poppler) and encodes it with c44 (djvulibre),
                    then concatenates with djvm. Always works when poppler +
                    djvulibre are installed; drops the original text layer.

Each step writes into a caller-provided temp directory and never uses a shell —
arguments are always passed as a list.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import ocr as ocr_module
from .ocr.types import PageWords
from .schemas import Preset

logger = logging.getLogger(__name__)


# Per-converter, per-preset CLI flags. pdf2djvu and djvudigital share several
# flag names but have different defaults, so we keep them separate.
_PRESETS_PDF2DJVU: dict[Preset, list[str]] = {
    Preset.fast: ["--dpi=200", "--jobs=2"],
    Preset.balanced: ["--dpi=300", "--jobs=2"],
    Preset.high_quality: ["--dpi=600", "--losslessjbig2", "--jobs=2"],
    Preset.max_compression: [
        "--dpi=300",
        "--bg-subsample=6",
        "--fg-colors=web",
        "--jobs=2",
    ],
}

_PRESETS_DJVUDIGITAL: dict[Preset, list[str]] = {
    Preset.fast: ["--dpi=200"],
    Preset.balanced: ["--dpi=300"],
    Preset.high_quality: ["--dpi=600"],
    Preset.max_compression: ["--dpi=300", "--bg-subsample=6"],
}

# (dpi, c44 slice spec) per preset for the pdftoppm+c44 fallback.
# c44's "slice" controls progressive wavelet compression; more slices = higher quality.
_PRESETS_C44: dict[Preset, tuple[int, list[str]]] = {
    Preset.fast: (200, ["-slice", "72+11+10+10"]),
    Preset.balanced: (300, ["-slice", "72+11+10+10+6+4"]),
    Preset.high_quality: (600, ["-slice", "74+10+9+10+7+3+2+1"]),
    Preset.max_compression: (300, ["-slice", "72+11"]),
}


def _have(*tools: str) -> bool:
    return all(tool_available(t) for t in tools)


@lru_cache(maxsize=1)
def _djvudigital_usable() -> bool:
    """djvudigital is only useful if a djvu-capable Ghostscript (gsdjvu) is present.

    On Arch, the stock djvulibre ships djvudigital but no gsdjvu, so it always
    fails with "cannot locate suitable ghostscript executable". We probe once at
    startup and cache the result.
    """
    if not tool_available("djvudigital"):
        return False
    try:
        proc = subprocess.run(
            ["djvudigital", "--help"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    blob = (proc.stdout or "") + (proc.stderr or "")
    if "cannot locate suitable ghostscript" in blob.lower():
        return False
    return proc.returncode == 0


def active_converter() -> str | None:
    """Pick the best converter that's actually installed AND functional.

    Returns one of "pdf2djvu", "djvudigital", "pdftoppm+c44", or None.
    """
    if tool_available("pdf2djvu"):
        return "pdf2djvu"
    if _djvudigital_usable():
        return "djvudigital"
    if _have("pdftoppm", "c44", "djvm"):
        return "pdftoppm+c44"
    return None


def list_converters() -> list[str]:
    out = []
    if tool_available("pdf2djvu"): out.append("pdf2djvu")
    if _djvudigital_usable(): out.append("djvudigital")
    if _have("pdftoppm", "c44", "djvm"): out.append("pdftoppm+c44")
    return out


async def render_djvu_page_png(
    djvu_path: Path, *, page: int, width: int | None = None, timeout: int = 30,
) -> bytes:
    """Render a single DjVu page to PNG.

    ddjvu (djvulibre) only outputs PPM/PGM/PNM/TIFF/PDF — not PNG directly — so
    we render to PPM and convert with Pillow.
    """
    if not tool_available("ddjvu"):
        raise ConversionError("ddjvu is not installed (need djvulibre).")

    ppm_path = djvu_path.parent / f"preview-{page}.ppm"
    cmd = ["ddjvu", "-format=ppm", f"-page={page}"]
    if width and width > 0:
        # ddjvu's -size= takes WxH bounding box; pass a tall H so aspect is preserved by width.
        cmd.append(f"-size={width}x{width * 10}")
    cmd += [str(djvu_path), str(ppm_path)]
    rc, _o, err = await _run(cmd, timeout=timeout)
    if rc != 0 or not ppm_path.exists():
        raise ConversionError(f"ddjvu failed: {err.strip()[:300]}")

    # PPM → PNG via Pillow. Done off the event loop because Pillow is sync.
    from PIL import Image  # local import keeps the module load light
    import io
    def _encode() -> bytes:
        with Image.open(ppm_path) as im:
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=False)
            return buf.getvalue()
    try:
        return await asyncio.to_thread(_encode)
    except Exception as e:
        raise ConversionError(f"PPM→PNG conversion failed: {e!s}")
    finally:
        try:
            ppm_path.unlink()
        except OSError:
            pass


async def count_djvu_pages(djvu_path: Path, *, timeout: int = 15) -> int:
    """Count pages in a DjVu file using djvused."""
    if not tool_available("djvused"):
        return 1
    rc, out, _err = await _run(["djvused", str(djvu_path), "-e", "n"], timeout=timeout)
    if rc != 0:
        return 1
    try:
        return int(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 1


def _maybe_make_bilevel(
    ppm_path: Path,
    *,
    max_midtone_frac: float = 0.05,
    min_dark_frac: float = 0.001,
) -> Path | None:
    """Detect whether a rendered page is effectively bilevel (scanned B&W text).

    Strategy: convert to grayscale and look at the histogram. A bilevel-friendly
    page is bimodal — most pixels cluster in "dark" (text) or "light" (paper)
    buckets, with very little in the mid-tone region. Real scans have anti-
    aliased edges and off-white paper, so a naive "must be 0 or 255" test is
    far too strict. Allow the dark/light tails to be wide and instead require
    that the mid-tone region (97..159) is a tiny fraction of the total.

    A page passes when:
      - mid-tone fraction (gray 97..159) ≤ `max_midtone_frac` (default 5%)
      - dark fraction (gray < 97) ≥ `min_dark_frac` (so blank pages don't qualify
        as bilevel — they'd encode trivially small either way, but cjb2 needs ink)

    Returns the PBM path on success (caller encodes with cjb2), else None
    (caller encodes with c44).
    """
    from PIL import Image

    with Image.open(ppm_path) as im:
        gray = im.convert("L")
        hist = gray.histogram()
        total = sum(hist) or 1
        dark = sum(hist[:97])
        midtone = sum(hist[97:160])
        if midtone / total > max_midtone_frac:
            return None
        if dark / total < min_dark_frac:
            return None
        # Threshold at 128. cjb2 -lossy will clean up the small amount of
        # speckling introduced by hard-thresholding anti-aliased edges.
        bw = gray.point(lambda v: 0 if v < 128 else 255, mode="L").convert("1")
        pbm_path = ppm_path.with_suffix(".pbm")
        bw.save(pbm_path, "PPM")  # Pillow writes P4 (binary PBM) for mode "1"
        return pbm_path


async def _emit(progress, event: dict) -> None:
    """Push a progress event onto the queue, if a queue was given."""
    if progress is not None:
        await progress.put(event)


async def _convert_via_img2djvu(
    *, source_pdf: Path, djvu_out: Path, work_dir: Path, preset: Preset, timeout: int,
    progress=None,
) -> None:
    """Rasterise the PDF, encode each page with cjb2 or c44, then merge with djvm.

    Per-page codec selection:
      - cjb2 (bilevel JBIG2-equivalent) — when the page is effectively B&W text/scan.
        Typical scanned-book pages drop from ~800 KB → ~30 KB this way.
      - c44 (continuous-tone IW44 wavelet) — for colour/grayscale pages.
    """
    dpi, c44_extra = _PRESETS_C44[preset]
    ppm_prefix = work_dir / "page"

    # 1. PDF → PPM (or PGM) per page.
    await _emit(progress, {"stage": "render", "message": "Rendering pages…"})
    rc, _o, err = await _run(
        ["pdftoppm", "-r", str(dpi), str(source_pdf), str(ppm_prefix)],
        timeout=timeout,
    )
    if rc != 0:
        raise ConversionError(f"pdftoppm failed: {err.strip()[:500]}")

    pages = sorted(work_dir.glob("page-*.ppm")) or sorted(work_dir.glob("page-*.pgm"))
    if not pages:
        raise ConversionError("pdftoppm produced no pages.")
    total = len(pages)

    # 2. Encode each page — bilevel via cjb2, otherwise via c44.
    page_djvus: list[Path] = []
    bilevel_count = 0
    for i, ppm in enumerate(pages, start=1):
        page_djvu = ppm.with_suffix(".djvu")
        pbm = await asyncio.to_thread(_maybe_make_bilevel, ppm)
        if pbm is not None:
            args = ["cjb2", "-dpi", str(dpi), "-lossy", str(pbm), str(page_djvu)]
            bilevel_count += 1
            codec = "cjb2"
        else:
            args = ["c44", "-dpi", str(dpi), *c44_extra, str(ppm), str(page_djvu)]
            codec = "c44"
        rc, _o, err = await _run(args, timeout=timeout)
        if rc != 0:
            raise ConversionError(
                f"{args[0]} failed on {ppm.name}: {err.strip()[:500]}"
            )
        page_djvus.append(page_djvu)
        await _emit(progress, {
            "stage": "encode", "current": i, "total": total, "codec": codec,
            "message": f"Encoded page {i} of {total} ({codec})",
        })

    logger.info(
        "img2djvu: %d/%d pages encoded as bilevel (cjb2), rest as c44",
        bilevel_count, total,
    )

    # 3. Concatenate into a multi-page DjVu document.
    await _emit(progress, {"stage": "assemble", "message": "Assembling DjVu document…"})
    rc, _o, err = await _run(
        ["djvm", "-c", str(djvu_out), *[str(p) for p in page_djvus]],
        timeout=timeout,
    )
    if rc != 0 or not djvu_out.exists():
        raise ConversionError(f"djvm failed: {err.strip()[:500]}")


class ConversionError(RuntimeError):
    """Raised when an external conversion tool fails."""


@dataclass
class ConversionOutcome:
    djvu_path: Path
    pages: int
    duration_ms: int
    # When OCR ran, one string per page of plain text extracted from the OCR'd PDF.
    # None when OCR was skipped.
    ocr_text: list[str] | None = None
    # Engine used: "tesseract" | "easyocr" | None.
    ocr_engine: str | None = None


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


async def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    """Run a subprocess with arg-list (no shell). Return (rc, stdout, stderr)."""
    logger.info("running: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise ConversionError(f"{cmd[0]} timed out after {timeout}s") from e
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


_PAGES_RE = re.compile(r"(?i)\bpages?\s*[:=]\s*(\d+)\b")


def _escape_djvu_string(s: str) -> str:
    """Escape a string for inclusion in a DjVu text S-expression literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_djvused_text_script(pages: list[PageWords], dpi: int) -> str:
    """Build a djvused script that calls set-txt with word-level S-expressions.

    DjVu text-layer coordinates are pixel offsets from the **bottom-left** of the
    page. pdftotext emits points (1/72 inch) with origin at **top-left**, so we
    scale by (dpi / 72) and flip Y per page.
    """
    scale = dpi / 72.0
    out: list[str] = []
    for page_num, page in enumerate(pages, start=1):
        width_px = max(1, int(round(page.width_pts * scale)))
        height_px = max(1, int(round(page.height_pts * scale)))
        out.append(f"select {page_num}")
        out.append("set-txt")
        out.append(f"(page 0 0 {width_px} {height_px}")
        for line in page.lines:
            if not line.words:
                continue
            lx1 = int(round(min(w.x_min for w in line.words) * scale))
            lx2 = int(round(max(w.x_max for w in line.words) * scale))
            ly1 = height_px - int(round(max(w.y_max for w in line.words) * scale))
            ly2 = height_px - int(round(min(w.y_min for w in line.words) * scale))
            out.append(f"  (line {lx1} {ly1} {lx2} {ly2}")
            for word in line.words:
                wx1 = int(round(word.x_min * scale))
                wx2 = int(round(word.x_max * scale))
                wy1 = height_px - int(round(word.y_max * scale))
                wy2 = height_px - int(round(word.y_min * scale))
                out.append(
                    f'    (word {wx1} {wy1} {wx2} {wy2} "{_escape_djvu_string(word.text)}")'
                )
            out.append("  )")
        out.append(")")
        out.append(".")
    return "\n".join(out) + "\n"


async def inject_text_layer(
    *,
    djvu_path: Path,
    pages: list[PageWords],
    work_dir: Path,
    dpi: int,
    timeout: int = 300,
) -> int:
    """Inject pre-computed word-level OCR boxes into a DjVu via djvused set-txt.

    Returns the number of annotated pages, or 0 if djvused is unavailable or
    `pages` is empty. Non-fatal — callers should treat failure here as a
    missing-feature, not a conversion error.
    """
    if not tool_available("djvused"):
        logger.info("djvused unavailable; skipping text-layer injection.")
        return 0
    if not pages or not any(p.lines for p in pages):
        return 0

    script = _build_djvused_text_script(pages, dpi)
    script_path = work_dir / "text-layer.dsed"
    script_path.write_text(script, encoding="utf-8")

    rc, _o, err = await _run(
        ["djvused", "-s", "-f", str(script_path), str(djvu_path)],
        timeout=timeout,
    )
    if rc != 0:
        logger.warning("djvused failed during text-layer injection: %s", err.strip()[:300])
        return 0
    return sum(1 for p in pages if p.lines)


@dataclass
class PdfInspection:
    """Lightweight pre-conversion analysis used to gate-keep born-digital PDFs."""
    pages: int
    bytes_per_page: float
    text_chars_per_page: float
    is_likely_born_digital: bool
    reason: str


async def inspect_pdf(pdf_path: Path, timeout: int = 30) -> PdfInspection:
    """Quick heuristic check: is this PDF born-digital (waste of time to convert)?

    Heuristic: born-digital PDFs are typically small (vector instructions are
    cheap) AND text-heavy (the text is real glyphs, not OCR over an image).
    A scanned PDF that's been OCR'd has lots of text too but is much bigger
    per page because each page carries a raster image.

      bytes/page < ~70 KB AND chars/page > 200  → very likely born-digital
      bytes/page > 150 KB                       → very likely scan
      everything else                           → ambiguous, proceed normally
    """
    pages = max(1, await _count_pdf_pages(pdf_path, timeout))
    try:
        pdf_size = pdf_path.stat().st_size
    except OSError:
        pdf_size = 0
    bytes_per_page = pdf_size / pages

    text_chars = 0
    if tool_available("pdftotext"):
        rc, out, _err = await _run(
            ["pdftotext", "-q", str(pdf_path), "-"], timeout=min(timeout, 30),
        )
        if rc == 0:
            text_chars = len(out.replace("\x0c", "").strip())
    chars_per_page = text_chars / pages

    born_digital = bytes_per_page < 70_000 and chars_per_page > 200
    if born_digital:
        reason = (
            f"avg {bytes_per_page/1024:.0f} KB/page and ~{chars_per_page:.0f} "
            f"text chars/page — looks like vector text, not a scan"
        )
    else:
        reason = ""
    return PdfInspection(
        pages=pages,
        bytes_per_page=bytes_per_page,
        text_chars_per_page=chars_per_page,
        is_likely_born_digital=born_digital,
        reason=reason,
    )


async def _count_pdf_pages(pdf: Path, timeout: int) -> int:
    """Use pdfinfo (from poppler-utils) if available; fall back to a regex over the PDF."""
    if tool_available("pdfinfo"):
        rc, out, err = await _run(["pdfinfo", str(pdf)], timeout=min(timeout, 30))
        if rc == 0:
            m = _PAGES_RE.search(out)
            if m:
                return int(m.group(1))
    # Fallback: count "/Type /Page" occurrences. Not perfect but robust enough.
    try:
        data = pdf.read_bytes()
        return max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))
    except OSError:
        return 0


async def convert_pdf_to_djvu(
    *,
    pdf_path: Path,
    work_dir: Path,
    preset: Preset = Preset.balanced,
    ocr: bool = False,
    ocr_language: str = "eng",
    ocr_engine_preference: str = "auto",
    timeout: int = 600,
    progress=None,
) -> ConversionOutcome:
    """Convert a PDF on disk into a DjVu file inside `work_dir`.

    The returned `djvu_path` is guaranteed to be in `work_dir`. If `progress`
    is given (an asyncio.Queue), events are pushed onto it as the pipeline
    advances — useful for streaming step-by-step status to a client.
    """
    converter = active_converter()
    if converter is None:
        raise ConversionError(
            "No PDF→DjVu converter is installed. Install either 'pdf2djvu' or "
            "'djvulibre' (which provides 'djvudigital')."
        )
    await _emit(progress, {"stage": "preflight", "message": f"Using converter: {converter}"})

    work_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    # Run OCR through the selected engine. The engine returns:
    #   - the PDF that should feed the visual conversion (deskewed, etc.)
    #   - structured word boxes for the text panel + DjVu injection
    source_pdf = pdf_path
    ocr_text_pages: list[str] | None = None
    ocr_pages: list[PageWords] = []
    ocr_engine_used: str | None = None
    if ocr:
        engine_name = ocr_module.select_engine(ocr_engine_preference)
        logger.info("OCR engine: requested=%s resolved=%s", ocr_engine_preference, engine_name)
        await _emit(progress, {
            "stage": "ocr", "engine": engine_name,
            "message": f"Running OCR with {engine_name}…",
        })
        try:
            if engine_name == "easyocr":
                from .ocr import easyocr_engine
                result = await easyocr_engine.run(
                    pdf_path=pdf_path, work_dir=work_dir, language=ocr_language,
                    timeout=timeout, run_subprocess=_run, tool_available=tool_available,
                    progress=progress,
                )
            else:
                from .ocr import tesseract as tesseract_engine
                result = await tesseract_engine.run(
                    pdf_path=pdf_path, work_dir=work_dir, language=ocr_language,
                    timeout=timeout, run_subprocess=_run, tool_available=tool_available,
                    progress=progress,
                )
        except Exception as e:
            raise ConversionError(f"OCR failed ({engine_name}): {e}") from e
        source_pdf = result.pdf_for_conversion
        ocr_pages = result.pages
        ocr_text_pages = result.plain_text_per_page
        ocr_engine_used = result.engine
        await _emit(progress, {
            "stage": "ocr_done", "engine": engine_name, "pages": len(ocr_pages),
            "message": f"OCR finished — {len(ocr_pages)} pages processed",
        })

    djvu_out = work_dir / "output.djvu"

    if converter == "pdf2djvu":
        await _emit(progress, {"stage": "convert", "message": "Converting with pdf2djvu…"})
        args = ["pdf2djvu", "--output", str(djvu_out), *_PRESETS_PDF2DJVU[preset], str(source_pdf)]
        rc, _o, err = await _run(args, timeout=timeout)
        if rc != 0 or not djvu_out.exists():
            raise ConversionError(f"pdf2djvu failed: {err.strip()[:500]}")
    elif converter == "djvudigital":
        await _emit(progress, {"stage": "convert", "message": "Converting with djvudigital…"})
        args = ["djvudigital", *_PRESETS_DJVUDIGITAL[preset], str(source_pdf), str(djvu_out)]
        rc, _o, err = await _run(args, timeout=timeout)
        if rc != 0 or not djvu_out.exists():
            raise ConversionError(f"djvudigital failed: {err.strip()[:500]}")
    else:  # pdftoppm+c44
        await _convert_via_img2djvu(
            source_pdf=source_pdf, djvu_out=djvu_out, work_dir=work_dir,
            preset=preset, timeout=timeout, progress=progress,
        )
        # img2djvu rasterises everything and so destroys any text layer the
        # source PDF carried. Re-inject from the OCR engine's word boxes.
        if ocr and ocr_pages:
            await _emit(progress, {
                "stage": "textlayer", "message": "Embedding OCR text layer…",
            })
            dpi = _PRESETS_C44[preset][0]
            try:
                injected = await inject_text_layer(
                    djvu_path=djvu_out, pages=ocr_pages,
                    work_dir=work_dir, dpi=dpi, timeout=timeout,
                )
                if injected:
                    logger.info("Injected text layer for %d pages.", injected)
            except Exception as e:  # non-fatal — file is still useful without text
                logger.warning("Text-layer injection failed (non-fatal): %s", e)

    pages = await _count_pdf_pages(source_pdf, timeout=timeout)
    duration_ms = int((time.monotonic() - started) * 1000)
    return ConversionOutcome(
        djvu_path=djvu_out,
        pages=pages,
        duration_ms=duration_ms,
        ocr_text=ocr_text_pages,
        ocr_engine=ocr_engine_used,
    )

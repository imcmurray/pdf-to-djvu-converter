# syntax=docker/dockerfile:1.7
#
# Backend image. CPU-only by default; the OCR engine resolves to Tesseract.
# For GPU OCR (EasyOCR + CUDA torch) you'd need an nvidia/cuda base image plus
# the nvidia-container-toolkit on the host — out of scope here. The Python code
# already detects GPU presence at runtime, so a GPU image is a drop-in.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Conversion toolchain. Every CLI the backend shells out to:
#   pdf2djvu                — preferred PDF→DjVu converter
#   ddjvu djvused djvm c44 cjb2 djvudigital  — from djvulibre-bin
#   pdftoppm pdftotext pdfinfo                — from poppler-utils
#   ocrmypdf + tesseract + tesseract-ocr-eng  — OCR (English; add more lang
#                                               packs as image build args if needed)
#   ghostscript + imagemagick                 — PDF/image rendering deps
#   libmagic1                                 — python-magic runtime
#   curl                                      — healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        pdf2djvu \
        djvulibre-bin \
        poppler-utils \
        ocrmypdf \
        tesseract-ocr \
        tesseract-ocr-eng \
        ghostscript \
        imagemagick \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ImageMagick's default policy blocks PDFs; relax it so the backend can read
# PDFs that flow through ImageMagick (none today, but ocrmypdf may use it).
# Handle both v6 and v7 policy file locations.
RUN for f in /etc/ImageMagick-6/policy.xml /etc/ImageMagick-7/policy.xml; do \
        [ -f "$f" ] && sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' "$f" ; \
    done; \
    true

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Non-root user, storage dir under /tmp/pdf2djvu (matches STORAGE_DIR default).
RUN useradd -m -u 1000 appuser && \
    mkdir -p /tmp/pdf2djvu && chown -R appuser:appuser /tmp/pdf2djvu /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

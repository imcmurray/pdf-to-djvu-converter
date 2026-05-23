FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Conversion toolchain + libmagic for python-magic + curl for healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        pdf2djvu \
        djvulibre-bin \
        ocrmypdf \
        ghostscript \
        imagemagick \
        tesseract-ocr \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ImageMagick's default policy blocks PDFs; relax it so the backend can read them.
RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
        sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' \
            /etc/ImageMagick-6/policy.xml ; \
    fi

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /tmp/pdf2djvu && chown -R appuser:appuser /tmp/pdf2djvu /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""FastAPI entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import get_settings
from .routers import compare, convert, health, preview
from .security import limiter
from .storage import ShareStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = ShareStore(base_dir=settings.storage_dir, ttl_seconds=settings.storage_ttl_seconds)
    await store.start_sweeper()
    app.state.share_store = store
    try:
        yield
    finally:
        await store.stop_sweeper()


API_DESCRIPTION = """
Convert PDFs to the **DjVu** format with optional OCR, quality presets, batch
processing, side-by-side preview, and shareable download links.

### Conversion pipeline

The backend auto-selects the best installed converter:

1. **`pdf2djvu`** — preferred; preserves vector text and existing text layers
2. **`djvudigital`** — secondary; requires `gsdjvu`
3. **`pdftoppm` + `c44`/`cjb2` + `djvm`** — universal fallback (always works
   with poppler + djvulibre). Per-page bilevel vs continuous-tone routing.

The active converter is exposed via [`GET /api/health`](#tag/meta/operation/health_api_health_get).

### OCR engines

OCR is opt-in (set `ocr=true` on the convert form). The engine resolves from
the `OCR_ENGINE` env var:

| Value | Behaviour |
|---|---|
| `auto` (default) | EasyOCR (CUDA) if a GPU is detected, else Tesseract |
| `tesseract` | always CPU Tesseract via ocrmypdf |
| `easyocr` | force GPU EasyOCR; falls back to Tesseract if uninstalled |

### Streaming progress

`POST /api/convert` returns **`application/x-ndjson`** — one JSON event per
line. The client should read line-by-line and react to `stage` values
(`preflight`, `ocr`, `ocr_done`, `render`, `encode`, `assemble`, `textlayer`,
`done`, `error`). The terminal `done` event includes the `share_token` to
fetch the result via `GET /api/download/{token}`.

### Born-digital gate

`POST /api/convert` returns **409 Conflict** when the input PDF looks
born-digital (vector text, low bytes-per-page) — converting those is a
waste of time. Resubmit the same form with `force_born_digital=true` to
override.

### Rate limits

Per-IP, configured via `RATE_LIMIT_CONVERT` / `RATE_LIMIT_COMPARE`. Defaults
are `30/hour` and `60/hour` respectively. The `Retry-After` header is set
on 429 responses.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "convert",
        "description": (
            "Run the PDF→DjVu pipeline. The single-file endpoint streams "
            "newline-delimited progress events; the batch endpoint returns "
            "one summary per file."
        ),
    },
    {
        "name": "compare",
        "description": (
            "Convert and return metadata only — file sizes, compression ratio, "
            "page count, OCR engine used, optional share URL. The DjVu bytes "
            "are stored under a share token if `share=true`."
        ),
    },
    {
        "name": "share",
        "description": "Download a previously stored DjVu by share token (TTL-bounded).",
    },
    {
        "name": "preview",
        "description": (
            "Server-side rendering of stored DjVu pages to PNG (via ddjvu + "
            "Pillow), plus OCR-text retrieval for the in-UI text panel."
        ),
    },
    {
        "name": "meta",
        "description": "Liveness/readiness, tool availability, OCR engine status.",
    },
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PDF → DjVu Converter API",
        version="0.1.0",
        description=API_DESCRIPTION,
        summary="Convert PDFs to DjVu with OCR, presets, batching, and shareable links.",
        openapi_tags=OPENAPI_TAGS,
        contact={
            "name": "pdf-to-djvu-converter",
            "url": "https://github.com/anthropics/claude-code",
        },
        license_info={"name": "MIT", "identifier": "MIT"},
        lifespan=lifespan,
        # Mount docs under /api/* so the frontend's dev-server (Vite) and the
        # prod nginx — which both only proxy /api/* to the backend — can reach
        # them without an extra rewrite rule.
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        # Swagger UI niceties
        swagger_ui_parameters={
            "defaultModelsExpandDepth": 1,
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
            "persistAuthorization": True,
            "syntaxHighlight.theme": "monokai",
        },
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Conversion-Pages",
            "X-Conversion-Duration-Ms",
            "X-Conversion-Preset",
            "X-Pdf-Bytes",
            "X-Djvu-Bytes",
            "X-Share-Token",
            "Content-Disposition",
        ],
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Routes — everything lives under /api
    app.include_router(health.router, prefix="/api")
    app.include_router(convert.router, prefix="/api")
    app.include_router(convert.download_router, prefix="/api")
    app.include_router(compare.router, prefix="/api")
    app.include_router(preview.router, prefix="/api")

    return app


app = create_app()

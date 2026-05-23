# Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Browser (React + TS)                        │
│  Drag-drop PDF → /api/convert (XHR with upload progress)             │
│  Side-by-side viewers:  iframe(PDF)   |   djvu.js(canvas)            │
└────────────────────────────────────────────────┬─────────────────────┘
                                                 │ HTTPS / HTTP
                                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      nginx (frontend container)                      │
│  - Serves Vite-built SPA                                             │
│  - Reverse-proxies /api/* → backend:8000                             │
└────────────────────────────────────────────────┬─────────────────────┘
                                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  FastAPI (Uvicorn, backend container)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  /convert   │  │  /compare   │  │  /download  │  /health         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
│         └────────┬───────┘                │                          │
│                  ▼                        ▼                          │
│         ┌────────────────┐       ┌──────────────────┐                │
│         │ converter.py   │       │   storage.py     │                │
│         │  - ocrmypdf    │       │  TTL-purged      │                │
│         │  - pdf2djvu    │       │  share store     │                │
│         └────────┬───────┘       └──────────────────┘                │
│                  ▼                                                   │
│        subprocesses (arg-list, no shell)                             │
└──────────────────────────────────────────────────────────────────────┘
                  │
                  ▼ uses
        ocrmypdf + Tesseract + pdf2djvu + Ghostscript
```

## Module map

| Module | Responsibility |
|--------|----------------|
| `app/main.py` | App factory, CORS, rate-limit middleware, lifespan, router wiring |
| `app/config.py` | Pydantic-settings env loading + computed properties |
| `app/schemas.py` | Pydantic request/response models, `Preset` enum |
| `app/security.py` | MIME / magic-byte validation, filename safety, `slowapi` limiter |
| `app/converter.py` | OCR + pdf2djvu pipeline, page count detection, presets |
| `app/storage.py` | Token-keyed share store with background TTL sweeper |
| `app/routers/convert.py` | `POST /convert`, `POST /convert/batch`, `GET /download/{token}` |
| `app/routers/compare.py` | `POST /compare` (metadata-only) |
| `app/routers/health.py` | `GET /health` |

## Request lifecycle (POST /api/convert)

1. `SlowAPIMiddleware` checks the per-IP rate limit.
2. The handler streams the upload chunk-by-chunk, enforcing `MAX_UPLOAD_MB`.
3. `assert_pdf_or_raise` confirms PDF magic bytes (and libmagic MIME if available).
4. A scoped `TemporaryDirectory` is created under `STORAGE_DIR`.
5. If `ocr=true`, `ocrmypdf` runs first, producing `ocr.pdf`.
6. `pdf2djvu` converts the (possibly OCR'd) PDF to `output.djvu`.
7. Page count is derived via `pdfinfo` (fallback: regex over the PDF).
8. Result is stored under a random token and streamed back to the client; the temp dir is
   removed automatically when the `with` block exits.
9. A background task in `ShareStore` purges tokens older than `STORAGE_TTL_SECONDS`.

## Why these tools?

- **pdf2djvu** is the most actively maintained CLI bridging PDFs to DjVu and preserves text
  layers, metadata, outlines, and hyperlinks.
- **ocrmypdf** wraps Tesseract with sensible defaults (deskew, image cleanup, optimisation)
  and is happy to be invoked on documents that already have a text layer (`--skip-text`).
- **djvulibre** ships `pdfinfo`-adjacent utilities and is required at runtime by pdf2djvu.

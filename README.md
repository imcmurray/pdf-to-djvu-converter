# 📄 PDF → DjVu Converter

A modern, full-stack web application that converts PDF files to the DjVu format, with side-by-side comparison, OCR support, quality presets, batch processing, dark mode, and shareable links.

[![CI](https://github.com/imcmurray/pdf-to-djvu-converter/actions/workflows/ci.yml/badge.svg)](https://github.com/imcmurray/pdf-to-djvu-converter/actions/workflows/ci.yml)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20TS%20%2B%20Tailwind-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

- **Drag-and-drop upload** with progress bar and real-time conversion status
- **Side-by-side comparison** of the original PDF and converted DjVu in the browser
- **File size & compression ratio** displayed prominently after conversion
- **Optional OCR pass** (`ocrmypdf` / Tesseract) for searchable text layers
- **Quality presets** — `fast`, `balanced`, `high-quality`, `max-compression`
- **Batch conversion** — convert multiple PDFs in one request
- **Shareable links** — share a converted DjVu via a short token URL
- **Dark mode** — system-aware with manual override
- **Educational "What is DjVu?" page** explaining history, trade-offs vs PDF
- **Production-ready**: Docker + docker-compose, rate limiting, MIME sniffing, size limits

---

## 🧱 Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, Uvicorn, pydantic-settings |
| Conversion | `pdf2djvu`, `djvulibre`, `ocrmypdf`, `Ghostscript`, `ImageMagick` |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, React Router |
| PDF viewer | `pdf.js` (via iframe) |
| DjVu viewer | `djvu.js` |
| Container | Docker, docker-compose, nginx (frontend) |

---

## 🚀 Quick start

### Option A — Docker Compose (recommended)

```bash
git clone https://github.com/<you>/pdf-to-djvu-converter.git
cd pdf-to-djvu-converter
docker compose up --build
```

The canonical compose file is **`compose.yaml`** and ships with safe defaults — no `.env`
required. Copy `.env.example` to `.env` only if you want to override defaults.

Then open:

- **App + Swagger docs** → http://localhost:5173 (the frontend proxies `/api/*` to the backend, so Swagger lives at http://localhost:5173/api/docs)
- **Direct backend access** (optional) → http://localhost:8000

### Option A2 — Deploy via [Dockge](https://github.com/louislam/dockge)

This stack is Dockge-ready out of the box:

1. In Dockge, **Compose → Create new stack**, name it `pdf2djvu`.
2. Paste the contents of `compose.yaml` into the editor (or `git clone` directly into your
   Dockge stacks directory — e.g. `/opt/stacks/pdf2djvu/`).
3. (Optional) Add any overrides in the **Environment** tab — every variable is exposed via
   `${VAR:-default}`, so the stack runs with no env edits.
4. Click **Deploy**.

Default published ports are `5173` (frontend) and `8000` (backend); override with
`FRONTEND_PORT` / `BACKEND_PORT` env vars if those are taken on your host.

The DjVu output volume is named `pdf2djvu-storage` and persists across redeploys.

### Option B — Run locally without Docker

You'll need the conversion CLI tools installed:

**Debian/Ubuntu**
```bash
sudo apt-get install -y pdf2djvu djvulibre-bin ocrmypdf ghostscript imagemagick tesseract-ocr
```

**macOS (Homebrew)**
```bash
brew install pdf2djvu djvulibre ocrmypdf ghostscript imagemagick tesseract
```

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## 🔌 API

Once running, full interactive docs are available at **`/api/docs`** (Swagger) and **`/api/redoc`** on whichever host/port serves the app (e.g. http://localhost:5173/api/docs in the default dev/Docker setup).

### `POST /api/convert`

Convert a single PDF to DjVu.

| Field | Type | Description |
|-------|------|-------------|
| `file` | multipart file | The PDF (≤ 100 MB) |
| `preset` | form field | `fast` \| `balanced` \| `high-quality` \| `max-compression` (default: `balanced`) |
| `ocr` | form field | `true` \| `false` — run OCR before conversion (default `false`) |
| `share` | form field | `true` \| `false` — return a shareable link instead of bytes |

**Returns** `application/vnd.djvu` (or JSON with `share_url` if `share=true`).

### `POST /api/compare`

Returns JSON metadata comparing the PDF and the (just-)converted DjVu without forcing a download.

```json
{
  "pdf_bytes": 4837120,
  "djvu_bytes": 712384,
  "compression_ratio": 6.79,
  "size_reduction_pct": 85.27,
  "pages": 24,
  "preset": "balanced",
  "ocr": false,
  "duration_ms": 3421
}
```

### `POST /api/convert/batch`

Multipart with multiple `files`. Returns a JSON array, one entry per file, each containing a `share_url`.

### `GET /api/download/{token}`

Stream a previously stored conversion. Tokens expire (default 1 h, see `.env`).

### `GET /api/health`

Liveness probe.

---

## 📚 What is DjVu?

DjVu (pronounced *déjà vu*) is an open document format developed at AT&T in the late 1990s, designed to compress scanned documents far more aggressively than PDF — especially documents containing a mix of text, line art, and photographs. See the in-app **About** page for a deeper dive on history, internals, and trade-offs.

**TL;DR comparison**

| | PDF | DjVu |
|---|-----|------|
| Best for | Born-digital docs, vector graphics | Scanned books, archival imagery |
| Compression of scans | Good | Often 5–10× better |
| Ubiquity | Universal | Niche but supported by archive.org, scholar tools |
| Vector graphics | Yes | Limited |
| OCR text layer | Yes (via `ocrmypdf`) | Yes (preserved through `pdf2djvu`) |

---

## ⚠️ Limitations

- Conversion of complex vector PDFs (CAD, slide decks) is not DjVu's strength — for those, stick with PDF.
- OCR adds 5–60 s per page depending on hardware and language.
- Maximum file size is 100 MB by default (configurable via `MAX_UPLOAD_MB`).
- Browser DjVu rendering uses `djvu.js`, which is heavier than native PDF rendering.

---

## 🔒 Security & operational notes

- Files are written to a sandboxed temp directory (`STORAGE_DIR`) and purged on a TTL (`STORAGE_TTL_SECONDS`).
- MIME and magic-byte validation rejects anything that isn't a real PDF.
- IP-based rate limiting via `slowapi` (default: 30 conversions / hour / IP).
- All subprocess invocations use argument arrays, never shell strings.
- Set `ALLOWED_ORIGINS` in `.env` to restrict CORS in production.

---

## 🧪 Tests

```bash
cd backend
pytest -q
```

---

## 📜 License

MIT — see [LICENSE](./LICENSE).

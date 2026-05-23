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

CI publishes two pre-built images to **GitHub Container Registry** on every push to `main` and every git tag:

- `ghcr.io/imcmurray/pdf-to-djvu-converter-backend:latest`
- `ghcr.io/imcmurray/pdf-to-djvu-converter-frontend:latest`

Both are public — no GitHub token needed to pull. The fastest paths use these images directly.

### Option A — Docker Compose (recommended, no source clone)

Save just the [`compose.yaml`](./compose.yaml) somewhere and run:

```bash
curl -O https://raw.githubusercontent.com/imcmurray/pdf-to-djvu-converter/main/compose.yaml
docker compose up -d
```

`docker compose` pulls both images from GHCR and starts them. The `compose.yaml` has safe inline defaults so it runs with **no `.env` file**.

Then open:

- **App + Swagger docs** → http://localhost:5173 — the nginx in the frontend image proxies `/api/*` to the backend, so Swagger lives at http://localhost:5173/api/docs
- **Direct backend access** (optional) → http://localhost:8000

### Option B — Deploy via [Dockge](https://github.com/louislam/dockge)

Identical setup, GUI-driven:

1. In Dockge, **Compose → Create new stack**, name it `pdf2djvu`.
2. **Paste the contents of [`compose.yaml`](./compose.yaml)** into the editor.
3. (Optional) Add overrides in the **Environment** tab — every var below is `${VAR:-default}` in the compose, so the stack runs without any of them set:

   | Var | Default | What it does |
   |---|---|---|
   | `IMAGE_TAG` | `latest` | Pin to a specific release, e.g. `v0.2.0` or `sha-a1aaeed` |
   | `PULL_POLICY` | `missing` | Set to `always` to refresh on every restart |
   | `FRONTEND_PORT` / `BACKEND_PORT` | `5173` / `8000` | Override published host ports |
   | `OCR_ENGINE` | `auto` | `tesseract` / `easyocr` to force an engine |
   | `OCR_LANGUAGE` | `eng` | Tesseract code(s), e.g. `eng+deu` |
   | `MAX_UPLOAD_MB` | `100` | Upload size cap |
   | `STORAGE_TTL_SECONDS` | `3600` | Share-link TTL |
   | `RATE_LIMIT_CONVERT` / `RATE_LIMIT_COMPARE` | `30/hour` / `60/hour` | Per-IP rate limits |
4. Click **Deploy**.

Dockge runs `docker compose pull` then `up -d` — no source on the host, no compile step. The DjVu output volume is `pdf2djvu-storage` and persists across redeploys.

### Option C — Build the Docker images yourself

For development, forks, or air-gapped hosts:

```bash
git clone https://github.com/imcmurray/pdf-to-djvu-converter.git
cd pdf-to-djvu-converter
docker compose up --build       # builds both images from ./backend and ./frontend
```

`compose.yaml` has both `image:` (GHCR) and `build:` (local context) — `--build` rebuilds locally and tags with the same image name, so subsequent `docker compose up` uses your local build until the next `docker compose pull`.

### Option D — Run locally without Docker

There's a one-shot setup script that handles OS detection, system CLIs, Python venv, and npm:

```bash
git clone https://github.com/imcmurray/pdf-to-djvu-converter.git
cd pdf-to-djvu-converter
./scripts/dev.sh setup          # installs CLIs (pacman/apt/brew), venv, npm deps,
                                # auto-detects NVIDIA GPU → installs EasyOCR+CUDA torch
./scripts/dev.sh up             # backend (:8000) + frontend (:5173) with combined logs
```

Other subcommands: `setup-gpu` (manual GPU install), `check` (verify CLIs + engine status), `test` (backend pytest), `clean` (nuke venv + node_modules).

Manual setup if you'd rather not run the script — install the conversion CLIs:

| OS | Command |
|---|---|
| Debian/Ubuntu | `sudo apt install pdf2djvu djvulibre-bin poppler-utils ocrmypdf ghostscript imagemagick tesseract-ocr tesseract-ocr-eng libmagic1` |
| Arch | `sudo pacman -S djvulibre tesseract tesseract-data-eng ghostscript imagemagick poppler && yay -S pdf2djvu ocrmypdf` |
| macOS | `brew install pdf2djvu djvulibre ocrmypdf ghostscript imagemagick tesseract poppler libmagic` |

Then:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
# in another terminal:
cd frontend && npm install && npm run dev
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

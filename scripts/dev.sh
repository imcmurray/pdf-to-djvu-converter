#!/usr/bin/env bash
# Local-development helper for pdf-to-djvu-converter.
#
# Usage:
#   scripts/dev.sh setup       # one-time: install system CLIs, Python venv, npm deps
#                              # (auto-installs GPU OCR support if an NVIDIA GPU is detected)
#   scripts/dev.sh setup-gpu   # install/upgrade CUDA torch + EasyOCR into the venv
#   scripts/dev.sh check       # verify all required CLI tools are present
#   scripts/dev.sh backend     # run FastAPI on :8000
#   scripts/dev.sh frontend    # run Vite on :5173
#   scripts/dev.sh up          # run both, side-by-side, with combined logs
#   scripts/dev.sh test        # backend pytest
#   scripts/dev.sh clean       # remove .venv, node_modules, build artefacts
#
# Safe to re-run. Detects pacman / apt / brew automatically.

set -euo pipefail

# Resolve repo root regardless of where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

# Colours — disabled if not a TTY (e.g. piped to a logger).
if [[ -t 1 ]]; then
  C_RED=$'\033[0;31m'; C_GRN=$'\033[0;32m'; C_YEL=$'\033[0;33m'
  C_BLU=$'\033[0;34m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_DIM=""; C_OFF=""
fi
log()  { printf "%s==>%s %s\n" "$C_BLU" "$C_OFF" "$*"; }
ok()   { printf "%s ✓ %s%s\n" "$C_GRN" "$*" "$C_OFF"; }
warn() { printf "%s ! %s%s\n" "$C_YEL" "$*" "$C_OFF"; }
err()  { printf "%s ✗ %s%s\n" "$C_RED" "$*" "$C_OFF" >&2; }

# ----------------------------------------------------------------------- #
# Package manager detection
# ----------------------------------------------------------------------- #
detect_pm() {
  if command -v pacman &>/dev/null; then echo "pacman"
  elif command -v apt-get &>/dev/null; then echo "apt"
  elif command -v brew &>/dev/null; then echo "brew"
  else echo "unknown"
  fi
}

install_system_deps() {
  local pm
  pm="$(detect_pm)"
  log "Detected package manager: $pm"

  case "$pm" in
    pacman)
      # Refresh the package database first — stale mirror caches cause 404s on
      # packages that were just bumped upstream (e.g. python-pikepdf).
      log "Refreshing pacman database (sudo pacman -Sy)"
      sudo pacman -Sy --noconfirm

      # Only the official-repo packages go through pacman. pdf2djvu and ocrmypdf
      # live in the AUR — handled separately below.
      sudo pacman -S --needed --noconfirm \
        djvulibre tesseract tesseract-data-eng \
        ghostscript imagemagick poppler file python python-pip nodejs npm

      # The backend picks a converter automatically in this preference order:
      #   1. pdf2djvu       — best quality (AUR, often broken on bleeding-edge Arch)
      #   2. djvudigital    — needs gsdjvu (separate AUR build)
      #   3. pdftoppm + c44 — always works once poppler + djvulibre are installed
      # We try pdf2djvu via AUR helpers if available, but failure is non-fatal —
      # the universal img2djvu fallback uses the tools we already installed above.
      if ! command -v pdf2djvu &>/dev/null; then
        if command -v paru &>/dev/null; then
          log "Trying to install pdf2djvu from the AUR (paru)…"
          paru -S --needed --noconfirm pdf2djvu || true
        elif command -v yay &>/dev/null; then
          log "Trying to install pdf2djvu from the AUR (yay)…"
          yay -S --needed --noconfirm pdf2djvu || true
        fi
      fi

      if command -v pdf2djvu &>/dev/null; then
        ok "Using pdf2djvu (best quality)"
      elif command -v c44 &>/dev/null && command -v djvm &>/dev/null && command -v pdftoppm &>/dev/null; then
        warn "pdf2djvu unavailable (known Arch/Poppler-26 build issue)."
        ok "Backend will use the pdftoppm + c44 + djvm fallback — fully functional."
      else
        err "Couldn't find pdf2djvu and the c44/djvm/pdftoppm fallback is incomplete."
        err "Make sure 'djvulibre' and 'poppler' installed successfully."
        exit 1
      fi

      # ocrmypdf is optional (only used when OCR is requested). Try AUR, then pipx.
      if ! command -v ocrmypdf &>/dev/null; then
        if   command -v paru &>/dev/null; then paru -S --needed --noconfirm ocrmypdf || true
        elif command -v yay  &>/dev/null; then yay  -S --needed --noconfirm ocrmypdf || true
        elif command -v pipx &>/dev/null; then pipx install ocrmypdf || true
        else warn "ocrmypdf not installed (OCR feature disabled). Install paru/yay or run 'pipx install ocrmypdf' later."
        fi
      fi
      ;;
    apt)
      sudo apt-get update
      sudo apt-get install -y \
        pdf2djvu djvulibre-bin ocrmypdf ghostscript imagemagick \
        tesseract-ocr poppler-utils libmagic1 \
        python3 python3-venv python3-pip nodejs npm
      ;;
    brew)
      brew install pdf2djvu djvulibre ocrmypdf ghostscript imagemagick \
                   tesseract poppler libmagic node python@3.11
      ;;
    *)
      err "Unsupported package manager. Install these manually: pdf2djvu, djvulibre, ocrmypdf, ghostscript, imagemagick, tesseract, poppler, libmagic, python3, node."
      return 1
      ;;
  esac
}

# Some Linux distros ship ImageMagick with PDFs disabled by policy. Relax it
# (read+write) so ocrmypdf-style pipelines don't blow up.
fix_imagemagick_policy() {
  local policies=(/etc/ImageMagick-7/policy.xml /etc/ImageMagick-6/policy.xml)
  for f in "${policies[@]}"; do
    if [[ -f "$f" ]] && grep -q 'pattern="PDF"' "$f" && grep -q 'rights="none" pattern="PDF"' "$f"; then
      log "Relaxing ImageMagick PDF policy in $f"
      sudo sed -i.bak 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' "$f"
      ok "ImageMagick PDF policy updated (backup at $f.bak)"
    fi
  done
}

# ----------------------------------------------------------------------- #
# Backend setup
# ----------------------------------------------------------------------- #
setup_backend() {
  log "Setting up Python venv at $VENV_DIR"
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"

  # Sanity check the Python version. Backend requires 3.11+; <3.10 is unsupported.
  local pyver
  pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  log "Using Python $pyver from $(python3 -c 'import sys; print(sys.executable)')"
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
    err "Python 3.11+ required (found $pyver). Install python3.11+ and re-run."
    deactivate
    return 1
  fi

  pip install --upgrade pip
  pip install -r "$BACKEND_DIR/requirements.txt"
  deactivate
  ok "Backend dependencies installed"
}

# ----------------------------------------------------------------------- #
# Frontend setup
# ----------------------------------------------------------------------- #
# ----------------------------------------------------------------------- #
# GPU OCR (EasyOCR + CUDA torch)
# ----------------------------------------------------------------------- #
detect_nvidia_gpu() {
  command -v nvidia-smi &>/dev/null && nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1
}

setup_gpu() {
  [[ -d "$VENV_DIR" ]] || { err "Run 'scripts/dev.sh setup' first to create the venv."; return 1; }
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"

  local gpu
  gpu=$(detect_nvidia_gpu || true)
  if [[ -z "$gpu" ]]; then
    warn "No NVIDIA GPU detected (nvidia-smi missing or returned nothing)."
    warn "GPU OCR requires the NVIDIA proprietary driver. On Arch:"
    warn "    sudo pacman -S nvidia nvidia-utils"
    warn "    sudo reboot"
    warn "Then re-run 'scripts/dev.sh setup-gpu'."
    deactivate
    return 1
  fi
  ok "Detected NVIDIA GPU: $gpu"

  local pyver
  pyver=$(python -c 'import sys; print(f"py{sys.version_info[0]}.{sys.version_info[1]}")')
  log "Looking for CUDA torch wheel matching $pyver…"

  # PyTorch ships per-CUDA-version wheel indexes. Newer Python versions only
  # land on the newer indexes (e.g. Python 3.14 won't be on cu121). Try newest
  # → oldest, plus the nightly index as a last resort.
  local indexes=(
    "https://download.pytorch.org/whl/cu128"
    "https://download.pytorch.org/whl/cu126"
    "https://download.pytorch.org/whl/cu124"
    "https://download.pytorch.org/whl/cu121"
    "https://download.pytorch.org/whl/nightly/cu126"
  )
  local installed_index=""
  for idx in "${indexes[@]}"; do
    log "Trying $idx …"
    if pip install --upgrade --index-url "$idx" torch; then
      installed_index="$idx"
      break
    fi
    warn "no wheel on $idx for $pyver — trying next."
  done

  if [[ -z "$installed_index" ]]; then
    err "No CUDA torch wheel is available for $pyver on any tried index."
    err ""
    err "PyTorch's CUDA wheels often lag bleeding-edge Python releases by a few months."
    err "Your options:"
    err "  1. Wait — re-run 'scripts/dev.sh setup-gpu' periodically."
    err "  2. Create a Python 3.13 venv instead:"
    err "       python3.13 -m venv backend/.venv"
    err "       ./scripts/dev.sh setup"
    err "  3. Stick with CPU Tesseract — it's already configured and works fine."
    err ""
    err "Backend will fall back to CPU Tesseract automatically; this is non-fatal."
    deactivate
    return 1
  fi
  ok "torch installed from $installed_index"

  log "Installing EasyOCR + dependencies…"
  pip install -r "$BACKEND_DIR/requirements-gpu.txt" || {
    err "EasyOCR install failed."
    deactivate
    return 1
  }

  log "Verifying GPU acceleration end-to-end…"
  local verify_rc=0
  python - <<'PY' || verify_rc=$?
import sys
import torch
print(f"  torch: {torch.__version__}")
print(f"  CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  device: {torch.cuda.get_device_name(0)}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory // (1024**3)} GB")
else:
    print("  WARNING: torch installed but torch.cuda.is_available() is False.")
    print("  The wheel may be CPU-only, or the NVIDIA driver isn't matching the CUDA runtime.")
    sys.exit(2)
try:
    import easyocr
    print(f"  easyocr: {easyocr.__version__}")
except Exception as e:
    print(f"  easyocr import failed: {e}")
    sys.exit(3)
PY

  if [[ $verify_rc -ne 0 ]]; then
    warn "GPU verification failed (rc=$verify_rc) — see notes above."
    warn "Backend will fall back to CPU Tesseract until this is resolved."
    deactivate
    return 1
  fi
  ok "GPU OCR is ready. EasyOCR will auto-activate on next conversion with OCR ticked."
  deactivate
}

setup_frontend() {
  log "Installing frontend deps (npm install)"
  (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund)
  ok "Frontend dependencies installed"
}

# ----------------------------------------------------------------------- #
# Check
# ----------------------------------------------------------------------- #
check_tools() {
  local required=(tesseract gs convert python3 node npm)
  local optional=(ocrmypdf pdfinfo)
  local missing=()

  log "Checking required tools…"
  for t in "${required[@]}"; do
    if command -v "$t" &>/dev/null; then
      ok "$t  $($t --version 2>&1 | head -n1 || true)"
    else
      err "$t missing"; missing+=("$t")
    fi
  done

  # PDF→DjVu converter: one of three strategies must be available.
  log "Checking PDF→DjVu converter…"
  if command -v pdf2djvu &>/dev/null; then
    ok "pdf2djvu  $(pdf2djvu --version 2>&1 | head -n1)  (preferred)"
  elif command -v djvudigital &>/dev/null && djvudigital --help 2>&1 | grep -qi 'usage'; then
    ok "djvudigital  (secondary fallback)"
  elif command -v pdftoppm &>/dev/null && command -v c44 &>/dev/null && command -v djvm &>/dev/null; then
    ok "pdftoppm + c44 + djvm  (universal img2djvu fallback)"
  else
    err "No working PDF→DjVu converter found"
    missing+=("pdf2djvu-or-djvulibre+poppler")
  fi

  log "Checking optional tools…"
  for t in "${optional[@]}"; do
    if command -v "$t" &>/dev/null; then
      ok "$t  $($t --version 2>&1 | head -n1 || true)"
    else
      warn "$t missing (OCR / page count fallback will be skipped)"
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    err "Missing required tools: ${missing[*]}"
    return 1
  fi
  ok "All required tools present"

  log "Checking OCR engine status…"
  if [[ -d "$VENV_DIR" ]]; then
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    python - <<'PY'
try:
    from app.ocr import select_engine, easyocr_importable, gpu_available, gpu_info
    print(f"  active engine (auto): {select_engine('auto')}")
    print(f"  easyocr installed:    {easyocr_importable()}")
    print(f"  GPU available:        {gpu_available()}")
    if gpu_available():
        print(f"  GPU:                  {gpu_info()}")
except Exception as e:
    print(f"  (could not import backend: {e})")
PY
    deactivate
  else
    warn "venv missing — run 'scripts/dev.sh setup' first."
  fi
}

# ----------------------------------------------------------------------- #
# Runners
# ----------------------------------------------------------------------- #
run_backend() {
  [[ -d "$VENV_DIR" ]] || { err "venv missing — run 'scripts/dev.sh setup' first"; exit 1; }
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  cd "$BACKEND_DIR"
  log "Starting FastAPI on http://localhost:8000  (docs: /api/docs)"
  exec uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
}

run_frontend() {
  [[ -d "$FRONTEND_DIR/node_modules" ]] || { err "node_modules missing — run 'scripts/dev.sh setup' first"; exit 1; }
  cd "$FRONTEND_DIR"
  log "Starting Vite dev server on http://localhost:5173"
  exec npm run dev
}

# Run backend + frontend together and forward Ctrl-C to both.
run_both() {
  [[ -d "$VENV_DIR"          ]] || { err "Run 'scripts/dev.sh setup' first."; exit 1; }
  [[ -d "$FRONTEND_DIR/node_modules" ]] || { err "Run 'scripts/dev.sh setup' first."; exit 1; }

  local pids=()
  cleanup() {
    printf "\n%s==>%s shutting down…\n" "$C_BLU" "$C_OFF"
    for pid in "${pids[@]:-}"; do
      kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    exit 0
  }
  trap cleanup INT TERM

  ( "$0" backend  2>&1 | sed -u "s/^/$(printf '%sbackend %s ' "$C_BLU" "$C_OFF")/" ) &
  pids+=($!)
  ( "$0" frontend 2>&1 | sed -u "s/^/$(printf '%sfrontend%s ' "$C_GRN" "$C_OFF")/" ) &
  pids+=($!)

  log "Frontend → http://localhost:5173      (Swagger via proxy: /api/docs)"
  log "Backend  → http://localhost:8000      (direct access; also serves /api/docs)"
  log "Press Ctrl-C to stop both."
  wait
}

# ----------------------------------------------------------------------- #
# Test / clean
# ----------------------------------------------------------------------- #
run_tests() {
  [[ -d "$VENV_DIR" ]] || { err "venv missing — run 'scripts/dev.sh setup' first"; exit 1; }
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  cd "$BACKEND_DIR"
  exec pytest -q
}

clean() {
  log "Removing .venv, node_modules, build/dist directories"
  rm -rf "$VENV_DIR" "$FRONTEND_DIR/node_modules" "$FRONTEND_DIR/dist"
  find "$BACKEND_DIR" -type d \( -name __pycache__ -o -name .pytest_cache \) -exec rm -rf {} + 2>/dev/null || true
  ok "Cleaned"
}

# ----------------------------------------------------------------------- #
# Entry point
# ----------------------------------------------------------------------- #
usage() {
  sed -n '2,15p' "$0"
}

cmd="${1:-}"
case "$cmd" in
  setup)
    install_system_deps
    fix_imagemagick_policy
    setup_backend
    setup_frontend
    # If an NVIDIA GPU is present, auto-install the GPU OCR stack so the
    # default "ocr_engine=auto" actually resolves to EasyOCR.
    if gpu=$(detect_nvidia_gpu) && [[ -n "$gpu" ]]; then
      log "NVIDIA GPU found ($gpu) — installing GPU OCR support (EasyOCR + CUDA torch)."
      setup_gpu || warn "GPU OCR setup failed; backend will fall back to CPU Tesseract."
    else
      log "No NVIDIA GPU detected — sticking with CPU Tesseract for OCR."
      log "If you add a GPU later, run:  scripts/dev.sh setup-gpu"
    fi
    check_tools || true
    log "Done. Start everything with:  scripts/dev.sh up"
    ;;
  setup-gpu) setup_gpu ;;
  check)    check_tools ;;
  backend)  run_backend ;;
  frontend) run_frontend ;;
  up)       run_both ;;
  test)     run_tests ;;
  clean)    clean ;;
  -h|--help|help|"") usage ;;
  *)
    err "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac

import { useEffect, useState } from "react";
import { fetchHealth, type HealthInfo } from "../api/client";

export function System() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((e) => setError((e as Error).message));
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200">
          Couldn't load system info: {error}
        </div>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10 text-sm text-slate-500 dark:text-slate-400">
        Loading…
      </div>
    );
  }

  const useEasyOCR = health.ocr_engine_active === "easyocr";

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 space-y-10">
      <header className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wider text-brand-600 dark:text-brand-400">
          System
        </p>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
          OCR engine &amp; hardware
        </h1>
        <p className="text-slate-600 dark:text-slate-300">
          OCR is the slowest step of the conversion. This page shows which engine is currently
          running, whether your hardware supports GPU acceleration, and how to opt in if it does.
        </p>
      </header>

      {/* Active status card */}
      <section className="card space-y-4">
        <h2 className="text-xl font-semibold">Active configuration</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <KV label="Active OCR engine" value={
            <span className={useEasyOCR ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300"}>
              {health.ocr_engine_active}{" "}
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {useEasyOCR ? "(GPU)" : "(CPU)"}
              </span>
            </span>
          } />
          <KV label="Preference" value={health.ocr_engine_preference} />
          <KV
            label="EasyOCR installed"
            value={<Pill ok={health.easyocr_available}>{String(health.easyocr_available)}</Pill>}
          />
          <KV
            label="GPU detected (CUDA)"
            value={<Pill ok={health.gpu_available}>{String(health.gpu_available)}</Pill>}
          />
          {health.gpu_info && <KV label="GPU device" value={<span className="font-mono">{health.gpu_info}</span>} />}
          <KV label="Active DjVu converter" value={<span className="font-mono">{health.active_converter ?? "none"}</span>} />
        </div>
      </section>

      {/* Status-specific guidance */}
      {useEasyOCR ? (
        <section className="card bg-emerald-50/50 border-emerald-200 dark:bg-emerald-900/10 dark:border-emerald-900/40 space-y-3">
          <h2 className="text-xl font-semibold text-emerald-900 dark:text-emerald-100">
            ✓ GPU OCR is active
          </h2>
          <p className="text-sm text-emerald-900/90 dark:text-emerald-100/90">
            Conversions with OCR ticked will run through EasyOCR on your GPU
            ({health.gpu_info ?? "CUDA device"}). Expect roughly{" "}
            <strong>3–10× faster</strong> OCR than CPU Tesseract, especially on long
            scanned documents.
          </p>
        </section>
      ) : health.gpu_available && !health.easyocr_available ? (
        <section className="card border-amber-200 bg-amber-50/50 dark:border-amber-900/40 dark:bg-amber-900/10 space-y-3">
          <h2 className="text-xl font-semibold text-amber-900 dark:text-amber-100">
            ⚠ GPU detected, but EasyOCR is not installed
          </h2>
          <p className="text-sm text-amber-900/90 dark:text-amber-100/90">
            We see a CUDA-capable device ({health.gpu_info ?? "GPU"}), but the EasyOCR
            package isn't available in the backend's Python environment. Install it to
            unlock GPU OCR:
          </p>
          <CodeBlock>{`# From the project root:
./scripts/dev.sh setup-gpu

# Or manually:
source backend/.venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cu121 torch
pip install -r backend/requirements-gpu.txt`}</CodeBlock>
          <p className="text-xs text-amber-900/80 dark:text-amber-100/80">
            The install is ~1 GB (PyTorch + CUDA runtime + EasyOCR model weights).
            After it finishes, restart the backend — the engine will switch automatically.
          </p>
        </section>
      ) : (
        <section className="card border-slate-200 dark:border-slate-800 space-y-3">
          <h2 className="text-xl font-semibold">No CUDA GPU available — using CPU Tesseract</h2>
          <p className="text-sm text-slate-700 dark:text-slate-300">
            OCR is currently running on the CPU via Tesseract (through ocrmypdf). That works fine
            for everything; on large scanned books it'll just be slower than GPU OCR.
          </p>
          <details className="text-sm text-slate-700 dark:text-slate-300">
            <summary className="cursor-pointer font-medium text-slate-900 dark:text-slate-100">
              How to enable GPU OCR
            </summary>
            <div className="mt-3 space-y-2 pl-2">
              <p>You'll need:</p>
              <ul className="list-disc pl-6 space-y-1">
                <li>An NVIDIA GPU with at least 2 GB VRAM (CUDA compute capability 5.0+).</li>
                <li>
                  The proprietary NVIDIA driver installed on the host.
                  On Arch: <code className="font-mono text-xs">sudo pacman -S nvidia nvidia-utils</code>, then reboot.
                </li>
                <li>
                  Run <code className="font-mono text-xs">./scripts/dev.sh setup-gpu</code> to install
                  PyTorch with CUDA wheels + EasyOCR into the backend venv.
                </li>
              </ul>
              <p>The backend will start using the GPU on its next request — no config change needed.</p>
            </div>
          </details>
        </section>
      )}

      {/* How OCR fits the pipeline */}
      <section className="card space-y-3">
        <h2 className="text-xl font-semibold">How OCR fits the pipeline</h2>
        <ol className="list-decimal pl-6 space-y-2 text-sm text-slate-700 dark:text-slate-300">
          <li>
            When you tick <strong>Run OCR</strong>, the backend resolves your{" "}
            <code className="font-mono text-xs">OCR_ENGINE</code> preference. With{" "}
            <code className="font-mono text-xs">auto</code> (the default), it picks EasyOCR if a CUDA GPU
            is detectable, otherwise Tesseract.
          </li>
          <li>
            The chosen engine produces per-page word-level bounding boxes from your PDF.
          </li>
          <li>
            Those word boxes power two things:
            <ul className="mt-1 list-disc pl-6 space-y-1">
              <li>The <strong>OCR text</strong> tab in the DjVu pane, for quality inspection.</li>
              <li>
                A DjVu hidden-text layer injected via <code className="font-mono text-xs">djvused</code>,
                making the downloaded <code className="font-mono text-xs">.djvu</code> searchable in any
                desktop viewer (djview, the Internet Archive's reader, etc.).
              </li>
            </ul>
          </li>
          <li>
            The visual conversion (DjVu page rendering) runs independently of OCR — same{" "}
            <code className="font-mono text-xs">pdf2djvu</code> /{" "}
            <code className="font-mono text-xs">djvudigital</code> /{" "}
            <code className="font-mono text-xs">pdftoppm+c44</code> pipeline either way.
          </li>
        </ol>
      </section>

      {/* Engine comparison */}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Engine comparison</h2>
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left dark:bg-slate-800/60">
              <tr>
                <th className="px-4 py-3 font-medium">Trait</th>
                <th className="px-4 py-3 font-medium">Tesseract (CPU)</th>
                <th className="px-4 py-3 font-medium">EasyOCR (CUDA)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              <Row trait="Hardware" a="Any CPU" b="NVIDIA GPU (2 GB+ VRAM)" />
              <Row trait="Speed" a="~1–2 s/page" b="~0.2–0.5 s/page" />
              <Row trait="Setup cost" a="~30 MB (ships with ocrmypdf)" b="~1 GB (PyTorch + CUDA + model)" />
              <Row trait="Preprocessing" a="deskew + auto-rotate" a_meta="ocrmypdf" b="Built-in rotation tolerance" />
              <Row trait="Languages" a="Per Tesseract language pack" b="80+ baked into the model" />
              <Row trait="Accuracy: clean prints" a="Excellent" b="Excellent" />
              <Row trait="Accuracy: degraded scans" a="Good" b="Very good" />
              <Row trait="Word-level boxes" a="Yes" b="Yes" />
              <Row trait="DjVu text-layer injection" a="✓" b="✓" />
            </tbody>
          </table>
        </div>
      </section>

      {/* Override */}
      <section className="card space-y-3">
        <h2 className="text-xl font-semibold">Forcing a specific engine</h2>
        <p className="text-sm text-slate-700 dark:text-slate-300">
          Set the <code className="font-mono text-xs">OCR_ENGINE</code> env var when starting the
          backend (or in your <code className="font-mono text-xs">.env</code>):
        </p>
        <CodeBlock>{`OCR_ENGINE=auto       # default — GPU if available, else CPU
OCR_ENGINE=tesseract  # always CPU
OCR_ENGINE=easyocr    # force GPU; falls back to Tesseract if uninstalled`}</CodeBlock>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          You can verify the resolved choice any time via{" "}
          <a className="link font-mono" href="/api/health" target="_blank" rel="noreferrer">
            /api/health
          </a>{" "}
          (also visible in the{" "}
          <a className="link" href="/api/docs" target="_blank" rel="noreferrer">
            interactive API docs
          </a>
          ){" "}
          — the <code className="font-mono">ocr_engine_active</code> field shows which engine the
          backend will actually use.
        </p>
      </section>
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="mt-1 text-base font-semibold">{value}</div>
    </div>
  );
}

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        ok
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
          : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
      ].join(" ")}
    >
      {children}
    </span>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100 dark:bg-slate-950">
      <code>{children}</code>
    </pre>
  );
}

function Row({
  trait, a, b, a_meta,
}: { trait: string; a: string; b: string; a_meta?: string }) {
  return (
    <tr>
      <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">{trait}</td>
      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">
        {a}
        {a_meta && <span className="ml-1 text-xs text-slate-500 dark:text-slate-400">({a_meta})</span>}
      </td>
      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{b}</td>
    </tr>
  );
}

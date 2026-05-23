import { useState } from "react";
import { Link } from "react-router-dom";
import { Dropzone } from "../components/Dropzone";
import { PresetSelector } from "../components/PresetSelector";
import { StepProgress } from "../components/StepProgress";
import { BornDigitalModal } from "../components/BornDigitalModal";
import { ComparisonView } from "../components/ComparisonView";
import { ConversionStats } from "../components/ConversionStats";
import { ShareLink } from "../components/ShareLink";
import { useConvert } from "../hooks/useConvert";
import type { Preset } from "../api/client";

export function Home() {
  const [preset, setPreset] = useState<Preset>("balanced");
  const [ocr, setOcr] = useState(false);
  const { state, start, confirmBornDigital, reset } = useConvert();

  const busy = state.stage === "running";

  const download = () => {
    if (!state.result) return;
    const a = document.createElement("a");
    a.href = state.result.djvuUrl;
    a.download = state.result.filename;
    a.click();
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-10 space-y-8">
      {/* Hero */}
      <section className="space-y-3">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
          Convert PDF to DjVu
        </h1>
        <p className="text-slate-600 dark:text-slate-300">
          Upload a PDF, pick a quality preset, and get a DjVu file that's typically{" "}
          <span className="font-semibold">5–10× smaller</span> than the original — perfect for
          scanned books and archival documents. OCR keeps your text searchable.
        </p>
      </section>

      {/* Conversion card */}
      <section className="card space-y-6">
        {state.stage === "idle" && (
          <>
            <Dropzone onFile={(f) => start(f, preset, ocr)} maxMB={100} />
            <PresetSelector
              value={preset}
              onChange={setPreset}
              ocr={ocr}
              onOcrChange={setOcr}
            />
          </>
        )}

        {busy && (
          <div className="space-y-4">
            <StepProgress step={state.step} history={state.history} />
            <button type="button" className="btn-secondary" onClick={reset}>
              Cancel
            </button>
          </div>
        )}

        {state.stage === "error" && (
          <div className="space-y-3">
            <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200">
              <strong>Conversion failed.</strong> {state.error}
            </div>
            <button type="button" className="btn-secondary" onClick={reset}>
              Try again
            </button>
          </div>
        )}

        {state.stage === "done" && state.result && (
          <div className="space-y-6">
            <ConversionStats meta={state.result.meta} />

            {state.result.meta.djvu_bytes > state.result.meta.pdf_bytes && (
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700/60 dark:bg-amber-900/20">
                <p className="font-medium text-amber-900 dark:text-amber-100">
                  ⚠ Heads up — the DjVu is larger than the original PDF.
                </p>
                <p className="mt-1 text-amber-800 dark:text-amber-200/90">
                  This usually means the source PDF is <strong>born-digital</strong>
                  {" "}(vector text and layout, not a scan). PDF stores those as compact
                  drawing instructions; converting to DjVu rasterises every page first,
                  so the output is bigger than the input. DjVu's compression wins only
                  show up on <strong>scanned</strong> PDFs — try a scanned book or
                  archival document to see the typical 5–10× size reduction.{" "}
                  <Link to="/about" className="link font-medium">
                    Learn more →
                  </Link>
                </p>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="btn-primary" onClick={download}>
                Download .djvu
              </button>
              <button type="button" className="btn-secondary" onClick={reset}>
                Convert another
              </button>
              <div className="ml-auto w-full sm:w-auto">
                <ShareLink file={state.result.file} preset={preset} ocr={ocr} />
              </div>
            </div>

            <ComparisonView
              pdfUrl={state.result.pdfUrl}
              shareToken={state.result.shareToken}
              pagesHint={state.result.meta.pages}
            />
          </div>
        )}
      </section>

      {state.stage === "needs_confirm" && state.bornDigital && (
        <BornDigitalModal
          inspection={state.bornDigital}
          onConfirm={confirmBornDigital}
          onCancel={reset}
        />
      )}

      {/* Helper section */}
      {state.stage === "idle" && (
        <section className="grid gap-4 sm:grid-cols-3">
          <div className="card">
            <h3 className="font-semibold">Quality presets</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Pick speed or maximum compression — defaults are tuned for scanned books.
            </p>
          </div>
          <div className="card">
            <h3 className="font-semibold">Optional OCR</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Add a searchable text layer with ocrmypdf before converting.
            </p>
          </div>
          <div className="card">
            <h3 className="font-semibold">Shareable links</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Generate a short URL teammates can use to download the DjVu output.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}

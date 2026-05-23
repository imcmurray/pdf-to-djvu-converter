import type { StepProgress as Step } from "../hooks/useConvert";

// Stage labels — friendly names + ordering so we can render a step-list.
const STAGE_LABELS: Record<string, string> = {
  preflight: "Preparing",
  ocr: "Running OCR",
  ocr_done: "OCR finished",
  render: "Rendering pages",
  encode: "Encoding pages",
  assemble: "Assembling DjVu",
  textlayer: "Embedding text layer",
  convert: "Converting",
};

const ORDER = [
  "preflight", "ocr", "ocr_done", "render", "encode", "assemble", "textlayer", "convert", "done",
];

interface Props {
  step: Step | null;
  history: Step[];
}

export function StepProgress({ step, history }: Props) {
  // Unique stages seen in the history, plus the current step.
  const seen = new Set(history.map((s) => s.stage));
  if (step) seen.add(step.stage);
  const stages = ORDER.filter((s) => seen.has(s));

  if (!step && stages.length === 0) {
    return null;
  }

  const pct =
    step?.current != null && step?.total != null && step.total > 0
      ? Math.round((step.current / step.total) * 100)
      : null;

  return (
    <div className="space-y-3">
      {/* Active row */}
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-brand-500 animate-pulse" />
          <span className="font-medium truncate">
            {step ? STAGE_LABELS[step.stage] ?? step.stage : "Starting…"}
          </span>
          {step?.codec && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {step.codec}
            </span>
          )}
        </div>
        <div className="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
          {step?.current != null && step?.total != null
            ? `${step.current} / ${step.total}`
            : "working…"}
        </div>
      </div>

      {/* Bar — % when we know it, indeterminate shimmer when we don't. */}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        {pct != null ? (
          <div
            className="h-full rounded-full bg-brand-500 transition-[width] duration-200"
            style={{ width: `${pct}%` }}
          />
        ) : (
          <div className="h-full w-1/3 animate-[shimmer_1.2s_ease-in-out_infinite] rounded-full bg-brand-500" />
        )}
      </div>

      {/* Friendly text + a tiny stage-list breadcrumb */}
      {step?.message && (
        <p className="text-xs text-slate-500 dark:text-slate-400">{step.message}</p>
      )}
      {stages.length > 1 && (
        <div className="flex flex-wrap items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
          {stages.map((s, i) => (
            <span key={s} className="flex items-center gap-1">
              <span
                className={
                  s === step?.stage
                    ? "rounded bg-brand-100 px-1.5 py-0.5 font-medium text-brand-800 dark:bg-brand-900/40 dark:text-brand-200"
                    : "rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                }
              >
                {STAGE_LABELS[s] ?? s}
              </span>
              {i < stages.length - 1 && <span className="text-slate-300 dark:text-slate-600">→</span>}
            </span>
          ))}
        </div>
      )}

      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-50%); }
          100% { transform: translateX(250%); }
        }
      `}</style>
    </div>
  );
}

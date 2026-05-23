interface Props {
  inspection: {
    pages: number;
    bytes_per_page: number;
    text_chars_per_page: number;
    reason: string;
  };
  onConfirm: () => void;
  onCancel: () => void;
}

export function BornDigitalModal({ inspection, onConfirm, onCancel }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-lg space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200">
            ⚠
          </div>
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">This PDF looks born-digital</h2>
            <p className="text-sm text-slate-700 dark:text-slate-300">
              The file looks like it was created from vector text (a word
              processor or LaTeX), not from a scanned image. DjVu wins on
              scans; on born-digital PDFs it almost always{" "}
              <strong>increases</strong> file size and loses crisp vector glyphs.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
          <Stat label="Pages" value={String(inspection.pages)} />
          <Stat label="Avg KB / page" value={(inspection.bytes_per_page / 1024).toFixed(1)} />
          <Stat label="Chars / page" value={Math.round(inspection.text_chars_per_page).toString()} />
        </div>

        {inspection.reason && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            <span className="font-medium">Why:</span> {inspection.reason}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={onConfirm}>
            Convert anyway
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-0.5 font-semibold tabular-nums">{value}</div>
    </div>
  );
}

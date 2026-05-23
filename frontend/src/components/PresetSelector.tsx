import type { Preset } from "../api/client";

interface Props {
  value: Preset;
  onChange: (p: Preset) => void;
  ocr: boolean;
  onOcrChange: (v: boolean) => void;
  disabled?: boolean;
}

const PRESETS: { id: Preset; label: string; sub: string }[] = [
  { id: "fast", label: "Fast", sub: "Lower DPI · quick" },
  { id: "balanced", label: "Balanced", sub: "Default · recommended" },
  { id: "high-quality", label: "High quality", sub: "600 DPI · lossless JBIG2" },
  { id: "max-compression", label: "Max compression", sub: "Smallest file" },
];

export function PresetSelector({ value, onChange, ocr, onOcrChange, disabled }: Props) {
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Quality preset</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PRESETS.map((p) => {
            const active = value === p.id;
            return (
              <button
                key={p.id}
                type="button"
                disabled={disabled}
                onClick={() => onChange(p.id)}
                className={[
                  "rounded-lg border p-3 text-left transition-colors",
                  active
                    ? "border-brand-500 bg-brand-50 dark:bg-brand-900/30"
                    : "border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600",
                  disabled ? "opacity-50 cursor-not-allowed" : "",
                ].join(" ")}
              >
                <div className="text-sm font-medium">{p.label}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">{p.sub}</div>
              </button>
            );
          })}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ocr}
          onChange={(e) => onOcrChange(e.target.checked)}
          disabled={disabled}
          className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        />
        <span>Run OCR before conversion (adds a searchable text layer)</span>
      </label>
    </div>
  );
}

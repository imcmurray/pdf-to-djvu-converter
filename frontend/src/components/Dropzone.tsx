import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
  maxMB?: number;
}

export function Dropzone({ onFile, disabled, maxMB = 100 }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handle = useCallback(
    (f: File | undefined) => {
      setError(null);
      if (!f) return;
      if (!f.name.toLowerCase().endsWith(".pdf") && f.type !== "application/pdf") {
        setError("Please choose a PDF file.");
        return;
      }
      if (f.size > maxMB * 1024 * 1024) {
        setError(`File is too large. Maximum is ${maxMB} MB.`);
        return;
      }
      onFile(f);
    },
    [maxMB, onFile],
  );

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (disabled) return;
          handle(e.dataTransfer.files?.[0]);
        }}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        aria-disabled={disabled}
        className={[
          "relative grid place-items-center rounded-2xl border-2 border-dashed p-12 text-center transition-colors cursor-pointer",
          disabled ? "opacity-50 cursor-not-allowed" : "hover:border-brand-500",
          over
            ? "border-brand-500 bg-brand-50/50 dark:bg-brand-900/20"
            : "border-slate-300 dark:border-slate-700",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => handle(e.target.files?.[0] ?? undefined)}
        />
        <div className="flex flex-col items-center gap-3">
          <div className="grid h-14 w-14 place-items-center rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" />
            </svg>
          </div>
          <div>
            <p className="text-base font-medium">
              Drop a PDF here, or <span className="text-brand-600 dark:text-brand-400">browse</span>
            </p>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Up to {maxMB} MB · single file
            </p>
          </div>
        </div>
      </div>
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

import { useState } from "react";
import { compareOnly, type CompareResult, type Preset } from "../api/client";

interface Props {
  file: File;
  preset: Preset;
  ocr: boolean;
}

export function ShareLink({ file, preset, ocr }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setCopied(false);
    try {
      const meta = await compareOnly(file, { preset, ocr });
      setResult(meta);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (!result?.share_url) return;
    await navigator.clipboard.writeText(result.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (result?.share_url) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <input
          readOnly
          value={result.share_url}
          className="flex-1 min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-mono dark:border-slate-700 dark:bg-slate-900"
          onClick={(e) => (e.target as HTMLInputElement).select()}
        />
        <button type="button" onClick={copy} className="btn-secondary">
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={handleGenerate}
        disabled={loading}
        className="btn-secondary"
      >
        {loading ? "Generating…" : "Generate share link"}
      </button>
      {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
    </div>
  );
}

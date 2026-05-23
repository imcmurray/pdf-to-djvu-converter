import type { CompareResult } from "../api/client";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

interface Props {
  meta: CompareResult;
}

export function ConversionStats({ meta }: Props) {
  const stats = [
    { label: "PDF size", value: formatBytes(meta.pdf_bytes) },
    { label: "DjVu size", value: formatBytes(meta.djvu_bytes) },
    { label: "Compression", value: `${meta.compression_ratio.toFixed(2)}×` },
    { label: "Size reduction", value: `${meta.size_reduction_pct.toFixed(1)}%` },
    { label: "Pages", value: String(meta.pages) },
    { label: "Time", value: formatDuration(meta.duration_ms) },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {stats.map((s) => (
        <div key={s.label} className="stat">
          <div className="stat-label">{s.label}</div>
          <div className="stat-value">{s.value}</div>
        </div>
      ))}
    </div>
  );
}

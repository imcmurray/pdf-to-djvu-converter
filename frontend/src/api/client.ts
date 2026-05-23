// Typed client for the FastAPI backend.
// In dev, /api is proxied by Vite. In prod (Docker), /api is proxied by nginx.

export type Preset = "fast" | "balanced" | "high-quality" | "max-compression";

export interface CompareResult {
  pdf_bytes: number;
  djvu_bytes: number;
  compression_ratio: number;
  size_reduction_pct: number;
  pages: number;
  preset: Preset;
  ocr: boolean;
  duration_ms: number;
  share_url?: string | null;
}

export interface ProgressEvent {
  stage: string;
  message?: string;
  current?: number;
  total?: number;
  codec?: string;
  engine?: string;
  pages?: number;
  // Final-event fields:
  share_token?: string;
  filename?: string;
  result?: CompareResult;
  ocr_engine?: string | null;
  // Error-event fields:
  error?: string;
}

export interface ConvertOptions {
  preset?: Preset;
  ocr?: boolean;
  forceBornDigital?: boolean;
  onUploadProgress?: (uploadedPct: number) => void;
  onStageEvent?: (event: ProgressEvent) => void;
  signal?: AbortSignal;
}

/** Thrown by convertPdf when the server returns 409 BORN_DIGITAL_PDF. */
export class BornDigitalError extends Error {
  inspection: {
    pages: number;
    bytes_per_page: number;
    text_chars_per_page: number;
    reason: string;
  };
  constructor(message: string, inspection: BornDigitalError["inspection"]) {
    super(message);
    this.name = "BornDigitalError";
    this.inspection = inspection;
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

function url(path: string): string {
  if (API_BASE) return `${API_BASE.replace(/\/$/, "")}${path}`;
  return path;
}

/**
 * Convert a single PDF and return both the binary blob and the metadata
 * embedded in the response headers. Uses XHR so we can track upload progress.
 */
export interface ConvertResponse {
  blob: Blob;
  meta: CompareResult;
  filename: string;
  shareToken: string;
}

/**
 * Convert a PDF, streaming server progress events through `onStageEvent`.
 *
 * Throws `BornDigitalError` if the server's gate fires (409). The caller
 * should show a confirmation modal and, on user accept, retry with
 * `forceBornDigital: true`.
 */
export async function convertPdf(
  file: File,
  opts: ConvertOptions = {},
): Promise<ConvertResponse> {
  const {
    preset = "balanced",
    ocr = false,
    forceBornDigital = false,
    onStageEvent,
    signal,
  } = opts;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("preset", preset);
  fd.append("ocr", String(ocr));
  fd.append("force_born_digital", String(forceBornDigital));

  const res = await fetch(url("/api/convert"), {
    method: "POST",
    body: fd,
    signal,
  });

  if (res.status === 409) {
    let detail: any;
    try {
      detail = (await res.json()).detail;
    } catch {
      throw new Error("Server returned 409 with no detail");
    }
    if (detail?.code === "BORN_DIGITAL_PDF") {
      throw new BornDigitalError(detail.message ?? "Born-digital PDF", detail.inspection);
    }
    throw new Error(detail?.message ?? "HTTP 409");
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || body.message || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }

  if (!res.body) {
    throw new Error("Server response had no body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalEvent: ProgressEvent | null = null;
  let errorEvent: ProgressEvent | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      let event: ProgressEvent;
      try {
        event = JSON.parse(line) as ProgressEvent;
      } catch {
        continue;
      }
      if (event.stage === "done") finalEvent = event;
      else if (event.stage === "error") errorEvent = event;
      onStageEvent?.(event);
    }
  }

  if (errorEvent) throw new Error(errorEvent.error ?? "Conversion failed");
  if (!finalEvent?.share_token || !finalEvent.result) {
    throw new Error("Server stream ended without a final 'done' event");
  }

  // Fetch the actual DjVu bytes via the share-token endpoint.
  const downloadRes = await fetch(url(`/api/download/${finalEvent.share_token}`));
  if (!downloadRes.ok) {
    throw new Error(`Failed to fetch converted file: HTTP ${downloadRes.status}`);
  }
  const blob = await downloadRes.blob();

  return {
    blob,
    meta: finalEvent.result,
    filename: finalEvent.filename ?? `${file.name.replace(/\.pdf$/i, "")}.djvu`,
    shareToken: finalEvent.share_token,
  };
}

/** Convert a single PDF and return metadata + a share URL (no file body in response). */
export async function compareOnly(file: File, opts: ConvertOptions = {}): Promise<CompareResult> {
  const { preset = "balanced", ocr = false } = opts;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("preset", preset);
  fd.append("ocr", String(ocr));
  fd.append("share", "true");

  const res = await fetch(url("/api/compare"), { method: "POST", body: fd });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as CompareResult;
}

/** Build the URL for a server-rendered PNG of a single DjVu page. */
export function previewPageUrl(token: string, page: number, width = 900): string {
  return url(`/api/preview/${encodeURIComponent(token)}/page/${page}.png?width=${width}`);
}

/** Fetch the number of pages in a stored DjVu. */
export async function previewPageCount(token: string): Promise<number> {
  const res = await fetch(url(`/api/preview/${encodeURIComponent(token)}/page-count`));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as { pages: number };
  return data.pages;
}

/** True if the stored conversion includes an OCR text layer. */
export async function previewHasText(token: string): Promise<boolean> {
  const res = await fetch(url(`/api/preview/${encodeURIComponent(token)}/has-text`));
  if (!res.ok) return false;
  const data = (await res.json()) as { has_text: boolean };
  return data.has_text;
}

export interface HealthInfo {
  status: string;
  version: string;
  pdf2djvu_available: boolean;
  djvudigital_available: boolean;
  img2djvu_available: boolean;
  ocrmypdf_available: boolean;
  active_converter: string | null;
  available_converters: string[];
  ocr_engine_preference: string;
  ocr_engine_active: string;
  easyocr_available: boolean;
  gpu_available: boolean;
  gpu_info: string | null;
}

export async function fetchHealth(): Promise<HealthInfo> {
  const res = await fetch(url(`/api/health`));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as HealthInfo;
}

/** Fetch the OCR-extracted text for a single page. */
export async function previewPageText(token: string, page: number): Promise<string> {
  const res = await fetch(
    url(`/api/preview/${encodeURIComponent(token)}/page/${page}/text`),
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as { text: string };
  return data.text;
}

/** Convert several PDFs in a single request. */
export async function convertBatch(
  files: File[],
  opts: ConvertOptions = {},
): Promise<{ filename: string; success: boolean; error?: string; result?: CompareResult }[]> {
  const { preset = "balanced", ocr = false } = opts;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("preset", preset);
  fd.append("ocr", String(ocr));

  const res = await fetch(url("/api/convert/batch"), { method: "POST", body: fd });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.items;
}

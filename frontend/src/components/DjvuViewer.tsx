import { useEffect, useState } from "react";
import {
  previewHasText,
  previewPageCount,
  previewPageText,
  previewPageUrl,
} from "../api/client";

interface Props {
  shareToken: string | null;
  pagesHint?: number;
}

type Mode = "image" | "text";

export function DjvuViewer({ shareToken, pagesHint }: Props) {
  const [pageIdx, setPageIdx] = useState(1);
  const [pageCount, setPageCount] = useState(pagesHint && pagesHint > 0 ? pagesHint : 1);
  const [imgError, setImgError] = useState<string | null>(null);
  const [imgLoading, setImgLoading] = useState(false);
  const [mode, setMode] = useState<Mode>("image");

  const [hasText, setHasText] = useState(false);
  const [text, setText] = useState<string>("");
  const [textLoading, setTextLoading] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);

  // Page count + text availability — fetched once per token.
  useEffect(() => {
    if (!shareToken) return;
    let cancelled = false;
    previewPageCount(shareToken)
      .then((n) => !cancelled && setPageCount(Math.max(1, n)))
      .catch(() => {});
    previewHasText(shareToken)
      .then((v) => !cancelled && setHasText(v))
      .catch(() => !cancelled && setHasText(false));
    return () => {
      cancelled = true;
    };
  }, [shareToken]);

  // Fetch text whenever we're in text mode and the page changes.
  useEffect(() => {
    if (!shareToken || mode !== "text" || !hasText) return;
    let cancelled = false;
    setTextLoading(true);
    setTextError(null);
    previewPageText(shareToken, pageIdx)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch((e) => {
        if (!cancelled) setTextError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setTextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shareToken, pageIdx, mode, hasText]);

  if (!shareToken) {
    return (
      <div className="flex h-[70vh] items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        DjVu preview unavailable: missing share token from the server response.
      </div>
    );
  }

  const src = previewPageUrl(shareToken, pageIdx, 1200);

  return (
    <div className="flex h-[70vh] flex-col rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
      {/* Header: page nav + image/text tabs */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
        <div className="flex items-center gap-1">
          <span className="font-medium">Converted DjVu</span>
          {hasText && (
            <div className="ml-2 inline-flex overflow-hidden rounded-md border border-slate-300 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setMode("image")}
                className={`px-2 py-0.5 text-xs ${
                  mode === "image"
                    ? "bg-brand-600 text-white"
                    : "bg-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                Image
              </button>
              <button
                type="button"
                onClick={() => setMode("text")}
                className={`px-2 py-0.5 text-xs ${
                  mode === "text"
                    ? "bg-brand-600 text-white"
                    : "bg-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                OCR text
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            disabled={pageIdx <= 1 || imgLoading}
            onClick={() => setPageIdx((p) => Math.max(1, p - 1))}
          >
            ←
          </button>
          <span className="tabular-nums text-slate-600 dark:text-slate-300">
            {pageIdx} / {pageCount}
          </span>
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            disabled={pageIdx >= pageCount || imgLoading}
            onClick={() => setPageIdx((p) => Math.min(pageCount, p + 1))}
          >
            →
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-3">
        {mode === "image" ? (
          imgError ? (
            <div className="text-sm text-red-600 dark:text-red-400">
              DjVu preview unavailable: {imgError}
            </div>
          ) : (
            <img
              key={src}
              src={src}
              alt={`DjVu page ${pageIdx}`}
              className="mx-auto max-w-full bg-white shadow-sm dark:bg-slate-100"
              onLoadStart={() => {
                setImgLoading(true);
                setImgError(null);
              }}
              onLoad={() => setImgLoading(false)}
              onError={() => {
                setImgLoading(false);
                setImgError("server-side page render failed");
              }}
            />
          )
        ) : textLoading ? (
          <div className="text-sm text-slate-500 dark:text-slate-400">Loading OCR text…</div>
        ) : textError ? (
          <div className="text-sm text-red-600 dark:text-red-400">
            Couldn't load OCR text: {textError}
          </div>
        ) : text.trim() === "" ? (
          <div className="text-sm italic text-slate-500 dark:text-slate-400">
            (This page has no recognised text.)
          </div>
        ) : (
          <pre className="whitespace-pre-wrap break-words rounded bg-white p-3 font-mono text-xs leading-relaxed text-slate-800 shadow-sm dark:bg-slate-950 dark:text-slate-200">
            {text}
          </pre>
        )}
      </div>
    </div>
  );
}

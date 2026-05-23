import { useCallback, useRef, useState } from "react";
import {
  BornDigitalError,
  convertPdf,
  type CompareResult,
  type Preset,
  type ProgressEvent,
} from "../api/client";

type Stage = "idle" | "uploading" | "running" | "done" | "error" | "needs_confirm";

export interface StepProgress {
  stage: string;
  message: string;
  current?: number;
  total?: number;
}

export interface ConvertState {
  stage: Stage;
  step: StepProgress | null;
  history: StepProgress[];
  error: string | null;
  bornDigital: {
    pages: number;
    bytes_per_page: number;
    text_chars_per_page: number;
    reason: string;
  } | null;
  result: {
    file: File;
    djvuBlob: Blob;
    djvuUrl: string;
    pdfUrl: string;
    meta: CompareResult;
    filename: string;
    shareToken: string;
  } | null;
}

const initial: ConvertState = {
  stage: "idle",
  step: null,
  history: [],
  error: null,
  bornDigital: null,
  result: null,
};

export function useConvert() {
  const [state, setState] = useState<ConvertState>(initial);

  const abortRef = useRef<AbortController | null>(null);
  // The file that triggered the last attempt — needed for the "convert anyway" retry path.
  const pendingFileRef = useRef<{ file: File; preset: Preset; ocr: boolean } | null>(null);

  const handleEvent = useCallback((event: ProgressEvent) => {
    if (event.stage === "done" || event.stage === "error") return; // handled by promise
    const step: StepProgress = {
      stage: event.stage,
      message: event.message ?? event.stage,
      current: event.current,
      total: event.total,
    };
    setState((s) => ({
      ...s,
      step,
      history: [...s.history, step].slice(-200), // keep last 200 events to bound memory
    }));
  }, []);

  const run = useCallback(
    async (file: File, preset: Preset, ocr: boolean, forceBornDigital: boolean) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      pendingFileRef.current = { file, preset, ocr };

      setState({
        ...initial,
        stage: "running",
      });

      try {
        const { blob, meta, filename, shareToken } = await convertPdf(file, {
          preset, ocr, forceBornDigital, signal: ac.signal,
          onStageEvent: handleEvent,
        });
        const djvuUrl = URL.createObjectURL(blob);
        const pdfUrl = URL.createObjectURL(file);
        setState((s) => ({
          ...s,
          stage: "done",
          step: null,
          result: { file, djvuBlob: blob, djvuUrl, pdfUrl, meta, filename, shareToken },
        }));
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          setState(initial);
          return;
        }
        if (e instanceof BornDigitalError) {
          setState((s) => ({
            ...s,
            stage: "needs_confirm",
            bornDigital: e.inspection,
            error: null,
          }));
          return;
        }
        setState((s) => ({
          ...s,
          stage: "error",
          error: (e as Error).message || "Conversion failed",
        }));
      }
    },
    [handleEvent],
  );

  const start = useCallback(
    (file: File, preset: Preset, ocr: boolean) => run(file, preset, ocr, false),
    [run],
  );

  /** Resubmit the last upload with the born-digital gate overridden. */
  const confirmBornDigital = useCallback(() => {
    const p = pendingFileRef.current;
    if (!p) return;
    run(p.file, p.preset, p.ocr, true);
  }, [run]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => {
      if (s.result) {
        URL.revokeObjectURL(s.result.djvuUrl);
        URL.revokeObjectURL(s.result.pdfUrl);
      }
      return initial;
    });
  }, []);

  return { state, start, confirmBornDigital, reset };
}

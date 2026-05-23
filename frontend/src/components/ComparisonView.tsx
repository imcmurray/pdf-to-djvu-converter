import { PdfViewer } from "./PdfViewer";
import { DjvuViewer } from "./DjvuViewer";

interface Props {
  pdfUrl: string;
  shareToken: string | null;
  pagesHint?: number;
}

export function ComparisonView({ pdfUrl, shareToken, pagesHint }: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Original (PDF)
        </h3>
        <PdfViewer url={pdfUrl} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Converted (DjVu)
        </h3>
        <DjvuViewer shareToken={shareToken} pagesHint={pagesHint} />
      </div>
    </div>
  );
}

interface Props {
  url: string;
  title?: string;
}

/**
 * Embeds the original PDF using the browser's native viewer.
 * Modern browsers (Chrome, Edge, Firefox, Safari) ship a PDF renderer for iframes.
 */
export function PdfViewer({ url, title = "Original PDF" }: Props) {
  return (
    <div className="h-[70vh] w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
      <iframe
        title={title}
        src={`${url}#view=FitH`}
        className="h-full w-full"
        style={{ border: 0 }}
      />
    </div>
  );
}

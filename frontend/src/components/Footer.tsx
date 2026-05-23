export function Footer() {
  return (
    <footer className="mt-16 border-t border-slate-200 dark:border-slate-800">
      <div className="mx-auto max-w-6xl px-6 py-6 text-sm text-slate-500 dark:text-slate-400 flex flex-wrap items-center justify-between gap-2">
        <span>
          MIT licensed. Conversion powered by{" "}
          <a className="link" href="https://jwilk.net/software/pdf2djvu" target="_blank" rel="noreferrer">
            pdf2djvu
          </a>{" "}
          &amp;{" "}
          <a className="link" href="https://djvu.sourceforge.net/" target="_blank" rel="noreferrer">
            djvulibre
          </a>
          .
        </span>
        <span>
          <a className="link" href="/api/docs" target="_blank" rel="noreferrer">
            API docs
          </a>
        </span>
      </div>
    </footer>
  );
}

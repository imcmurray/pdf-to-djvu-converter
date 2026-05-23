export function About() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-10 space-y-10">
      <header className="space-y-3">
        <p className="text-sm font-medium uppercase tracking-wider text-brand-600 dark:text-brand-400">
          Format primer
        </p>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">What is DjVu?</h1>
        <p className="text-lg text-slate-600 dark:text-slate-300">
          DjVu (pronounced <em>déjà vu</em>) is an open document format designed in the late 1990s at
          AT&amp;T Labs specifically for compressing scanned documents — books, journals, manuscripts,
          newspapers — at a fraction of the size PDF can achieve, without sacrificing legibility.
        </p>
      </header>

      {/* History */}
      <section className="card space-y-3">
        <h2 className="text-xl font-semibold">A short history</h2>
        <p className="text-slate-700 dark:text-slate-300">
          DjVu was developed by Yann LeCun, Léon Bottou, Patrick Haffner, and Paul Howard at AT&amp;T
          Labs around 1996. It was open-sourced as <code>djvulibre</code> in 2000 and has since
          become the de-facto archival format at the Internet Archive and many digital libraries.
          PDF — born at Adobe in 1993 — was designed to faithfully reproduce <em>any</em> printable
          document; DjVu narrows its focus to <strong>scanned imagery</strong> and excels there.
        </p>
      </section>

      {/* How it works */}
      <section className="card space-y-4">
        <h2 className="text-xl font-semibold">How DjVu compresses scans</h2>
        <p className="text-slate-700 dark:text-slate-300">
          DjVu separates every scanned page into three layers and compresses each one with a codec
          tuned to its content:
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Layer
            color="bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
            title="Foreground mask"
            body="Black-and-white text and line-art, compressed with JB2 (a JBIG2-like algorithm that finds and dedupes repeated character shapes)."
          />
          <Layer
            color="bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200"
            title="Foreground colour"
            body="Low-resolution colour of the foreground pixels (e.g. red headings), stored at ~25 DPI with IW44 wavelet compression."
          />
          <Layer
            color="bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200"
            title="Background"
            body="The smooth page background (paper texture, photos) at a lower resolution with IW44 wavelet compression."
          />
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          PDF, by contrast, stores scanned pages as JPEG, JBIG2, or JPEG 2000 images — each treated
          as a single layer. DjVu's three-layer model is what lets it stay sharp on text while
          compressing photo regions aggressively.
        </p>
      </section>

      {/* Comparison */}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">PDF vs DjVu at a glance</h2>
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left dark:bg-slate-800/60">
              <tr>
                <th className="px-4 py-3 font-medium">Trait</th>
                <th className="px-4 py-3 font-medium">PDF</th>
                <th className="px-4 py-3 font-medium">DjVu</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              <Row trait="Best for" pdf="Born-digital docs, forms, vector art" djvu="Scanned books, archives, photo-heavy pages" />
              <Row trait="Compression of scans" pdf="Good" djvu="Typically 5–10× better" />
              <Row trait="Vector graphics" pdf="Yes (native)" djvu="Limited — raster-oriented" />
              <Row trait="Searchable text layer" pdf="Yes (via OCR)" djvu="Yes (preserved through pdf2djvu)" />
              <Row trait="Browser support" pdf="Native everywhere" djvu="Plugin or djvu.js" />
              <Row trait="Hyperlinks / forms" pdf="Yes (rich)" djvu="Basic hyperlinks only" />
              <Row trait="Open standard" pdf="ISO 32000" djvu="Open spec; djvulibre is GPL" />
              <Row trait="Typical file size (300 dpi book)" pdf="~150–400 KB / page" djvu="~30–60 KB / page" />
            </tbody>
          </table>
        </div>
      </section>

      {/* Pros / cons */}
      <section className="grid gap-4 sm:grid-cols-2">
        <div className="card">
          <h3 className="font-semibold text-emerald-700 dark:text-emerald-300">
            Where DjVu wins
          </h3>
          <ul className="mt-2 space-y-1.5 text-sm text-slate-700 dark:text-slate-300 list-disc pl-5">
            <li>Massive size savings on scanned text-heavy material.</li>
            <li>Crisp rendering of small text even at low file sizes.</li>
            <li>Faster page loads in archival viewers (smaller bytes over the wire).</li>
            <li>Free, open-source ecosystem (djvulibre, pdf2djvu).</li>
          </ul>
        </div>
        <div className="card">
          <h3 className="font-semibold text-rose-700 dark:text-rose-300">
            Where PDF wins
          </h3>
          <ul className="mt-2 space-y-1.5 text-sm text-slate-700 dark:text-slate-300 list-disc pl-5">
            <li>Universal native viewer support — every OS, every browser, every device.</li>
            <li>Better for vector graphics, presentations, and editable documents.</li>
            <li>Rich features: forms, signatures, annotations, JavaScript, embedded media.</li>
            <li>Wider toolchain (Acrobat, Foxit, Preview, etc.).</li>
          </ul>
        </div>
      </section>

      {/* When to convert */}
      <section className="card space-y-3">
        <h2 className="text-xl font-semibold">Should I convert this PDF?</h2>
        <p className="text-slate-700 dark:text-slate-300">
          Convert <strong>yes</strong> when:
        </p>
        <ul className="list-disc pl-5 text-sm text-slate-700 dark:text-slate-300 space-y-1">
          <li>It's a scanned book, journal, or document set.</li>
          <li>You're archiving for long-term storage or distribution.</li>
          <li>You need to host pages on bandwidth-constrained infrastructure.</li>
        </ul>
        <p className="text-slate-700 dark:text-slate-300">
          Stick with PDF when:
        </p>
        <ul className="list-disc pl-5 text-sm text-slate-700 dark:text-slate-300 space-y-1">
          <li>It's a born-digital document with crisp vector text/graphics.</li>
          <li>End-users need to open it without extra software.</li>
          <li>It contains fillable forms, signatures, or rich annotations.</li>
        </ul>
      </section>

      <section className="text-sm text-slate-500 dark:text-slate-400 space-y-1">
        <p>
          Further reading: the original{" "}
          <a className="link" href="https://djvu.sourceforge.net/" target="_blank" rel="noreferrer">
            djvu.sourceforge.net
          </a>
          , Internet Archive's{" "}
          <a className="link" href="https://archive.org/details/texts" target="_blank" rel="noreferrer">
            DjVu collections
          </a>
          , and{" "}
          <a className="link" href="https://jwilk.net/software/pdf2djvu" target="_blank" rel="noreferrer">
            pdf2djvu
          </a>{" "}
          (the converter under the hood).
        </p>
      </section>
    </div>
  );
}

function Row({ trait, pdf, djvu }: { trait: string; pdf: string; djvu: string }) {
  return (
    <tr>
      <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">{trait}</td>
      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{pdf}</td>
      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{djvu}</td>
    </tr>
  );
}

function Layer({ color, title, body }: { color: string; title: string; body: string }) {
  return (
    <div className={`rounded-lg p-4 ${color}`}>
      <div className="font-semibold">{title}</div>
      <p className="mt-1 text-sm">{body}</p>
    </div>
  );
}

import { Link, NavLink } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";

export function Navbar() {
  const { theme, toggle } = useTheme();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? "bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200"
        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
    }`;

  return (
    <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80 sticky top-0 z-30">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white font-bold">
            DJ
          </div>
          <span className="text-lg font-semibold tracking-tight">PDF → DjVu</span>
        </Link>

        <nav className="flex items-center gap-1">
          <NavLink to="/" end className={linkClass}>
            Convert
          </NavLink>
          <NavLink to="/about" className={linkClass}>
            What is DjVu?
          </NavLink>
          <NavLink to="/system" className={linkClass}>
            System
          </NavLink>
          <a
            href="/api/docs"
            className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            target="_blank"
            rel="noreferrer"
          >
            API
          </a>
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="ml-2 grid h-9 w-9 place-items-center rounded-md text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </nav>
      </div>
    </header>
  );
}

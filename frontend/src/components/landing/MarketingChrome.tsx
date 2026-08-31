import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { CONSOLE_PATHS } from "../../utils/format";
import { LandingCta } from "./primitives";

export const API_DOCS_URL = `${api.baseUrl}/docs`;

const NAV = [
  { href: "#product", label: "Product" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#engine", label: "Engine" },
  { href: "#evaluation", label: "Evaluation" },
  { href: "#developers", label: "Developers" },
];

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span
        className="flex h-7 w-7 items-center justify-center rounded-[5px] bg-[var(--marketing-fg)]"
        aria-hidden
      >
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
          <rect x="1" y="2" width="11" height="1.4" rx="0.5" fill="white" />
          <rect x="1" y="5.8" width="7.5" height="1.4" rx="0.5" fill="white" opacity="0.72" />
          <rect x="1" y="9.6" width="9.5" height="1.4" rx="0.5" fill="#06B6D4" />
        </svg>
      </span>
      <span className={compact ? "text-[14px] font-semibold tracking-tight" : "text-[15px] font-semibold tracking-tight"}>
        ReconEngine
      </span>
    </Link>
  );
}

export function MarketingHeader() {
  const header = (
    <header className="marketing-tokens fixed top-0 right-0 left-0 z-50 border-b border-[var(--marketing-border)] bg-[var(--marketing-bg)]/90 text-[var(--marketing-fg)] backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center justify-between gap-4 px-6">
        <Wordmark />

        <nav className="hidden items-center gap-5 md:flex lg:gap-7" aria-label="Marketing">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-[13px] font-medium text-[var(--marketing-muted)] transition hover:text-[var(--marketing-fg)]"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <LandingCta to={CONSOLE_PATHS.home} variant="dark" size="sm">
          Open Console
        </LandingCta>
      </div>
    </header>
  );

  if (typeof document === "undefined") return header;
  return createPortal(header, document.body);
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-[var(--marketing-border)] px-6 py-12">
      <div className="mx-auto flex max-w-[1120px] flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Wordmark compact />
          <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-[var(--marketing-muted)]">
            Deterministic financial reconciliation infrastructure.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-[var(--marketing-muted)]" aria-label="Footer">
          <a href="#product" className="hover:text-[var(--marketing-fg)]">
            Product
          </a>
          <Link to={CONSOLE_PATHS.home} className="hover:text-[var(--marketing-fg)]">
            Console
          </Link>
          <a href="#evaluation" className="hover:text-[var(--marketing-fg)]">
            Evaluation
          </a>
          <a href={API_DOCS_URL} target="_blank" rel="noreferrer" className="hover:text-[var(--marketing-fg)]">
            API Docs
          </a>
        </nav>
      </div>
    </footer>
  );
}

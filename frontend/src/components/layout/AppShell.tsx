import {
  ClipboardCheck,
  FileUp,
  LayoutGrid,
  Settings,
  ShieldAlert,
  Table2,
} from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useHealth } from "../../hooks/useApi";
import { cn, CONSOLE_PATHS, ROUTE_META } from "../../utils/format";
import { EngineStatus } from "../ui/primitives";

const navGroups = [
  {
    label: "Overview",
    items: [{ to: CONSOLE_PATHS.dashboard, label: "Command Center", icon: LayoutGrid }],
  },
  {
    label: "Operations",
    items: [
      { to: CONSOLE_PATHS.bankImport, label: "Bank Import", icon: FileUp },
      { to: CONSOLE_PATHS.reconciliation, label: "Reconciliation", icon: Table2 },
      { to: CONSOLE_PATHS.exceptions, label: "Exceptions", icon: ShieldAlert },
      { to: CONSOLE_PATHS.evaluation, label: "Evaluation", icon: ClipboardCheck },
    ],
  },
  {
    label: "System",
    items: [{ to: CONSOLE_PATHS.settings, label: "Settings", icon: Settings }],
  },
];

function ConsoleWordmark() {
  return (
    <Link
      to="/"
      className="flex items-center gap-2.5 rounded-md outline-offset-2"
      aria-label="ReconEngine home"
      data-testid="console-brand-link"
    >
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[5px] bg-[var(--color-ink)]"
        aria-hidden
      >
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
          <rect x="1" y="2" width="11" height="1.4" rx="0.5" fill="white" />
          <rect x="1" y="5.8" width="7.5" height="1.4" rx="0.5" fill="white" opacity="0.72" />
          <rect x="1" y="9.6" width="9.5" height="1.4" rx="0.5" fill="#06B6D4" />
        </svg>
      </span>
      <span className="min-w-0">
        <p className="text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">ReconEngine</p>
        <p className="text-[11px] text-[var(--color-muted)]">Financial Operations</p>
      </span>
    </Link>
  );
}

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const health = useHealth();

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-[var(--color-ink)]/25 transition-opacity duration-200 lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-svh w-[260px] shrink-0 flex-col border-r border-[var(--color-border)] bg-white transition-transform duration-300 ease-[var(--ease-out)] lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="px-5 pt-6 pb-5 lg:px-6 lg:pt-7">
          <ConsoleWordmark />
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto px-4">
          {navGroups.map((group) => (
            <div key={group.label}>
              <p className="mb-2 px-2 text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === CONSOLE_PATHS.dashboard}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors duration-150",
                        isActive
                          ? "bg-[var(--color-bg)] text-[var(--color-ink)] shadow-[0_1px_2px_rgba(11,27,43,0.04)]"
                          : "text-[var(--color-muted)] hover:bg-black/[0.025] hover:text-[var(--color-ink)]",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive ? (
                          <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-gradient-to-b from-[#2563EB] to-[#06B6D4]" />
                        ) : null}
                        <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                        {label}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-[var(--color-border)] px-6 py-5">
          <EngineStatus online={health.data?.status === "ok" && !health.error} />
          <p className="mt-1.5 text-[11px] text-[var(--color-muted)]">v1 · Deterministic</p>
        </div>
      </aside>
    </>
  );
}

/** Soft blue/cyan atmosphere behind console content — restrained landing continuation. */
export function ConsoleAtmosphere() {
  return (
    <div className="console-atmosphere" aria-hidden>
      <div className="console-atmosphere__glow console-atmosphere__glow--blue" />
      <div className="console-atmosphere__glow console-atmosphere__glow--cyan" />
      <div className="console-atmosphere__glow console-atmosphere__glow--center" />
    </div>
  );
}

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const location = useLocation();
  const meta = ROUTE_META[location.pathname] ?? ROUTE_META[CONSOLE_PATHS.dashboard];
  const health = useHealth();

  return (
    <header className="z-30 shrink-0 border-b border-[var(--color-border)] bg-white/85 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between gap-4 px-5 lg:px-10">
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-muted)] transition hover:border-[var(--color-accent)]/30 hover:text-[var(--color-ink)] lg:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
              {meta.group}
            </p>
            <h1 className="text-sm font-semibold tracking-tight text-[var(--color-ink)]">{meta.title}</h1>
          </div>
        </div>
        <div className="hidden items-center gap-6 md:flex">
          <p className="max-w-xs truncate text-[13px] text-[var(--color-muted)]">{meta.subtitle}</p>
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <EngineStatus online={health.data?.status === "ok" && !health.error} />
        </div>
      </div>
    </header>
  );
}

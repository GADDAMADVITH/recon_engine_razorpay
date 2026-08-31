import {
  Activity,
  ClipboardCheck,
  LayoutGrid,
  Settings,
  ShieldAlert,
  Table2,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
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
          "fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r border-[var(--color-border)] bg-[var(--color-bg)] transition-transform duration-300 ease-[var(--ease-out)] lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="px-6 pt-7 pb-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--color-ink)]">
              <Activity className="h-4 w-4 text-white" strokeWidth={2} />
            </div>
            <div>
              <p className="text-[15px] font-semibold tracking-tight">ReconEngine</p>
              <p className="text-[11px] text-[var(--color-muted)]">Financial Operations</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto px-4">
          {navGroups.map((group) => (
            <div key={group.label}>
              <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
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
                          ? "bg-white text-[var(--color-ink)] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                          : "text-[var(--color-muted)] hover:bg-black/[0.03] hover:text-[var(--color-ink)]",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive ? (
                          <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-[var(--color-accent)]" />
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

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const location = useLocation();
  const meta = ROUTE_META[location.pathname] ?? ROUTE_META[CONSOLE_PATHS.dashboard];
  const health = useHealth();

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--color-border)] bg-[var(--color-bg)]/90 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between gap-4 px-4 lg:px-8">
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-muted)] transition hover:border-black/20 hover:text-[var(--color-ink)] lg:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--color-muted)]">
              {meta.group}
            </p>
            <h1 className="text-sm font-semibold tracking-tight">{meta.title}</h1>
          </div>
        </div>
        <div className="hidden items-center gap-6 md:flex">
          <p className="max-w-xs truncate text-xs text-[var(--color-muted)]">{meta.subtitle}</p>
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <EngineStatus online={health.data?.status === "ok" && !health.error} />
        </div>
      </div>
    </header>
  );
}

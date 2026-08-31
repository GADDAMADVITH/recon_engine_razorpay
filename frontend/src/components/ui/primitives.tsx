import { ArrowRight, Check, RefreshCw } from "lucide-react";
import { cn, formatExceptionLabel, getExceptionSeverity } from "../../utils/format";

/* ── Layout ── */

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[2rem] font-semibold tracking-[-0.03em] text-[var(--color-ink)] sm:text-[2.25rem]">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[var(--color-muted)]">
            {subtitle}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

export function SectionLabel({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4 border-b border-[var(--color-border)] pb-4">
      <div>
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
          {title}
        </h2>
        {description ? (
          <p className="mt-1 text-sm text-[var(--color-muted)]">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function Divider() {
  return <hr className="border-0 border-t border-[var(--color-border)]" />;
}

/* ── Metrics ── */

export function DisplayMetric({
  value,
  label,
  hint,
  size = "lg",
}: {
  value: string;
  label: string;
  hint?: string;
  size?: "lg" | "md" | "sm";
}) {
  const sizes = {
    lg: "text-[3.5rem] leading-none tracking-[-0.04em]",
    md: "text-3xl tracking-[-0.03em]",
    sm: "text-xl tracking-[-0.02em]",
  };
  return (
    <div>
      <p className={cn("font-semibold tabular-nums text-[var(--color-ink)]", sizes[size])}>
        {value}
      </p>
      <p className="mt-2 text-sm font-medium text-[var(--color-muted)]">{label}</p>
      {hint ? <p className="mt-0.5 text-xs text-[var(--color-muted)]">{hint}</p> : null}
    </div>
  );
}

export function StatPill({
  value,
  label,
}: {
  value: string | number;
  label: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-lg font-semibold tabular-nums tracking-tight">{value}</span>
      <span className="text-xs text-[var(--color-muted)]">{label}</span>
    </div>
  );
}

/* ── Buttons ── */

export function Button({
  children,
  variant = "secondary",
  size = "md",
  className,
  icon,
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
}) {
  const variants = {
    primary:
      "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] active:scale-[0.98]",
    secondary:
      "border border-[var(--color-border)] bg-white text-[var(--color-ink)] hover:border-black/20 hover:bg-[var(--color-bg)] active:scale-[0.98]",
    ghost:
      "text-[var(--color-muted)] hover:text-[var(--color-ink)] hover:bg-black/[0.04] active:scale-[0.98]",
    danger:
      "border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10",
  };
  const sizes = {
    sm: "h-8 px-3 text-xs gap-1.5",
    md: "h-10 px-4 text-sm gap-2",
    lg: "h-11 px-5 text-sm gap-2",
  };
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center rounded-lg font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-40",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

export function PrimaryCTA({
  onClick,
  loading,
  success,
  label = "Run reconciliation",
}: {
  onClick?: () => void;
  loading?: boolean;
  success?: boolean;
  label?: string;
}) {
  const displayLabel = success ? "Reconciliation complete" : loading ? "Running reconciliation…" : label;

  return (
    <Button
      variant="primary"
      size="lg"
      onClick={onClick}
      disabled={loading}
      aria-busy={loading}
      aria-live="polite"
      icon={
        success ? (
          <Check className="h-4 w-4" />
        ) : (
          <RefreshCw className={cn("h-4 w-4", loading && "animate-[spin_1s_linear_infinite]")} />
        )
      }
    >
      {displayLabel}
      {!success && !loading ? <ArrowRight className="h-4 w-4" /> : null}
    </Button>
  );
}

/* ── Form controls ── */

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-muted)] transition-colors hover:border-black/20 focus:border-[var(--color-accent)] focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-ink)] transition-colors hover:border-black/20 focus:border-[var(--color-accent)] focus:outline-none",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

/* ── Status ── */

export function StatusBadge({
  status,
  reconciled,
}: {
  status: string;
  reconciled: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        reconciled
          ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
          : "bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: "critical" | "warning" | "info" }) {
  const styles = {
    critical: "bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
    warning: "bg-[var(--color-warning)]/10 text-[var(--color-warning)]",
    info: "bg-black/[0.05] text-[var(--color-muted)]",
  };
  const labels = { critical: "Critical", warning: "Warning", info: "Info" };
  return (
    <span className={cn("rounded-md px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide", styles[severity])}>
      {labels[severity]}
    </span>
  );
}

export function EngineStatus({ online }: { online: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          online ? "bg-[var(--color-success)]" : "bg-[var(--color-danger)]",
        )}
        aria-hidden
      />
      <span>{online ? "Engine online" : "Engine offline"}</span>
    </div>
  );
}

export function StatusDot({ status }: { status: "ok" | "warning" | "error" | "neutral" }) {
  const colors = {
    ok: "bg-[var(--color-success)]",
    warning: "bg-[var(--color-warning)]",
    error: "bg-[var(--color-danger)]",
    neutral: "bg-[var(--color-muted)]",
  };
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", colors[status])} />;
}

/* ── Interactive rows ── */

export function InteractiveRow({
  label,
  count,
  severity,
  onClick,
}: {
  label: string;
  count: number;
  severity?: "critical" | "warning" | "info";
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-4 border-b border-[var(--color-border)] py-4 text-left transition-colors last:border-b-0 hover:bg-black/[0.02] focus-visible:bg-black/[0.02]"
    >
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-medium text-[var(--color-ink)]">{label}</p>
      </div>
      {severity ? <SeverityBadge severity={severity} /> : null}
      <span className="w-8 text-right text-sm font-semibold tabular-nums">{count}</span>
      <ArrowRight className="h-4 w-4 text-[var(--color-muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--color-ink)]" />
    </button>
  );
}

/* ── Settings rows ── */

export function SettingRow({
  label,
  value,
  status,
}: {
  label: string;
  value: React.ReactNode;
  status?: "ok" | "warning" | "error" | "neutral";
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--color-border)] py-4 last:border-b-0">
      <dt className="text-sm text-[var(--color-muted)]">{label}</dt>
      <dd className="flex items-center gap-2 text-sm font-medium text-[var(--color-ink)]">
        {status ? <StatusDot status={status} /> : null}
        {value}
      </dd>
    </div>
  );
}

/* ── States ── */

export function LoadingState({ label = "Loading reconciliation data..." }: { label?: string }) {
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center">
      <div
        className="mb-4 h-5 w-5 animate-[spin_0.8s_linear_infinite] rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent)]"
        role="status"
        aria-label="Loading"
      />
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
      <p className="text-base font-medium text-[var(--color-ink)]">Unable to load data</p>
      <p className="mt-2 max-w-md text-sm text-[var(--color-muted)]">{message}</p>
      {onRetry ? (
        <Button variant="primary" className="mt-6" onClick={onRetry}>
          Retry connection
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="py-16 text-center">
      <p className="text-base font-medium">{title}</p>
      <p className="mt-2 text-sm text-[var(--color-muted)]">{description}</p>
    </div>
  );
}

/* ── Exception type badge helper ── */

export function ExceptionTypeBadge({ type }: { type: string }) {
  const severity = getExceptionSeverity(type);
  return (
    <span className="inline-flex items-center gap-2">
      <SeverityBadge severity={severity} />
      <span className="text-sm">{formatExceptionLabel(type)}</span>
    </span>
  );
}

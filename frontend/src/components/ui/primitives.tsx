import { ArrowRight, Check, RefreshCw } from "lucide-react";
import { cn, formatExceptionLabel, formatStatusLabel, getExceptionSeverity } from "../../utils/format";

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
        <h1 className="text-[2rem] font-medium tracking-[-0.045em] text-[var(--color-ink)] sm:text-[2.35rem]">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[var(--color-muted)] sm:text-[16px]">
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
        <h2 className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          {title}
        </h2>
        {description ? (
          <p className="mt-1.5 text-sm text-[var(--color-muted)]">{description}</p>
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

/**
 * An elevated metric card — used in stat summary rows on the Dashboard,
 * Reconciliation, and Bank Import pages.
 */
export function MetricCard({
  value,
  label,
  accent,
}: {
  value: string | number;
  label: string;
  accent?: "success" | "danger" | "warning" | "brand" | "default";
}) {
  const accentColors = {
    success: "text-[var(--color-success)]",
    danger: "text-[var(--color-danger)]",
    warning: "text-[var(--color-warning)]",
    brand: "text-[var(--color-accent-blue)]",
    default: "text-[var(--color-ink)]",
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_0_rgba(11,27,43,0.04),0_8px_24px_rgba(11,27,43,0.04)]">
      <span
        className={cn(
          "text-[2.35rem] font-medium leading-none tabular-nums tracking-[-0.045em]",
          accentColors[accent ?? "default"],
        )}
      >
        {value}
      </span>
      <span className="text-[13px] font-medium text-[var(--color-muted)]">{label}</span>
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
      "rounded-full bg-gradient-to-r from-[#2563EB] to-[#0891B2] text-white shadow-[0_8px_20px_rgba(37,99,235,0.28)] hover:shadow-[0_14px_32px_rgba(37,99,235,0.38)] hover:brightness-105 active:scale-[0.98]",
    secondary:
      "rounded-full border border-[var(--color-border)] bg-white text-[var(--color-ink)] hover:border-[var(--color-accent)]/30 hover:bg-white active:scale-[0.98]",
    ghost:
      "rounded-lg text-[var(--color-muted)] hover:text-[var(--color-ink)] hover:bg-black/[0.03] active:scale-[0.98]",
    danger:
      "rounded-full border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10",
  };
  const sizes = {
    sm: "h-8 px-3.5 text-xs gap-1.5",
    md: "h-10 px-4 text-sm gap-2",
    lg: "h-11 px-5 text-[15px] gap-2",
  };
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-40",
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
      className="rounded-full px-5 shadow-[0_8px_20px_rgba(37,99,235,0.28)] hover:shadow-[0_14px_32px_rgba(37,99,235,0.38)]"
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
  // Derive a two-tone style based on reconciliation outcome
  const isRefundAdjusted = status.includes("refund_adjustment");
  const bgColor = reconciled
    ? isRefundAdjusted
      ? "bg-[var(--color-warning)]/10 text-[var(--color-warning)]"
      : "bg-[var(--color-success)]/10 text-[var(--color-success)]"
    : "bg-[var(--color-danger)]/10 text-[var(--color-danger)]";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        bgColor,
      )}
    >
      {formatStatusLabel(status)}
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
    <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-medium", styles[severity])}>
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
    <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-[var(--color-border)] bg-white shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
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
    <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-[var(--color-danger)]/20 bg-white text-center shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
      <div className="mb-1 h-2 w-2 rounded-full bg-[var(--color-danger)]" aria-hidden />
      <p className="mt-3 text-base font-semibold text-[var(--color-ink)]">Unable to load data</p>
      <p className="mt-2 max-w-md px-6 text-sm text-[var(--color-muted)]">{message}</p>
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
    <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-white px-8 py-14 text-center">
      <p className="text-[15px] font-semibold text-[var(--color-ink)]">{title}</p>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-[var(--color-muted)]">{description}</p>
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

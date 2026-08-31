import { useMemo, useState } from "react";
import type { OrderResult, ReconciliationReport, ReconciliationSummary } from "../../types/api";
import { cn, formatPaise, formatPercent } from "../../utils/format";
import { LiveMetric } from "./primitives";

function WindowChrome({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-[var(--marketing-border)] bg-white px-4 py-2.5">
      <span className="h-2 w-2 rounded-full bg-black/10" />
      <span className="h-2 w-2 rounded-full bg-black/10" />
      <span className="h-2 w-2 rounded-full bg-black/10" />
      <span className="ml-2 truncate font-sans text-[11px] text-[var(--marketing-muted)]">{title}</span>
    </div>
  );
}

export function averageConfidence(orders: { confidence_score: number }[] | undefined): number | null {
  if (!orders?.length) return null;
  return Math.round(orders.reduce((sum, order) => sum + order.confidence_score, 0) / orders.length);
}

function StatusChip({ reconciled }: { reconciled: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium",
        reconciled
          ? "bg-[var(--marketing-success)]/10 text-[var(--marketing-success)]"
          : "bg-[var(--marketing-critical)]/10 text-[var(--marketing-critical)]",
      )}
    >
      {reconciled ? "Reconciled" : "Unreconciled"}
    </span>
  );
}

function Frame({
  title,
  children,
  label,
}: {
  title: string;
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <div
      className="overflow-hidden rounded-2xl border border-[var(--marketing-border)] bg-white shadow-[0_1px_0_rgba(11,27,43,0.04),0_24px_64px_rgba(37,99,235,0.12),0_16px_40px_rgba(11,27,43,0.08)] transition duration-300 md:hover:-translate-y-0.5 md:hover:border-[#2563EB]/20 md:hover:shadow-[0_28px_72px_rgba(37,99,235,0.16),0_16px_40px_rgba(11,27,43,0.08)]"
      role={label ? "img" : undefined}
      aria-label={label}
    >
      <WindowChrome title={title} />
      {children}
    </div>
  );
}

function RateBar({ value, loading }: { value: number | null; loading?: boolean }) {
  const width = value == null || loading ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-black/[0.06]" aria-hidden>
      <div
        className="h-full rounded-full bg-gradient-to-r from-[#2563EB] to-[#06B6D4] transition-[width] duration-700 ease-out"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

function MetricCell({
  label,
  value,
  loading,
  format,
  tone,
}: {
  label: string;
  value: number | null;
  loading?: boolean;
  format: (n: number) => string;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <p className={cn("text-[1.35rem] font-medium tabular-nums tracking-tight sm:text-[1.6rem]", tone)}>
        <LiveMetric value={value} loading={loading} format={format} />
      </p>
      <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--marketing-muted)]">
        {label}
      </p>
    </div>
  );
}

export function HeroPreview({
  summary,
  report,
  loading,
  error,
  live,
}: {
  summary: ReconciliationSummary | null;
  report: ReconciliationReport | null;
  loading: boolean;
  error: string | null;
  live: boolean;
}) {
  const rate = summary && summary.total_orders > 0 ? (summary.reconciled_orders / summary.total_orders) * 100 : null;
  const confidence = averageConfidence(report?.order_results);
  const rows = report?.order_results.slice(0, 5) ?? [];
  const label = summary
    ? `Live ReconEngine preview showing ${summary.total_orders} orders, ${summary.reconciled_orders} reconciled, ${summary.unreconciled_orders} unreconciled, ${formatPercent(summary.reconciled_orders / summary.total_orders)} reconciled`
    : "ReconEngine product preview";

  return (
    <Frame title="ReconEngine · Live run" label={label}>
      <div className="border-b border-[var(--marketing-border)] px-5 py-5 sm:px-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <p className="text-[12px] font-medium tracking-tight text-[var(--marketing-fg)]">Current run</p>
          <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--marketing-muted)]">
            {live ? "Live" : "Offline"}
          </span>
        </div>
        {error && !summary ? (
          <p className="text-sm text-[var(--marketing-muted)]">Live engine data unavailable.</p>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-5">
            <MetricCell
              label="Orders"
              value={summary?.total_orders ?? null}
              loading={loading && !summary}
              format={(n) => String(Math.round(n))}
            />
            <MetricCell
              label="Reconciled"
              value={summary?.reconciled_orders ?? null}
              loading={loading && !summary}
              format={(n) => String(Math.round(n))}
              tone="text-[var(--marketing-success)]"
            />
            <MetricCell
              label="Unreconciled"
              value={summary?.unreconciled_orders ?? null}
              loading={loading && !summary}
              format={(n) => String(Math.round(n))}
              tone="text-[var(--marketing-critical)]"
            />
            <MetricCell
              label="Reconciliation rate"
              value={rate}
              loading={loading && !summary}
              format={(n) => `${n.toFixed(1)}%`}
              tone="text-[#2563EB]"
            />
            <MetricCell
              label="Avg. confidence"
              value={confidence}
              loading={loading && !report}
              format={(n) => String(Math.round(n))}
            />
          </div>
        )}
        {error && !summary ? null : <RateBar value={rate} loading={loading && !summary} />}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-[var(--marketing-border)] text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--marketing-muted)]">
              <th className="px-5 py-2.5 font-medium sm:px-6">Order</th>
              <th className="px-5 py-2.5 font-medium sm:px-6">Status</th>
              <th className="px-5 py-2.5 font-medium sm:px-6">Confidence</th>
              <th className="px-5 py-2.5 font-medium sm:px-6">Settlement</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-[var(--marketing-muted)] sm:px-6">
                  {loading ? "Loading live orders…" : "Live table unavailable"}
                </td>
              </tr>
            ) : (
              rows.map((order) => (
                <tr key={order.order_id} className="border-b border-[var(--marketing-border)] last:border-0">
                  <td className="px-5 py-3 font-medium sm:px-6">{order.order_id}</td>
                  <td className="px-5 py-3 sm:px-6">
                    <StatusChip reconciled={order.reconciled} />
                  </td>
                  <td className="px-5 py-3 tabular-nums sm:px-6">{order.confidence_score}</td>
                  <td className="px-5 py-3 font-mono text-[11px] text-[var(--marketing-muted)] sm:px-6">
                    {order.primary_settlement_id ?? "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Frame>
  );
}

function Flag({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok == null) {
    return <span className="text-[12px] text-[var(--marketing-muted)]">{label}</span>;
  }
  return (
    <span className={ok ? "text-[12px] text-[var(--marketing-success)]" : "text-[12px] text-[var(--marketing-critical)]"}>
      {label}
    </span>
  );
}

function OrderDetail({ order }: { order: OrderResult }) {
  const amount = order.amount_comparison;
  const time = order.timestamp_comparison;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{order.order_id}</p>
          <p className="mt-1 text-[12px] text-[var(--marketing-muted)]">
            Confidence {order.confidence_score}
          </p>
        </div>
        <StatusChip reconciled={order.reconciled} />
      </div>

      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--marketing-muted)]">
          Amount comparison
        </p>
        <dl className="mt-2 space-y-1.5 text-[12px]">
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--marketing-muted)]">Order</dt>
            <dd className="tabular-nums">{formatPaise(amount.order_amount_paise)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--marketing-muted)]">Settlement</dt>
            <dd className="tabular-nums">
              {amount.settlement_gross_paise == null ? "—" : formatPaise(amount.settlement_gross_paise)}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--marketing-muted)]">Bank</dt>
            <dd className="tabular-nums">
              {amount.bank_amount_paise == null ? "—" : formatPaise(amount.bank_amount_paise)}
            </dd>
          </div>
        </dl>
        <p className="mt-2 flex flex-wrap gap-x-3">
          <Flag ok={amount.settlement_gross_matches_order} label="Settlement" />
          <Flag ok={amount.bank_matches_settlement_net} label="Bank" />
        </p>
      </div>

      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--marketing-muted)]">
          Timestamp comparison
        </p>
        <p className="mt-2 text-[12px] text-[var(--marketing-muted)]">
          Tolerance {time.tolerance_hours}h
          {time.difference_hours == null ? "" : ` · Δ ${time.difference_hours}h`}
        </p>
        <p className="mt-1">
          <Flag
            ok={time.within_tolerance}
            label={time.within_tolerance == null ? "No timestamp pair" : time.within_tolerance ? "Within tolerance" : "Outside tolerance"}
          />
        </p>
      </div>

      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--marketing-muted)]">
          Audit trail
        </p>
        <ul className="mt-2 space-y-1.5">
          {order.audit_trail.slice(0, 4).map((entry) => (
            <li key={entry} className="text-[12px] leading-relaxed text-[var(--marketing-fg)]">
              {entry}
            </li>
          ))}
          {order.audit_trail.length === 0 ? (
            <li className="text-[12px] text-[var(--marketing-muted)]">No trail on this order.</li>
          ) : null}
        </ul>
      </div>

      {order.exceptions[0] ? (
        <p className="text-[12px] leading-relaxed text-[var(--marketing-muted)]">{order.exceptions[0].message}</p>
      ) : null}
    </div>
  );
}

export function ProductDemonstration({
  report,
  loading,
  error,
}: {
  report: ReconciliationReport | null;
  loading: boolean;
  error: string | null;
}) {
  const orders = report?.order_results ?? [];
  const defaultId = useMemo(() => {
    return orders.find((order) => !order.reconciled)?.order_id ?? orders[0]?.order_id ?? null;
  }, [orders]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const activeId = selectedId && orders.some((order) => order.order_id === selectedId) ? selectedId : defaultId;
  const selected = orders.find((order) => order.order_id === activeId) ?? null;
  const rows = orders.slice(0, 8);

  return (
    <Frame title="ReconEngine · Reconciliation">
      {error && !report ? (
        <p className="px-6 py-12 text-center text-sm text-[var(--marketing-muted)]">
          Live reconciliation data unavailable.
        </p>
      ) : (
        <div className="grid lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
          <div className="min-w-0 overflow-x-auto lg:border-r lg:border-[var(--marketing-border)]">
            <table className="w-full min-w-[560px] text-left text-[12px]">
              <thead>
                <tr className="border-b border-[var(--marketing-border)] text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--marketing-muted)]">
                  <th className="px-5 py-2.5 font-medium">Order</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Confidence</th>
                  <th className="px-5 py-2.5 font-medium">Settlement</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-5 py-10 text-center text-[var(--marketing-muted)]">
                      {loading ? "Loading live ledger…" : "Live table unavailable"}
                    </td>
                  </tr>
                ) : (
                  rows.map((order) => (
                    <tr
                      key={order.order_id}
                      className={cn(
                        "cursor-pointer border-b border-[var(--marketing-border)] last:border-0 transition",
                        order.order_id === activeId ? "bg-[var(--marketing-bg)]" : "hover:bg-[var(--marketing-bg)]/70",
                      )}
                      onClick={() => setSelectedId(order.order_id)}
                    >
                      <td className="px-5 py-3 font-medium">{order.order_id}</td>
                      <td className="px-5 py-3">
                        <StatusChip reconciled={order.reconciled} />
                      </td>
                      <td className="px-5 py-3 tabular-nums">{order.confidence_score}</td>
                      <td className="px-5 py-3 font-mono text-[11px] text-[var(--marketing-muted)]">
                        {order.primary_settlement_id ?? "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="border-t border-[var(--marketing-border)] p-5 lg:border-t-0">
            {selected ? (
              <OrderDetail order={selected} />
            ) : (
              <p className="py-8 text-sm text-[var(--marketing-muted)]">
                {loading ? "Loading order detail…" : "Select an order to inspect."}
              </p>
            )}
          </div>
        </div>
      )}
    </Frame>
  );
}

export function ApiSample({
  summary,
  loading,
  error,
}: {
  summary: ReconciliationSummary | null;
  loading: boolean;
  error: string | null;
}) {
  const body = summary
    ? JSON.stringify(
        {
          total_orders: summary.total_orders,
          reconciled_orders: summary.reconciled_orders,
          unreconciled_orders: summary.unreconciled_orders,
          status_counts: summary.status_counts,
          exception_counts: summary.exception_counts,
        },
        null,
        2,
      )
    : error
      ? "// Live response unavailable"
      : loading
        ? "// Loading live response…"
        : "// Live response unavailable";

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--marketing-border)] bg-[#0B1B2B] text-left shadow-[0_24px_64px_rgba(11,27,43,0.12)]">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
        <p className="font-mono text-[11px] text-white/55">GET /api/v1/reconciliation/summary</p>
        <p className="text-[11px] uppercase tracking-[0.12em] text-white/40">HTTP</p>
      </div>
      <pre className="overflow-x-auto p-5 font-mono text-[12px] leading-relaxed text-[#D7E3F4] sm:p-6">
        <code>{body}</code>
      </pre>
    </div>
  );
}

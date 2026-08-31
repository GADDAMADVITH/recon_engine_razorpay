import { ArrowDown, X } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { OrderResult } from "../../types/api";
import { cn, formatExceptionLabel, formatPaise, formatStatusLabel } from "../../utils/format";
import { StatusBadge } from "../ui/primitives";

function PipelineStage({
  title,
  body,
  meta,
  status,
  isLast,
}: {
  title: string;
  body: string;
  meta: string;
  status: "ok" | "warning" | "error" | "neutral";
  isLast?: boolean;
}) {
  const borderColors = {
    ok: "border-l-[var(--color-success)]",
    warning: "border-l-[var(--color-warning)]",
    error: "border-l-[var(--color-danger)]",
    neutral: "border-l-black/10",
  };

  return (
    <div className="relative pl-6">
      {!isLast ? (
        <div className="absolute left-[7px] top-8 bottom-0 w-px bg-[var(--color-border)]" />
      ) : null}
      <div
        className={cn(
          "absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-[var(--color-bg)]",
          status === "ok" && "ring-2 ring-[var(--color-success)]",
          status === "warning" && "ring-2 ring-[var(--color-warning)]",
          status === "error" && "ring-2 ring-[var(--color-danger)]",
          status === "neutral" && "ring-2 ring-black/10",
        )}
      />
      <div
        className={cn(
          "rounded-lg border border-[var(--color-border)] border-l-[3px] bg-white px-4 py-3",
          borderColors[status],
        )}
      >
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
          {title}
        </p>
        <p className="mt-1 text-sm font-medium">{body}</p>
        <p className="mt-1 font-mono text-xs text-[var(--color-muted)]">{meta}</p>
      </div>
      {!isLast ? (
        <div className="flex justify-center py-1">
          <ArrowDown className="h-3 w-3 text-[var(--color-muted)]" strokeWidth={1.5} />
        </div>
      ) : null}
    </div>
  );
}

export function OrderDetailDrawer({
  order,
  onClose,
}: {
  order: OrderResult | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!order) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [order, onClose]);

  if (!order) return null;

  const settlementStatus = order.primary_settlement_id
    ? order.amount_comparison.settlement_gross_matches_order === false
      ? "error"
      : "ok"
    : "error";

  const bankStatus = order.valid_bank_transaction_id
    ? order.amount_comparison.bank_matches_settlement_net === false
      ? "error"
      : "ok"
    : "error";

  const refundStatus =
    order.total_refund_paise > 0
      ? order.amount_comparison.settlement_reflects_refund === true
        ? "ok"
        : "error"
      : "neutral";

  const finalStatus = order.reconciled ? "ok" : "error";

  return createPortal(
    <div className="fixed inset-0 z-[100] flex justify-end" role="presentation">
      <button
        type="button"
        className="drawer-overlay absolute inset-0 z-0 bg-black/25"
        aria-label="Close order details"
        onClick={onClose}
      />
      <aside
        className="drawer-panel relative z-10 flex h-full w-full max-w-xl flex-col bg-[var(--color-bg)] shadow-[-8px_0_32px_rgba(0,0,0,0.08)] lg:max-w-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={`Order details for ${order.order_id}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between border-b border-[var(--color-border)] px-6 py-5">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
              Order Detail
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">{order.order_id}</h2>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={order.status} reconciled={order.reconciled} />
              <span className="rounded-md bg-black/[0.04] px-2 py-0.5 text-xs font-medium tabular-nums">
                Confidence {order.confidence_score}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-muted)] transition hover:border-black/20 hover:text-[var(--color-ink)]"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <section className="mb-8">
            <h3 className="mb-4 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
              Reconciliation Pipeline
            </h3>
            <PipelineStage
              title="Order"
              body={`Amount ${formatPaise(order.order_amount_paise)}`}
              meta={order.order_id}
              status="neutral"
            />
            <PipelineStage
              title="Settlement"
              body={
                order.primary_settlement_id
                  ? `Gross ${formatPaise(order.amount_comparison.settlement_gross_paise ?? 0)} · Net ${formatPaise(order.amount_comparison.settlement_net_paise ?? 0)}`
                  : "No settlement linked"
              }
              meta={order.primary_settlement_id ?? "Missing"}
              status={settlementStatus}
            />
            <PipelineStage
              title="Bank"
              body={
                order.valid_bank_transaction_id
                  ? `Bank amount ${formatPaise(order.amount_comparison.bank_amount_paise ?? 0)}`
                  : "No valid bank transaction"
              }
              meta={order.valid_bank_transaction_id ?? "Missing"}
              status={bankStatus}
            />
            <PipelineStage
              title="Refund"
              body={
                order.total_refund_paise > 0
                  ? `Refund total ${formatPaise(order.total_refund_paise)}`
                  : "No refund applied"
              }
              meta={
                order.amount_comparison.settlement_reflects_refund === true
                  ? "Refund reflected in settlement"
                  : order.total_refund_paise > 0
                    ? "Refund not reflected"
                    : "Not applicable"
              }
              status={refundStatus}
            />
            <PipelineStage
              title="Final Decision"
              body={formatStatusLabel(order.status)}
              meta={`Confidence score ${order.confidence_score}`}
              status={finalStatus}
              isLast
            />
          </section>

          <div className="mb-8 grid gap-6 sm:grid-cols-2">
            <section>
              <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
                Amount Comparison
              </h3>
              <dl className="space-y-2 text-sm">
                {[
                  ["Order", formatPaise(order.amount_comparison.order_amount_paise)],
                  [
                    "Settlement gross",
                    order.amount_comparison.settlement_gross_paise != null
                      ? formatPaise(order.amount_comparison.settlement_gross_paise)
                      : "—",
                  ],
                  [
                    "Settlement net",
                    order.amount_comparison.settlement_net_paise != null
                      ? formatPaise(order.amount_comparison.settlement_net_paise)
                      : "—",
                  ],
                  [
                    "Bank amount",
                    order.amount_comparison.bank_amount_paise != null
                      ? formatPaise(order.amount_comparison.bank_amount_paise)
                      : "—",
                  ],
                  [
                    "Expected post-refund",
                    order.amount_comparison.expected_post_refund_gross_paise != null
                      ? formatPaise(order.amount_comparison.expected_post_refund_gross_paise)
                      : "—",
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 border-b border-[var(--color-border)] py-2">
                    <dt className="text-[var(--color-muted)]">{label}</dt>
                    <dd className="font-medium tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section>
              <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
                Timestamp Comparison
              </h3>
              <dl className="space-y-2 text-sm">
                {[
                  ["Settlement", order.timestamp_comparison.settlement_settled_at ?? "—"],
                  ["Bank", order.timestamp_comparison.bank_transaction_date ?? "—"],
                  [
                    "Difference",
                    order.timestamp_comparison.difference_hours != null
                      ? `${order.timestamp_comparison.difference_hours}h`
                      : "—",
                  ],
                  ["Tolerance", `${order.timestamp_comparison.tolerance_hours}h`],
                  [
                    "Within tolerance",
                    order.timestamp_comparison.within_tolerance === true
                      ? "Yes"
                      : order.timestamp_comparison.within_tolerance === false
                        ? "No"
                        : "—",
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 border-b border-[var(--color-border)] py-2">
                    <dt className="text-[var(--color-muted)]">{label}</dt>
                    <dd className="font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>

          <section className="mb-8">
            <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
              Exceptions
            </h3>
            {order.exceptions.length ? (
              <ul className="space-y-2">
                {order.exceptions.map((exception) => (
                  <li
                    key={`${exception.type}-${exception.message}`}
                    className="rounded-lg border border-[var(--color-border)] bg-white px-4 py-3"
                  >
                    <p className="text-sm font-medium">{formatExceptionLabel(exception.type)}</p>
                    <p className="mt-1 text-sm text-[var(--color-muted)]">{exception.message}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[var(--color-muted)]">No exceptions recorded.</p>
            )}
          </section>

          {order.rules_triggered.length > 0 ? (
            <section className="mb-8">
              <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
                Rules Triggered
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {order.rules_triggered.map((rule) => (
                  <span
                    key={rule}
                    className="rounded-md bg-black/[0.04] px-2 py-1 font-mono text-xs"
                  >
                    {rule}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          <section>
            <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
              Audit Trail
            </h3>
            <ol className="space-y-2 border-l border-[var(--color-border)] pl-4">
              {order.audit_trail.map((entry, i) => (
                <li key={entry} className="relative text-sm text-[var(--color-muted)]">
                  <span className="absolute -left-[21px] top-2 h-1.5 w-1.5 rounded-full bg-[var(--color-border)]" />
                  <span className="mr-2 font-mono text-[10px] text-[var(--color-muted)]">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {entry}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
}

import { CheckCircle, XCircle, Clock, AlertTriangle, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type {
  AuditExplanationResponse,
  OrderResult,
  StructuredAuditResponse,
} from "../../types/api";
import { formatPaise } from "../../utils/format";
import { Button, StatusBadge } from "../ui/primitives";

/**
 * Compact structured audit trail panel.
 * When `orderResult` is provided (drawer / bank-import), audit + AI use that
 * payload so Pipeline and Audit Trail stay consistent for the same run.
 * Without it, falls back to GET by order id (production report).
 */
export function AuditTrailPanel({
  orderId,
  orderResult,
}: {
  orderId: string;
  orderResult?: OrderResult;
}) {
  const [audit, setAudit] = useState<StructuredAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<AuditExplanationResponse | null>(null);

  const fetchAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    setExplanation(null);
    setExplanationError(null);
    try {
      const result = orderResult
        ? await api.orderAuditFromResult(orderResult)
        : await api.orderAudit(orderId);
      setAudit(result);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load audit trail.",
      );
    } finally {
      setLoading(false);
    }
  }, [orderId, orderResult]);

  useEffect(() => {
    void fetchAudit();
  }, [fetchAudit]);

  const fetchExplanation = useCallback(async () => {
    setExplanationLoading(true);
    setExplanationError(null);
    try {
      const result = orderResult
        ? await api.orderAuditExplanationFromResult(orderResult)
        : await api.orderAuditExplanation(orderId);
      setExplanation(result);
    } catch (err) {
      setExplanationError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to generate AI explanation.",
      );
    } finally {
      setExplanationLoading(false);
    }
  }, [orderId, orderResult]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10" role="status">
        <div
          className="mb-3 h-5 w-5 animate-[spin_0.8s_linear_infinite] rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent)]"
          aria-hidden
        />
        <p className="text-sm text-[var(--color-muted)]">Loading audit trail…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-[var(--color-danger)]/25 bg-[var(--color-danger)]/5 px-4 py-4 text-sm">
        <p className="font-medium text-[var(--color-danger)]">Failed to load audit</p>
        <p className="mt-1 text-[var(--color-muted)]">{error}</p>
        <Button size="sm" variant="secondary" className="mt-3" onClick={() => void fetchAudit()}>
          Retry audit
        </Button>
      </div>
    );
  }

  if (!audit) return null;

  return (
    <div className="space-y-6" data-testid="audit-trail-panel">
      {/* Header */}
      <div>
        <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
          Audit Trail
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <span className="font-mono text-sm font-medium">{audit.order_id}</span>
          <StatusBadge status={audit.status} reconciled={audit.reconciled} />
          <span className="rounded-md bg-black/[0.04] px-2 py-0.5 text-xs font-medium tabular-nums">
            Confidence {audit.confidence_score}%
          </span>
        </div>
        <div className="mt-4">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void fetchExplanation()}
            disabled={explanationLoading}
            icon={<Sparkles className="h-3.5 w-3.5" />}
          >
            {explanationLoading ? "Generating explanation…" : "Explain with AI"}
          </Button>
        </div>
        {explanationError ? (
          <div className="mt-3 rounded-xl border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 px-4 py-3 text-sm">
            <p className="font-medium text-[var(--color-danger)]">AI explanation unavailable</p>
            <p className="mt-0.5 text-[var(--color-muted)]">{explanationError}</p>
            <p className="mt-2 text-[11px] text-[var(--color-muted)]">
              Reconciliation status is unchanged. You can retry the explanation.
            </p>
            <button
              type="button"
              className="mt-2 text-xs font-medium text-[var(--color-danger)] underline"
              onClick={() => void fetchExplanation()}
            >
              Retry
            </button>
          </div>
        ) : null}
        {explanation ? (
          <div className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-ivory)] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                AI Explanation
              </p>
              <span className="rounded-md bg-white px-2 py-0.5 text-[10px] font-medium tracking-wide text-[var(--color-muted)]">
                Read-only
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-muted)]">
              Grounded on this order’s audit facts — does not change reconciliation status.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={explanation.status} reconciled={explanation.reconciled} />
              <span className="text-[11px] tabular-nums text-[var(--color-muted)]">
                Confidence {explanation.confidence_score}%
              </span>
            </div>
            <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-relaxed text-[var(--color-ink)]">
              {explanation.explanation}
            </pre>
            {explanation.model ? (
              <p className="mt-2 font-mono text-[10px] text-[var(--color-muted)]">
                {explanation.provider} · {explanation.model}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Checks */}
      <section>
        <h4 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Checks
        </h4>
        <ul className="space-y-2">
          {audit.checks.map((check) => (
            <li
              key={check.rule}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                check.passed
                  ? "border-[var(--color-success)]/20 bg-[var(--color-success)]/5"
                  : "border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5"
              }`}
            >
              {check.passed ? (
                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-success)]" />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-danger)]" />
              )}
              <div className="min-w-0">
                <p className={check.passed ? "font-medium text-[var(--color-ink)]" : "font-medium text-[var(--color-danger)]"}>
                  {check.label}
                </p>
                <p className="mt-0.5 text-xs text-[var(--color-muted)]">{check.outcome}</p>
                {check.exception ? (
                  <p className="mt-0.5 text-xs text-[var(--color-danger)]">
                    {check.exception.message}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
          {audit.timestamp_check ? (
            <li
              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                audit.timestamp_check.passed
                  ? "border-[var(--color-success)]/20 bg-[var(--color-success)]/5"
                  : "border-[var(--color-warning)]/30 bg-amber-50"
              }`}
            >
              {audit.timestamp_check.passed ? (
                <Clock className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-success)]" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-warning)]" />
              )}
              <div>
                <p className={audit.timestamp_check.passed ? "font-medium text-[var(--color-ink)]" : "font-medium text-[var(--color-warning)]"}>
                  {audit.timestamp_check.label}
                </p>
                {audit.timestamp_check.difference_hours != null ? (
                  <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                    {audit.timestamp_check.difference_hours}h difference
                    (tolerance: {audit.timestamp_check.tolerance_hours}h)
                  </p>
                ) : null}
              </div>
            </li>
          ) : null}
        </ul>
      </section>

      {/* Amount Summary */}
      <section>
        <h4 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Amounts
        </h4>
        <dl className="grid gap-1 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm sm:grid-cols-2">
          {[
            ["Order", audit.amount_summary.order_amount_paise],
            ["Settlement gross", audit.amount_summary.settlement_gross_paise],
            ["Settlement net", audit.amount_summary.settlement_net_paise],
            ["Bank amount", audit.amount_summary.bank_amount_paise],
          ].map(([label, value]) => (
            <div key={label as string} className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5">
              <dt className="text-[var(--color-muted)]">{label as string}</dt>
              <dd className="font-medium tabular-nums">
                {value != null ? formatPaise(value as number) : "—"}
              </dd>
            </div>
          ))}
          {audit.amount_summary.total_refund_paise > 0 ? (
            <div className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5 sm:col-span-2">
              <dt className="text-[var(--color-muted)]">Total refund</dt>
              <dd className="font-medium tabular-nums">
                {formatPaise(audit.amount_summary.total_refund_paise)}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      {/* References */}
      <section>
        <h4 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          References
        </h4>
        <dl className="grid gap-1 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5">
            <dt className="text-[var(--color-muted)]">Settlement</dt>
            <dd className="font-mono text-xs">
              {audit.references.primary_settlement_id ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5">
            <dt className="text-[var(--color-muted)]">Bank</dt>
            <dd className="font-mono text-xs">
              {audit.references.valid_bank_transaction_id ?? "—"}
            </dd>
          </div>
          {audit.references.refund_ids.length > 0 ? (
            <div className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5 sm:col-span-2">
              <dt className="text-[var(--color-muted)]">Refunds</dt>
              <dd className="font-mono text-xs">
                {audit.references.refund_ids.join(", ")}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      {/* Exceptions */}
      {audit.exceptions.length > 0 ? (
        <section>
          <h4 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
            Exceptions
          </h4>
          <ul className="space-y-2">
            {audit.exceptions.map((exc) => (
              <li
                key={`${exc.type}-${exc.message}`}
                className="rounded-lg border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 px-3 py-2 text-sm"
              >
                <p className="font-mono text-[11px] font-semibold text-[var(--color-danger)]">
                  {exc.type}
                </p>
                <p className="mt-0.5 text-xs text-[var(--color-muted)]">{exc.message}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Timeline */}
      <section>
        <h4 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Timeline
        </h4>
        <ol className="space-y-2 border-l-2 border-[var(--color-accent)]/20 pl-4">
          {audit.timeline.map((entry, i) => (
            <li key={`${i}-${entry}`} className="relative text-sm text-[var(--color-muted)]">
              <span className="absolute -left-[21px] top-[7px] h-2 w-2 rounded-full border-2 border-white bg-[var(--color-accent)]/40" />
              <span className="mr-2 font-mono text-[10px] font-semibold text-[var(--color-accent)]/60">
                {String(i + 1).padStart(2, "0")}
              </span>
              {entry}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type {
  FinanceActionRecordResponse,
  FinanceAgentDecisionTrace,
  FinanceControllerDecision,
  OrderResult,
} from "../../types/api";
import {
  cn,
  formatAgentDecisionLabel,
  formatExceptionLabel,
  formatStatusLabel,
} from "../../utils/format";
import { Button, ErrorState, LoadingState } from "../ui/primitives";

function ApprovalBadge({ requiresApproval }: { requiresApproval: boolean }) {
  if (requiresApproval) {
    return (
      <span
        className="inline-flex items-center rounded-md bg-[var(--color-warning)]/12 px-2 py-0.5 text-xs font-semibold text-[var(--color-warning)]"
        data-testid="approval-required-badge"
      >
        Requires approval
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center rounded-md bg-[var(--color-success)]/10 px-2 py-0.5 text-xs font-semibold text-[var(--color-success)]"
      data-testid="no-approval-badge"
    >
      No action required
    </span>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const needsApproval = decision !== "NO_ACTION";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold",
        needsApproval
          ? "bg-[var(--color-accent-blue)]/10 text-[var(--color-accent-blue)]"
          : "bg-[var(--color-success)]/10 text-[var(--color-success)]",
      )}
      data-testid="agent-decision-type"
    >
      {decision}
    </span>
  );
}

function formatActionTypeLabel(actionType: string): string {
  const words = actionType.replace(/^RECORD_/, "").replace(/_/g, " ").toLowerCase();
  return words.replace(/^\w/, (c) => c.toUpperCase());
}

/**
 * Advisory Finance Controller decision for one order.
 * Displays ORIGINAL reconciliation facts beside the AGENT decision —
 * never implies the agent mutated status, amounts, or confidence.
 * Human-gated approval records a simulated action only (no money movement).
 */
export function AgentDecisionSection({
  order,
  decision,
  decisionTrace,
  loading,
  error,
  onRetry,
}: {
  order: OrderResult;
  decision: FinanceControllerDecision | null;
  /** Optional immutable trace from POST /finance-controller/run-agent. */
  decisionTrace?: FinanceAgentDecisionTrace | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}) {
  const [actionRecord, setActionRecord] = useState<FinanceActionRecordResponse | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  useEffect(() => {
    setActionRecord(null);
    setApproveError(null);
    setApproving(false);
  }, [order.order_id, decision?.decision]);

  const handleApprove = async () => {
    if (!decision || !decision.requires_approval) return;
    setApproving(true);
    setApproveError(null);
    try {
      const result = await api.approveFinanceAction({
        order_id: order.order_id,
        agent_decision: decision.decision,
        order_result: order,
      });
      setActionRecord(result);
    } catch (err) {
      setApproveError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to record the approved action.",
      );
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    if (!decision || !decision.requires_approval) return;
    setApproving(true);
    setApproveError(null);
    try {
      const result = await api.rejectFinanceAction({
        order_id: order.order_id,
        agent_decision: decision.decision,
        order_result: order,
      });
      setActionRecord(result);
    } catch (err) {
      setApproveError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to record the rejection.",
      );
    } finally {
      setApproving(false);
    }
  };

  const recorded = actionRecord?.action_status === "RECORDED";
  const rejected = actionRecord?.action_status === "REJECTED";

  return (
    <section className="mb-8" data-testid="agent-decision-section">
      <h3 className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
        Agent Decision
      </h3>

      {loading && !decision ? (
        <LoadingState label="Loading Finance Controller decision…" />
      ) : null}

      {error && !decision ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : null}

      {decision ? (
        <div className="space-y-4 rounded-xl border border-[var(--color-border)] bg-white p-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
          <div className="flex flex-wrap items-center gap-2">
            <DecisionBadge decision={decision.decision} />
            {recorded ? (
              <span
                className="inline-flex items-center rounded-md bg-[var(--color-success)]/10 px-2 py-0.5 text-xs font-semibold text-[var(--color-success)]"
                data-testid="action-recorded-badge"
              >
                Approved · Action recorded
              </span>
            ) : (
              <ApprovalBadge requiresApproval={decision.requires_approval} />
            )}
          </div>

          <p className="text-sm leading-relaxed text-[var(--color-ink)]" data-testid="agent-decision-reason">
            {decisionTrace?.rationale ?? decision.reason}
          </p>

          {decisionTrace ? (
            <div
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/50 px-3 py-3"
              data-testid="decision-trace-panel"
            >
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                Decision trace
              </p>
              <dl className="mt-2 space-y-1.5 text-xs text-[var(--color-muted)]">
                <div className="flex justify-between gap-2">
                  <dt>Proposed action</dt>
                  <dd
                    className="font-mono text-[10px] text-[var(--color-ink)]"
                    data-testid="decision-trace-proposed-action"
                  >
                    {decisionTrace.proposed_action ?? "none"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Triggered exceptions</dt>
                  <dd className="text-right text-[var(--color-ink)]" data-testid="decision-trace-exceptions">
                    {decisionTrace.triggered_exceptions.length > 0
                      ? decisionTrace.triggered_exceptions.join(", ")
                      : "None"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Trace time</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-ink)]" data-testid="decision-trace-timestamp">
                    {decisionTrace.timestamp}
                  </dd>
                </div>
              </dl>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/70 px-3 py-3"
              data-testid="original-result-panel"
            >
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                Original result
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--color-ink)]">
                {formatStatusLabel(decision.original_status)}
              </p>
              <dl className="mt-2 space-y-1.5 text-xs text-[var(--color-muted)]">
                <div className="flex justify-between gap-2">
                  <dt>Reconciled</dt>
                  <dd className="font-medium text-[var(--color-ink)]">
                    {decision.original_reconciled ? "Yes" : "No"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Confidence</dt>
                  <dd
                    className="font-medium tabular-nums text-[var(--color-ink)]"
                    data-testid="original-confidence"
                  >
                    {decision.confidence_score}%
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Engine status</dt>
                  <dd
                    className="font-mono text-[10px] text-[var(--color-ink)]"
                    data-testid="original-engine-status"
                  >
                    {order.status}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 text-[11px] leading-relaxed text-[var(--color-muted)]">
                Unchanged by the agent — reconciliation remains the source of truth.
              </p>
            </div>

            <div
              className="rounded-lg border border-[var(--color-border)] border-l-[3px] border-l-[var(--color-accent-blue)] px-3 py-3"
              data-testid="agent-decision-panel"
            >
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                Agent decision
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--color-ink)]">
                {formatAgentDecisionLabel(decision.decision)}
              </p>
              <dl className="mt-2 space-y-1.5 text-xs text-[var(--color-muted)]">
                <div className="flex justify-between gap-2">
                  <dt>Action</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-ink)]">
                    {decision.action}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Approval</dt>
                  <dd className="font-medium text-[var(--color-ink)]">
                    {decision.requires_approval ? "Required" : "Not required"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Provider</dt>
                  <dd className="font-medium text-[var(--color-ink)]">
                    {decision.provider ?? "deterministic_policy"}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 text-[11px] leading-relaxed text-[var(--color-muted)]">
                Advisory only until a human approves a simulated record. Does not refund,
                capture, or move money.
              </p>
            </div>
          </div>

          {decision.exception_types.length > 0 ? (
            <div data-testid="agent-decision-exceptions">
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                Exception evidence
              </p>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {decision.exception_types.map((type) => (
                  <li
                    key={type}
                    className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-ink)]"
                  >
                    {formatExceptionLabel(type)}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-[var(--color-muted)]">No blocking exceptions in agent evidence.</p>
          )}

          {/* Human-gated simulated action */}
          <div
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/50 px-4 py-3"
            data-testid="finance-action-panel"
          >
            {!decision.requires_approval ? (
              <p className="text-sm text-[var(--color-muted)]" data-testid="no-action-required-copy">
                No action required
              </p>
            ) : recorded && actionRecord ? (
              <div data-testid="action-recorded-state">
                <p className="text-sm font-semibold text-[var(--color-success)]">Approved</p>
                <p className="mt-1 text-sm text-[var(--color-ink)]">Action recorded</p>
                <dl className="mt-2 space-y-1 text-xs text-[var(--color-muted)]">
                  <div className="flex justify-between gap-2">
                    <dt>Action type</dt>
                    <dd className="font-mono text-[10px] text-[var(--color-ink)]" data-testid="recorded-action-type">
                      {actionRecord.action_type}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Record</dt>
                    <dd className="text-[var(--color-ink)]">
                      {formatActionTypeLabel(actionRecord.action_type)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Action ID</dt>
                    <dd className="font-mono text-[10px] text-[var(--color-ink)]">
                      {actionRecord.action_id}
                    </dd>
                  </div>
                </dl>
                <p className="mt-2 text-[11px] text-[var(--color-muted)]">
                  Simulated record only — no money moved. Original reconciliation facts unchanged.
                  {actionRecord.idempotent_replay ? " (Existing action returned.)" : ""}
                </p>
                <p className="mt-1 font-mono text-[10px] text-[var(--color-success)]" data-testid="money-moved-false">
                  Money moved: false
                </p>
                <p className="mt-2 text-[11px] text-[var(--color-muted)]" data-testid="audit-trail-hint">
                  Open the Audit Trail tab to inspect the recorded finance action event.
                </p>
              </div>
            ) : rejected && actionRecord ? (
              <div data-testid="action-rejected-state">
                <p className="text-sm font-semibold text-[var(--color-danger)]">Rejected</p>
                <p className="mt-1 text-sm text-[var(--color-ink)]">No simulated action recorded</p>
                <p className="mt-2 text-[11px] text-[var(--color-muted)]">
                  Human rejected the proposed follow-up. Original reconciliation facts unchanged.
                  No money moved.
                  {actionRecord.idempotent_replay ? " (Existing rejection returned.)" : ""}
                </p>
                <p className="mt-1 font-mono text-[10px] text-[var(--color-success)]">
                  Money moved: false
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-[var(--color-ink)]">Requires approval</p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Approve to record a simulated follow-up, or reject to dismiss. This does not refund,
                  capture, or call Razorpay money APIs.
                </p>
                <p className="mt-1 font-mono text-[10px] text-[var(--color-muted)]">
                  Money moved: false
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={approving}
                    onClick={() => void handleApprove()}
                    data-testid="approve-action-button"
                    aria-label="Approve and record action"
                  >
                    {approving ? "Recording…" : "Approve & Record Action"}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={approving}
                    onClick={() => void handleReject()}
                    data-testid="reject-action-button"
                    aria-label="Reject proposed action"
                  >
                    Reject
                  </Button>
                </div>
                {approving ? (
                  <p className="mt-2 text-xs text-[var(--color-muted)]" data-testid="approve-loading">
                    Recording simulated action…
                  </p>
                ) : null}
                {approveError ? (
                  <p className="mt-2 text-xs text-[var(--color-danger)]" data-testid="approve-error">
                    {approveError}
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** Compact badge for demo cards / tables. */
export function AgentDecisionChip({
  decision,
}: {
  decision: FinanceControllerDecision | null | undefined;
}) {
  if (!decision) return null;
  const needsApproval = decision.requires_approval;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid={`agent-chip-${decision.order_id}`}>
      <span
        className={cn(
          "rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold",
          needsApproval
            ? "bg-[var(--color-accent-blue)]/10 text-[var(--color-accent-blue)]"
            : "bg-[var(--color-success)]/10 text-[var(--color-success)]",
        )}
      >
        {decision.decision}
      </span>
      {needsApproval ? (
        <span className="rounded-md bg-[var(--color-warning)]/12 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]">
          Requires approval
        </span>
      ) : (
        <span className="rounded-md bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-success)]">
          No action required
        </span>
      )}
    </div>
  );
}

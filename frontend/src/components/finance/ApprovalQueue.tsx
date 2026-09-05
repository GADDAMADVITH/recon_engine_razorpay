import { useCallback, useEffect, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type {
  FinanceApprovalQueueItem,
  FinanceApprovalQueueResponse,
  FinanceLifecycleMetrics,
  OrderResult,
} from "../../types/api";
import { cn, formatAgentDecisionLabel } from "../../utils/format";
import { Button, ErrorState, LoadingState } from "../ui/primitives";

function LifecycleStrip({ metrics }: { metrics: FinanceLifecycleMetrics }) {
  const cells = [
    { label: "Total decisions", value: metrics.total_decisions },
    { label: "No action", value: metrics.no_action },
    { label: "Pending approval", value: metrics.pending_approval },
    { label: "Approved", value: metrics.approved },
    { label: "Rejected", value: metrics.rejected },
    { label: "Recorded", value: metrics.recorded },
    { label: "Unresolved", value: metrics.unresolved },
  ];
  return (
    <div
      className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7"
      data-testid="lifecycle-metrics"
    >
      {cells.map((cell) => (
        <div
          key={cell.label}
          className="console-card rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/60 px-2.5 py-2"
        >
          <p className="text-sm font-semibold tabular-nums text-[var(--color-ink)]">{cell.value}</p>
          <p className="mt-0.5 text-[10px] leading-tight text-[var(--color-muted)]">{cell.label}</p>
        </div>
      ))}
    </div>
  );
}

function statusTone(status: string): string {
  if (status === "PENDING") return "bg-[var(--color-warning)]/12 text-[var(--color-warning)]";
  if (status === "RECORDED" || status === "APPROVED")
    return "bg-[var(--color-success)]/10 text-[var(--color-success)]";
  if (status === "REJECTED") return "bg-[var(--color-danger)]/10 text-[var(--color-danger)]";
  return "bg-[var(--color-bg)] text-[var(--color-muted)]";
}

/**
 * Compact human-in-the-loop approval queue for the Finance Controller panel.
 * Uses live API data only — approve/reject are record-only (no money movement).
 */
export function ApprovalQueue({
  runId,
  orderResults,
  onChanged,
}: {
  runId: string | null | undefined;
  orderResults?: OrderResult[] | null;
  onChanged?: () => void;
}) {
  const [queue, setQueue] = useState<FinanceApprovalQueueResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const orderById = new Map((orderResults ?? []).map((o) => [o.order_id, o]));

  const refresh = useCallback(async () => {
    if (!runId) {
      setQueue(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.getFinanceApprovalQueue(runId);
      setQueue(result);
    } catch (err) {
      setQueue(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load the approval queue.",
      );
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleAction = async (item: FinanceApprovalQueueItem, kind: "approve" | "reject") => {
    setBusyOrderId(item.order_id);
    setActionError(null);
    try {
      const payload = {
        order_id: item.order_id,
        agent_decision: item.decision,
        order_result: orderById.get(item.order_id) ?? undefined,
        run_id: item.run_id,
      };
      if (kind === "approve") {
        await api.approveFinanceAction(payload);
      } else {
        await api.rejectFinanceAction(payload);
      }
      await refresh();
      onChanged?.();
    } catch (err) {
      setActionError(
        err instanceof ApiClientError
          ? err.message
          : kind === "approve"
            ? "Unable to approve the action."
            : "Unable to reject the action.",
      );
    } finally {
      setBusyOrderId(null);
    }
  };

  if (!runId) return null;

  const pendingItems = (queue?.items ?? []).filter((i) => i.lifecycle_status === "PENDING");
  const shownItems = pendingItems.slice(0, 8);

  return (
    <div
      className="mt-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="approval-queue"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Approval Queue
        </p>
        {queue ? (
          <p className="text-xs text-[var(--color-muted)]" data-testid="approval-queue-pending-count">
            {queue.pending_count} pending
          </p>
        ) : null}
      </div>

      {queue?.lifecycle ? <LifecycleStrip metrics={queue.lifecycle} /> : null}

      {loading && !queue ? <LoadingState label="Loading approval queue…" /> : null}
      {error && !queue ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

      {queue && shownItems.length === 0 ? (
        <p className="py-4 text-center text-sm text-[var(--color-muted)]" data-testid="approval-queue-empty">
          No decisions pending approval for this run.
        </p>
      ) : null}

      {shownItems.length > 0 ? (
        <ul className="divide-y divide-[var(--color-border)]" data-testid="approval-queue-list">
          {shownItems.map((item) => {
            const busy = busyOrderId === item.order_id;
            return (
              <li
                key={`${item.run_id}:${item.order_id}`}
                className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
                data-testid={`approval-queue-item-${item.order_id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-[var(--color-ink)]">
                      {item.order_id}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--color-accent-blue)]">
                      {item.decision}
                    </span>
                    <span
                      className={cn(
                        "rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
                        statusTone(item.lifecycle_status),
                      )}
                      data-testid={`approval-status-${item.order_id}`}
                    >
                      {item.lifecycle_status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">
                    {item.rationale}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-[var(--color-ink)]">
                    {item.proposed_action ?? "none"} · {formatAgentDecisionLabel(item.decision)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={busy}
                    onClick={() => void handleAction(item, "approve")}
                    data-testid={`approve-queue-${item.order_id}`}
                    aria-label={`Approve ${item.order_id}`}
                  >
                    {busy ? "…" : "Approve"}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => void handleAction(item, "reject")}
                    data-testid={`reject-queue-${item.order_id}`}
                    aria-label={`Reject ${item.order_id}`}
                  >
                    Reject
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      {pendingItems.length > shownItems.length ? (
        <p className="mt-3 text-xs text-[var(--color-muted)]">
          Showing {shownItems.length} of {pendingItems.length} pending items.
        </p>
      ) : null}

      {actionError ? (
        <p className="mt-3 text-xs text-[var(--color-danger)]" data-testid="approval-queue-action-error">
          {actionError}
        </p>
      ) : null}
      {loading && queue ? (
        <p className="mt-2 text-xs text-[var(--color-muted)]">Refreshing queue…</p>
      ) : null}
    </div>
  );
}

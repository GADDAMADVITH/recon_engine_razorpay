import { useCallback, useEffect, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type { FinanceAgentPlanResponse, OrderResult } from "../../types/api";
import { cn, formatAgentDecisionLabel, formatExceptionLabel } from "../../utils/format";
import { ErrorState, LoadingState, MetricCard } from "../ui/primitives";

/**
 * Compact Agent Work Queue + expandable Agent Plan.
 * Driven by POST /finance-controller/agent-plan (real API data only).
 */
export function AgentWorkQueue({
  orderResults,
  initialPlan = null,
  refreshToken,
}: {
  orderResults?: OrderResult[] | null;
  /** Prefer plan already produced by the Run Agent flow when present. */
  initialPlan?: FinanceAgentPlanResponse | null;
  /** Bumps refresh when a new agent run completes. */
  refreshToken?: string | number | null;
}) {
  const [plan, setPlan] = useState<FinanceAgentPlanResponse | null>(initialPlan);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const orderKey = orderResults
    ? `${orderResults.length}:${orderResults.map((o) => o.order_id).join(",")}`
    : "production";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result =
        orderResults && orderResults.length > 0
          ? await api.runFinanceControllerAgentPlan({ order_results: orderResults })
          : await api.runFinanceControllerAgentPlan();
      setPlan(result);
    } catch (err) {
      setPlan(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load the agent work plan.",
      );
    } finally {
      setLoading(false);
    }
  }, [orderKey]);

  useEffect(() => {
    if (initialPlan) {
      setPlan(initialPlan);
      return;
    }
    void refresh();
  }, [refresh, initialPlan, refreshToken]);

  const analysis = plan?.batch_analysis;
  const topItems = (plan?.prioritized_work_queue ?? []).slice(0, 8);

  return (
    <div
      className="mt-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="agent-work-queue"
    >
      <p className="mb-3 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
        Agent Work Queue
      </p>

      {loading && !plan ? <LoadingState label="Building agent work plan…" /> : null}
      {error && !plan ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}

      {analysis ? (
        <div
          className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"
          data-testid="agent-work-queue-metrics"
        >
          <MetricCard value={analysis.records_processed} label="Total records" accent="brand" />
          <MetricCard
            value={analysis.unresolved_count}
            label="Unresolved"
            accent={analysis.unresolved_count > 0 ? "warning" : "default"}
          />
          <MetricCard
            value={analysis.approval_required_count}
            label="Approval required"
            accent={analysis.approval_required_count > 0 ? "warning" : "default"}
          />
          <MetricCard
            value={analysis.reconciled_count}
            label="Reconciled"
            accent="success"
          />
        </div>
      ) : null}

      {topItems.length > 0 ? (
        <ul className="divide-y divide-[var(--color-border)]" data-testid="agent-work-queue-list">
          {topItems.map((item) => {
            const issue =
              item.exceptions.filter((e) => !e.includes("WITHIN_TOLERANCE"))[0] ??
              item.exceptions[0] ??
              item.decision;
            return (
              <li
                key={item.order_id}
                className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                data-testid={`agent-work-item-${item.order_id}`}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-[var(--color-ink)]">
                      {item.order_id}
                    </span>
                    <span className="text-xs text-[var(--color-muted)]">
                      {formatExceptionLabel(String(issue))}
                    </span>
                    <span
                      className="rounded-md bg-[var(--color-accent-blue)]/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[var(--color-accent-blue)]"
                      data-testid={`work-priority-${item.order_id}`}
                    >
                      P{item.priority}
                    </span>
                    {item.requires_approval ? (
                      <span
                        className="rounded-md bg-[var(--color-warning)]/12 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
                        data-testid={`work-approval-${item.order_id}`}
                      >
                        Approval required
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 font-mono text-[10px] text-[var(--color-ink)]">
                    {item.proposed_action ?? "none"} · {formatAgentDecisionLabel(item.decision)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      ) : plan && !loading ? (
        <p className="py-3 text-center text-sm text-[var(--color-muted)]">
          No prioritized work items for this batch.
        </p>
      ) : null}

      {plan?.agent_plan ? (
        <div className="mt-4 border-t border-[var(--color-border)] pt-3" data-testid="agent-plan-section">
          <button
            type="button"
            className={cn(
              "text-[13px] font-medium tracking-tight text-[var(--color-ink)]",
              "cursor-pointer hover:text-[var(--color-accent)]",
            )}
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            data-testid="agent-plan-toggle"
          >
            Agent Plan {expanded ? "▴" : "▾"}
          </button>
          {expanded ? (
            <div className="mt-3 space-y-3 text-sm" data-testid="agent-plan-body">
              <div>
                <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                  Objective
                </p>
                <p className="mt-1 text-[var(--color-ink)]">{plan.agent_plan.objective}</p>
              </div>
              <div>
                <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                  What the agent found
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-[var(--color-muted)]">
                  {plan.agent_plan.observations.map((obs) => (
                    <li key={obs}>{obs}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                  What it recommends
                </p>
                <ul className="mt-1 space-y-1 text-xs text-[var(--color-ink)]">
                  {plan.agent_plan.proposed_actions.map((a) => (
                    <li key={a.action} className="font-mono text-[10px]">
                      {a.action} × {a.count}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                  What needs human approval
                </p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  {plan.agent_plan.human_approval_requirements.required_count} decisions —{" "}
                  {plan.agent_plan.human_approval_requirements.rule}
                </p>
              </div>
              <div>
                <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
                  What remains unresolved
                </p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  {plan.agent_plan.unresolved_cases.count} unresolved · by decision{" "}
                  {JSON.stringify(plan.agent_plan.unresolved_cases.by_decision)}
                </p>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {loading && plan ? (
        <p className="mt-2 text-xs text-[var(--color-muted)]">Refreshing agent plan…</p>
      ) : null}
    </div>
  );
}

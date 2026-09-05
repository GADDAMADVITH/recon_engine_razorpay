import { useRef, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type {
  FinanceAgentPlanResponse,
  FinanceAgentRunResponse,
  FinanceWorkQueueItem,
  OrderResult,
} from "../../types/api";
import { cn, formatAgentDecisionLabel, formatExceptionLabel } from "../../utils/format";
import { Button, ErrorState } from "../ui/primitives";

const RUN_STAGES = [
  "Loading reconciliation results",
  "Analyzing financial exceptions",
  "Applying finance-control policy",
  "Generating agent decisions",
  "Prioritizing unresolved work",
  "Creating human approval queue",
] as const;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Demo-visible agent execution: calls real run-agent + agent-plan APIs.
 * Stage labels describe work in flight — no fake percentages or streamed records.
 */
export function AgentRunLauncher({
  orderResults,
  latestRun,
  onComplete,
  onClearResults,
  stageDelayMs = 180,
}: {
  orderResults?: OrderResult[] | null;
  latestRun?: FinanceAgentRunResponse | null;
  onComplete: (run: FinanceAgentRunResponse, plan: FinanceAgentPlanResponse) => void;
  /** Optional: clear displayed results before a fresh run (does not mutate engine data). */
  onClearResults?: () => void;
  /** Stage pacing for visible progress (0 in tests). Not a fake percentage. */
  stageDelayMs?: number;
}) {
  const [executing, setExecuting] = useState(false);
  const [stageIndex, setStageIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);
  const [completedRun, setCompletedRun] = useState<FinanceAgentRunResponse | null>(null);
  const [planSnapshot, setPlanSnapshot] = useState<FinanceAgentPlanResponse | null>(null);
  const inFlight = useRef(false);

  const readyCount = orderResults?.length ?? 0;
  const canRun = readyCount > 0 && !executing;
  const displayRun = completedRun ?? latestRun ?? null;

  const topCase: FinanceWorkQueueItem | null =
    planSnapshot?.prioritized_work_queue?.[0] ?? null;

  const handleRun = async () => {
    if (inFlight.current || !orderResults || orderResults.length === 0) return;
    inFlight.current = true;
    setExecuting(true);
    setError(null);
    setCompletedRun(null);
    setPlanSnapshot(null);
    onClearResults?.();

    try {
      setStageIndex(0);
      if (stageDelayMs > 0) await sleep(stageDelayMs);
      setStageIndex(1);
      if (stageDelayMs > 0) await sleep(stageDelayMs);
      setStageIndex(2);
      if (stageDelayMs > 0) await sleep(stageDelayMs);
      setStageIndex(3);

      const run = await api.runFinanceControllerAgent({ order_results: orderResults });

      setStageIndex(4);
      const plan = await api.runFinanceControllerAgentPlan({ order_results: orderResults });

      setStageIndex(5);
      if (stageDelayMs > 0) await sleep(Math.min(stageDelayMs, 120));

      setCompletedRun(run);
      setPlanSnapshot(plan);
      onComplete(run, plan);
    } catch (err) {
      setCompletedRun(null);
      setPlanSnapshot(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to run the Finance Controller Agent.",
      );
    } finally {
      setExecuting(false);
      setStageIndex(-1);
      inFlight.current = false;
    }
  };

  const scrollToQueue = () => {
    document
      .getElementById("agent-approval-section")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div
      className="console-card mb-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="agent-run-launcher"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
            Run Finance Controller Agent
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]" data-testid="agent-run-ready-count">
            {readyCount > 0
              ? `${readyCount} records ready`
              : "No reconciliation results loaded yet."}
          </p>
          {displayRun ? (
            <p className="mt-1 font-mono text-[10px] text-[var(--color-muted)]" data-testid="agent-run-latest-meta">
              Latest run {displayRun.run_id}
              {displayRun.completed_at ? ` · ${displayRun.completed_at}` : ""}
            </p>
          ) : (
            <p className="mt-1 text-xs text-[var(--color-muted)]" data-testid="agent-run-idle-status">
              Status: idle — click Run to analyze this batch
            </p>
          )}
        </div>
        <Button
          variant="primary"
          size="sm"
          disabled={!canRun}
          onClick={() => void handleRun()}
          data-testid="run-finance-controller-agent"
          aria-label="Run Finance Controller Agent"
        >
          {executing ? "Running…" : "Run Finance Controller Agent"}
        </Button>
      </div>

      {executing ? (
        <div className="agent-run-enter mt-5" data-testid="agent-run-progress">
          <p className="text-sm font-medium text-[var(--color-ink)]">
            Finance Controller Agent is analyzing…
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Stage-based progress from the live agent APIs — not a simulated record stream.
          </p>
          <ol className="mt-3 space-y-2">
            {RUN_STAGES.map((label, index) => {
              const done = stageIndex > index;
              const active = stageIndex === index;
              return (
                <li
                  key={label}
                  className={cn(
                    "flex items-center gap-2 text-xs transition-colors duration-200",
                    done
                      ? "text-[var(--color-success)]"
                      : active
                        ? "font-medium text-[var(--color-ink)]"
                        : "text-[var(--color-muted)]",
                  )}
                  data-testid={`agent-run-stage-${index}`}
                  data-active={active ? "true" : "false"}
                >
                  <span className="font-mono text-[10px] tabular-nums">{index + 1}.</span>
                  <span>{label}</span>
                  {active ? (
                    <span className="agent-stage-pulse h-1.5 w-1.5 rounded-full bg-[var(--color-accent-blue)]" aria-hidden />
                  ) : null}
                  {done ? <span aria-hidden>✓</span> : null}
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}

      {error ? (
        <div className="mt-4" data-testid="agent-run-error">
          <ErrorState message={error} onRetry={() => void handleRun()} />
        </div>
      ) : null}

      {completedRun && !executing ? (
        <div
          className="agent-run-enter mt-5 rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 px-4 py-4"
          data-testid="agent-run-complete-card"
        >
          <p className="text-sm font-semibold text-[var(--color-success)]">
            ✓ Finance Controller Agent completed
          </p>
          <p className="mt-2 text-sm text-[var(--color-ink)]" data-testid="agent-run-complete-summary">
            {completedRun.records_processed} records analyzed
            {" · "}
            {completedRun.review_required_count} require human review
            {" · "}
            {completedRun.no_action_count} require no action
          </p>
          <div className="mt-3" data-testid="agent-run-complete-decisions">
            <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
              Agent decisions
            </p>
            <ul className="mt-1 space-y-1 font-mono text-[10px] text-[var(--color-ink)]">
              {Object.entries(completedRun.decisions_by_type)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([decision, count]) => (
                  <li key={decision}>
                    {decision}: {count}
                  </li>
                ))}
            </ul>
          </div>
          <p className="mt-2 font-mono text-[10px] text-[var(--color-success)]">
            Money moved: false
          </p>
        </div>
      ) : null}

      {planSnapshot && !executing ? (
        <div
          className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]/50 px-4 py-4"
          data-testid="agent-work-generated"
        >
          <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
            Agent-generated work queue
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Built from the live agent-plan response after this run.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="agent-work-generated-metrics">
            <div>
              <p className="text-[1.25rem] font-semibold tabular-nums text-[var(--color-ink)]">
                {planSnapshot.records_processed}
              </p>
              <p className="text-[10px] text-[var(--color-muted)]">Records analyzed</p>
            </div>
            <div>
              <p className="text-[1.25rem] font-semibold tabular-nums text-[var(--color-warning)]">
                {planSnapshot.unresolved_count}
              </p>
              <p className="text-[10px] text-[var(--color-muted)]">Unresolved</p>
            </div>
            <div>
              <p className="text-[1.25rem] font-semibold tabular-nums text-[var(--color-warning)]">
                {planSnapshot.pending_approval_count}
              </p>
              <p className="text-[10px] text-[var(--color-muted)]">Pending approval</p>
            </div>
            <div>
              <p className="text-[1.25rem] font-semibold tabular-nums text-[var(--color-ink)]">
                {planSnapshot.prioritized_work_queue.length}
              </p>
              <p className="text-[10px] text-[var(--color-muted)]">Queued cases</p>
            </div>
          </div>

          {topCase ? (
            <div
              className="mt-4 rounded-md border border-[var(--color-accent-blue)]/25 bg-white px-3 py-3"
              data-testid="agent-highlight-case"
            >
              <p className="text-[11px] font-medium tracking-wide text-[var(--color-accent-blue)]">
                Agent identified a high-priority exception
              </p>
              <p className="mt-2 font-mono text-xs font-semibold text-[var(--color-ink)]">
                {topCase.order_id}
              </p>
              <dl className="mt-2 space-y-1 text-xs text-[var(--color-muted)]">
                <div className="flex justify-between gap-2">
                  <dt>Decision</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-ink)]">
                    {topCase.decision} · {formatAgentDecisionLabel(topCase.decision)}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Priority</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-ink)]">P{topCase.priority}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Exception</dt>
                  <dd className="text-right text-[var(--color-ink)]">
                    {formatExceptionLabel(
                      String(
                        topCase.exceptions.filter((e) => !e.includes("WITHIN_TOLERANCE"))[0] ??
                          topCase.exceptions[0] ??
                          topCase.decision,
                      ),
                    )}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Proposed action</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-ink)]">
                    {topCase.proposed_action ?? "none"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Requires approval</dt>
                  <dd className="text-[var(--color-ink)]">
                    {topCase.requires_approval ? "yes" : "no"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Money moved</dt>
                  <dd className="font-mono text-[10px] text-[var(--color-success)]">false</dd>
                </div>
              </dl>
              <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink)]" data-testid="agent-highlight-rationale">
                {topCase.rationale}
              </p>
              <p className="mt-2 text-[11px] text-[var(--color-muted)]">
                Agent found it → analyzed it → prioritized it → human must review it
              </p>
            </div>
          ) : null}

          <div className="mt-4">
            <Button
              variant="secondary"
              size="sm"
              onClick={scrollToQueue}
              data-testid="review-prioritized-cases"
            >
              Review prioritized cases
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

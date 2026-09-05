import { ArrowDown, ArrowRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiClientError } from "../../api/client";
import type {
  FinanceAgentDecisionTrace,
  FinanceAgentPlanResponse,
  FinanceAgentRunResponse,
  FinanceControllerEvaluationResponse,
  FinanceControllerRunResponse,
  FinanceDemoStatusResponse,
  OrderResult,
} from "../../types/api";
import { cn, formatAgentDecisionLabel, formatExceptionLabel } from "../../utils/format";
import {
  Button,
  ErrorState,
  LoadingState,
  MetricCard,
  SectionLabel,
} from "../ui/primitives";
import { ApprovalQueue } from "./ApprovalQueue";
import { AgentWorkQueue } from "./AgentWorkQueue";
import { AgentRunLauncher } from "./AgentRunLauncher";

const WORKFLOW_STEPS = [
  "Reconciliation",
  "Analyze",
  "Prioritize",
  "Human Review",
  "Approve/Reject",
  "Record Action",
  "Audit",
] as const;

const PIPELINE_STEPS = [
  { title: "Reconciliation Engine", caption: "Source of truth — status, amounts, confidence" },
  { title: "Structured Audit / Evidence", caption: "Deterministic checks and exception facts" },
  { title: "Finance Controller Agent", caption: "Deterministic classification / safety boundary" },
  { title: "Agent Orchestration", caption: "Batch analysis, priority queue, and work planning" },
  { title: "Human Approval → Simulated Action", caption: "Record-only; no autonomous money movement" },
] as const;

const DECISION_ORDER = [
  "NO_ACTION",
  "FLAG_FOR_REVIEW",
  "VERIFY_REFUND",
  "ESCALATE_MISSING_BANK",
  "ESCALATE_MISSING_SETTLEMENT",
] as const;

type FinancePanelData = FinanceControllerRunResponse | FinanceAgentRunResponse;

function isAgentRun(data: FinancePanelData): data is FinanceAgentRunResponse {
  return "run_id" in data && typeof (data as FinanceAgentRunResponse).run_id === "string";
}

function WorkflowStrip() {
  return (
    <div
      className="console-card mb-6 rounded-xl border border-[var(--color-border)] bg-white px-4 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="finance-ops-workflow"
    >
      <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
        Finance-ops loop
      </p>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        Reconciliation truth → deterministic decisions → orchestration → human approval → simulated
        record → audit. The agent never moves money.
      </p>
      <ol className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-2">
        {WORKFLOW_STEPS.map((step, index) => (
          <li key={step} className="flex items-center gap-1">
            <span
              className={cn(
                "rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]/70 px-2 py-1 text-[11px] font-medium text-[var(--color-ink)] transition-colors",
                step === "Human Review" || step === "Approve/Reject"
                  ? "border-[var(--color-warning)]/40 text-[var(--color-warning)]"
                  : step === "Reconciliation"
                    ? "border-[var(--color-accent-blue)]/30 text-[var(--color-accent-blue)]"
                    : null,
              )}
            >
              {step}
            </span>
            {index < WORKFLOW_STEPS.length - 1 ? (
              <ArrowRight className="h-3 w-3 text-[var(--color-muted)]" aria-hidden strokeWidth={1.5} />
            ) : null}
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2" data-testid="finance-safety-badges">
        <span className="rounded-md bg-[var(--color-warning)]/12 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]">
          Human approval required
        </span>
        <span
          className="rounded-md bg-[var(--color-success)]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[var(--color-success)]"
          data-testid="money-moved-false-badge"
        >
          Money moved: false
        </span>
        <span className="rounded-md bg-[var(--color-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-muted)]">
          Simulated actions only · Audit trail available
        </span>
      </div>
    </div>
  );
}

function ArchitectureFlow() {
  return (
    <div
      className="console-card h-fit self-start rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="finance-controller-architecture"
    >
      <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
        Decision architecture
      </p>
      <p className="mt-1 text-sm leading-relaxed text-[var(--color-muted)]">
        The agent sits downstream of reconciliation. It does not alter engine results.
      </p>
      <ol className="mt-4 space-y-0">
        {PIPELINE_STEPS.map((step, index) => (
          <li key={step.title} className="relative pl-0">
            <div className="rounded-lg border border-[var(--color-border)] border-l-[3px] border-l-[var(--color-accent-blue)] bg-[var(--color-bg)]/60 px-3.5 py-2.5">
              <p className="text-sm font-semibold tracking-tight text-[var(--color-ink)]">
                {step.title}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-[var(--color-muted)]">{step.caption}</p>
            </div>
            {index < PIPELINE_STEPS.length - 1 ? (
              <div className="flex justify-center py-1" aria-hidden>
                <ArrowDown className="h-3.5 w-3.5 text-[var(--color-muted)]" strokeWidth={1.5} />
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs leading-relaxed text-[var(--color-muted)]">
        Classification is deterministic policy. Orchestration plans and prioritizes the batch.
        Gemini remains explanation/chat only — never in the decision path.
      </p>
    </div>
  );
}

function DecisionBreakdown({
  decisionsByType,
  total,
}: {
  decisionsByType: Record<string, number>;
  total: number;
}) {
  const entries = [
    ...DECISION_ORDER.filter((key) => (decisionsByType[key] ?? 0) > 0).map((key) => [
      key,
      decisionsByType[key] ?? 0,
    ] as const),
    ...Object.entries(decisionsByType).filter(
      ([key, count]) => count > 0 && !(DECISION_ORDER as readonly string[]).includes(key),
    ),
  ];

  if (entries.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-[var(--color-muted)]">No decisions recorded.</p>
    );
  }

  return (
    <ul className="divide-y divide-[var(--color-border)]" data-testid="finance-controller-breakdown">
      {entries.map(([type, count]) => {
        const needsApproval = type !== "NO_ACTION";
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        return (
          <li
            key={type}
            className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
          >
            <div className="min-w-0">
              <p className="font-mono text-xs font-medium text-[var(--color-ink)]">{type}</p>
              <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                {formatAgentDecisionLabel(type)}
                {needsApproval ? " · Requires approval" : " · No approval required"}
                {" · "}
                {pct}%
              </p>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-md px-2.5 py-1 text-sm font-semibold tabular-nums",
                needsApproval
                  ? "bg-[var(--color-warning)]/10 text-[var(--color-warning)]"
                  : "bg-[var(--color-success)]/10 text-[var(--color-success)]",
              )}
            >
              {count}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ExceptionSummary({
  decisions,
  unresolvedCount,
  recordsProcessed,
}: {
  decisions: FinanceAgentDecisionTrace[];
  unresolvedCount: number;
  recordsProcessed: number;
}) {
  const groups = useMemo(() => {
    const byDecision: Record<string, string[]> = {};
    for (const d of decisions) {
      if (d.decision === "NO_ACTION" && !d.requires_approval) continue;
      const list = byDecision[d.decision] ?? [];
      list.push(d.order_id);
      byDecision[d.decision] = list;
    }
    return Object.entries(byDecision)
      .map(([decision, ids]) => ({
        decision,
        count: ids.length,
        sample: [...ids].sort().slice(0, 3),
        pct:
          unresolvedCount > 0
            ? Math.round((ids.length / unresolvedCount) * 100)
            : 0,
      }))
      .sort((a, b) => b.count - a.count || a.decision.localeCompare(b.decision));
  }, [decisions, unresolvedCount]);

  const exceptionTypes = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of decisions) {
      for (const ex of d.triggered_exceptions ?? []) {
        if (String(ex).includes("WITHIN_TOLERANCE")) continue;
        counts[ex] = (counts[ex] ?? 0) + 1;
      }
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 6);
  }, [decisions]);

  return (
    <div
      className="mt-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="exception-summary"
    >
      <p className="mb-1 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
        Exception summary
      </p>
      <p className="mb-4 text-xs text-[var(--color-muted)]">
        Honest unresolved cases from the operational batch — not hidden or auto-resolved.
        {` ${unresolvedCount} of ${recordsProcessed} require human review.`}
      </p>
      {exceptionTypes.length > 0 ? (
        <ul className="mb-4 space-y-2" data-testid="top-exception-categories">
          {exceptionTypes.map(([type, count]) => (
            <li key={type} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-[var(--color-ink)]">{formatExceptionLabel(type)}</span>
              <span className="font-mono tabular-nums text-[var(--color-muted)]">{count}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <ul className="divide-y divide-[var(--color-border)]" data-testid="exception-by-decision">
        {groups.map((g) => (
          <li key={g.decision} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-mono text-xs font-medium text-[var(--color-ink)]">{g.decision}</p>
              <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
                {g.count} · {g.pct}% of unresolved · Human approval required
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-[var(--color-muted)]">
                e.g. {g.sample.join(", ")}
              </p>
            </div>
            <span className="shrink-0 rounded-md bg-[var(--color-warning)]/10 px-2 py-1 text-sm font-semibold tabular-nums text-[var(--color-warning)]">
              {g.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HeldOutEvaluationStrip() {
  const [evalData, setEvalData] = useState<FinanceControllerEvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEvalData(await api.getFinanceControllerEvaluation());
    } catch (err) {
      setEvalData(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load held-out evaluation metrics.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const agreement =
    evalData && evalData.records_evaluated > 0
      ? `${Math.round(evalData.accuracy * 100)}% agreement with human-authored labels on ${evalData.records_evaluated} synthetic held-out records`
      : null;

  return (
    <div
      className="mt-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="held-out-evaluation"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Held-out evaluation
        </p>
        <span className="rounded-md bg-[var(--color-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-muted)]">
          Separate from operational batch
        </span>
      </div>
      {loading && !evalData ? <LoadingState label="Loading held-out evaluation…" /> : null}
      {error && !evalData ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}
      {evalData ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <MetricCard
              value={evalData.records_evaluated}
              label="Records evaluated"
              accent="brand"
            />
            <MetricCard
              value={evalData.correct_decisions}
              label="Correct"
              accent="success"
            />
            <MetricCard
              value={evalData.incorrect_decisions}
              label="Incorrect"
              accent={evalData.incorrect_decisions > 0 ? "danger" : "default"}
            />
          </div>
          <p className="mt-3 text-sm text-[var(--color-ink)]" data-testid="held-out-agreement-copy">
            {agreement}
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]" data-testid="held-out-measurement-note">
            {evalData.measurement_note} This is policy fidelity — not production accuracy.
          </p>
        </>
      ) : null}
    </div>
  );
}

function DemoReadiness({ onReset }: { onReset?: () => void }) {
  const [status, setStatus] = useState<FinanceDemoStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetNote, setResetNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setStatus(await api.getFinanceDemoStatus());
    } catch (err) {
      setStatus(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to check demo readiness.",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleReset = async () => {
    setResetting(true);
    setResetNote(null);
    try {
      const result = await api.resetFinanceDemoActions();
      setResetNote(result.note);
      onReset?.();
      await refresh();
    } catch (err) {
      setResetNote(
        err instanceof ApiClientError
          ? err.message
          : "Unable to reset demo action state.",
      );
    } finally {
      setResetting(false);
    }
  };

  return (
    <div
      className="rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="demo-readiness"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
          Demo readiness
        </p>
        {status ? (
          <span
            className={cn(
              "rounded-md px-2 py-0.5 text-[10px] font-semibold",
              status.ready
                ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                : "bg-[var(--color-warning)]/12 text-[var(--color-warning)]",
            )}
            data-testid="demo-readiness-badge"
          >
            {status.ready ? "Ready" : "Not ready"}
          </span>
        ) : null}
      </div>
      {error ? (
        <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>
      ) : null}
      {status ? (
        <ul className="mt-3 space-y-1 text-xs text-[var(--color-muted)]" data-testid="demo-readiness-checks">
          <li>API reachable: {status.checks.api_reachable ? "yes" : "no"}</li>
          <li>
            Reconciliation data:{" "}
            {status.checks.reconciliation_data_available
              ? `${status.operational_batch.records} records`
              : "unavailable"}
          </li>
          <li>Agent endpoint: {status.checks.agent_endpoint_available ? "available" : "no"}</li>
          <li>
            Evaluation endpoint:{" "}
            {status.checks.evaluation_endpoint_available
              ? `${status.held_out_evaluation.records_evaluated} held-out records`
              : "no"}
          </li>
          <li className="font-mono text-[10px]">Money moved: {String(status.money_moved)}</li>
        </ul>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={resetting}
          onClick={() => void handleReset()}
          data-testid="demo-reset-button"
        >
          {resetting ? "Resetting…" : "Reset demo actions"}
        </Button>
        <span className="text-[10px] text-[var(--color-muted)]">
          Clears local simulated actions only — not CSVs, eval labels, or policy.
        </span>
      </div>
      {resetNote ? (
        <p className="mt-2 text-xs text-[var(--color-muted)]" data-testid="demo-reset-note">
          {resetNote}
        </p>
      ) : null}
    </div>
  );
}

function AgentRunSummary({ data }: { data: FinanceAgentRunResponse }) {
  const durationLabel =
    data.elapsed_seconds < 0.001
      ? "<1ms"
      : data.elapsed_seconds < 1
        ? `${Math.round(data.elapsed_seconds * 1000)}ms`
        : `${data.elapsed_seconds.toFixed(3)}s`;

  return (
    <div
      className="mb-6 rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]"
      data-testid="agent-run-section"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
            Operational batch
          </p>
          <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
            Agent run metrics
          </p>
        </div>
        <p className="font-mono text-[10px] text-[var(--color-muted)]" data-testid="agent-run-id">
          {data.run_id}
        </p>
      </div>
      <p className="mb-3 text-sm text-[var(--color-ink)]" data-testid="records-processed-copy">
        {data.records_processed} records processed
        {data.review_required_count > 0
          ? ` · ${data.review_required_count} require human review`
          : ""}
      </p>
      <div
        className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3 lg:grid-cols-6"
        data-testid="agent-run-metrics"
      >
        <MetricCard value={data.records_processed} label="Records processed" accent="brand" />
        <MetricCard value={data.no_action_count} label="No action" accent="success" />
        <MetricCard
          value={data.review_required_count}
          label="Review required"
          accent={data.review_required_count > 0 ? "warning" : "default"}
        />
        <MetricCard
          value={data.pending_approval_count}
          label="Pending approval"
          accent={data.pending_approval_count > 0 ? "warning" : "default"}
        />
        <MetricCard
          value={data.unresolved_count}
          label="Unresolved"
          accent={data.unresolved_count > 0 ? "warning" : "default"}
        />
        <MetricCard value={durationLabel} label="Latest run duration" accent="default" />
      </div>
    </div>
  );
}

export function FinanceControllerPanel({
  data,
  loading,
  error,
  onRetry,
  orderResults,
  requireManualRun = false,
  onAgentRunComplete,
  onAgentRunClear,
}: {
  data: FinancePanelData | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
  /** Engine order_results for approve/reject (same facts as the run). */
  orderResults?: OrderResult[] | null;
  /** Dashboard demo: wait for explicit Run before showing agent results. */
  requireManualRun?: boolean;
  onAgentRunComplete?: (run: FinanceAgentRunResponse) => void;
  onAgentRunClear?: () => void;
}) {
  const [planFromRun, setPlanFromRun] = useState<FinanceAgentPlanResponse | null>(null);
  const approvalRefId = "agent-approval-section";

  const showResults = Boolean(data);

  return (
    <section className="mb-10 sm:mb-12" data-testid="finance-controller-panel">
      <SectionLabel
        title="Finance Controller Agent"
        description="Closes one finance-ops loop over the reconciliation batch: classify exceptions, prioritize review, gate simulated actions behind human approval."
      />

      <WorkflowStrip />

      <div className="mb-6">
        <DemoReadiness
          onReset={() => {
            onAgentRunClear?.();
            setPlanFromRun(null);
            onRetry?.();
          }}
        />
      </div>

      {requireManualRun && orderResults && orderResults.length > 0 ? (
        <AgentRunLauncher
          stageDelayMs={import.meta.env.MODE === "test" ? 0 : 180}
          orderResults={orderResults}
          latestRun={data && isAgentRun(data) ? data : null}
          onClearResults={() => {
            onAgentRunClear?.();
            setPlanFromRun(null);
          }}
          onComplete={(run, plan) => {
            setPlanFromRun(plan);
            onAgentRunComplete?.(run);
          }}
        />
      ) : null}

      {loading && !data ? (
        <LoadingState label="Running Finance Controller on reconciliation results…" />
      ) : null}

      {error && !data ? <ErrorState message={error} onRetry={onRetry} /> : null}

      {requireManualRun && !data && !loading ? (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <p
            className="rounded-xl border border-dashed border-[var(--color-border)] bg-white px-5 py-6 text-center text-sm text-[var(--color-muted)]"
            data-testid="agent-run-awaiting"
          >
            Run the Finance Controller Agent to analyze this batch, generate decisions, and build the
            prioritized work queue.
          </p>
          <ArchitectureFlow />
        </div>
      ) : null}

      {data && showResults ? (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="min-w-0">
            {isAgentRun(data) ? <AgentRunSummary data={data} /> : null}

            {!isAgentRun(data) ? (
              <div
                className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5"
                data-testid="finance-controller-metrics"
              >
                <MetricCard
                  value={data.records_processed}
                  label="Records processed"
                  accent="brand"
                />
                <MetricCard value={data.no_action_count} label="No action" accent="success" />
                <MetricCard
                  value={data.review_required_count}
                  label="Review required"
                  accent={data.review_required_count > 0 ? "warning" : "default"}
                />
                <MetricCard
                  value={data.exception_count}
                  label="Exceptions"
                  accent={data.exception_count > 0 ? "danger" : "default"}
                />
                <MetricCard
                  value={data.unresolved_count}
                  label="Unresolved"
                  accent={data.unresolved_count > 0 ? "warning" : "default"}
                />
              </div>
            ) : null}

            <div className="rounded-xl border border-[var(--color-border)] bg-white px-5 py-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
              <p className="mb-1 text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
                Decision distribution
              </p>
              <p className="mb-4 text-xs text-[var(--color-muted)]">
                Operational batch only — not held-out evaluation accuracy.
              </p>
              <DecisionBreakdown
                decisionsByType={data.decisions_by_type}
                total={data.records_processed}
              />
            </div>

            {isAgentRun(data) ? (
              <>
                <ExceptionSummary
                  decisions={data.decisions}
                  unresolvedCount={data.unresolved_count}
                  recordsProcessed={data.records_processed}
                />
                <div id={approvalRefId}>
                  <AgentWorkQueue
                    orderResults={orderResults}
                    initialPlan={planFromRun}
                    refreshToken={data.run_id}
                  />
                  <ApprovalQueue runId={data.run_id} orderResults={orderResults} onChanged={onRetry} />
                </div>
                <HeldOutEvaluationStrip />
              </>
            ) : null}

            {error ? (
              <p className="mt-3 text-xs text-[var(--color-warning)]">
                Latest refresh failed ({error}). Showing last successful agent batch.
              </p>
            ) : null}
            {loading ? (
              <p className="mt-3 text-xs text-[var(--color-muted)]">Refreshing agent decisions…</p>
            ) : null}
          </div>

          <ArchitectureFlow />
        </div>
      ) : null}
    </section>
  );
}

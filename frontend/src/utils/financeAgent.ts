import type {
  FinanceAgentDecisionTrace,
  FinanceControllerDecision,
} from "../types/api";

/** Adapt a run-agent decision trace for existing Agent Decision UI. */
export function decisionFromTrace(
  trace: FinanceAgentDecisionTrace,
): FinanceControllerDecision {
  const action = trace.proposed_action ?? "none";
  const reason = trace.agent_reason ?? trace.rationale;
  const evidence = trace.audit_evidence_summary ?? {};
  return {
    order_id: trace.order_id,
    original_status: trace.original_result.status,
    original_reconciled: trace.original_result.reconciled,
    confidence_score: trace.original_result.confidence_score,
    exception_types: [...trace.triggered_exceptions],
    decision: trace.decision,
    action,
    reason,
    evidence,
    requires_approval: trace.requires_approval,
    provider: trace.provider,
    agent: trace.agent,
    agent_version: trace.agent_version,
    original_result: { ...trace.original_result },
    agent_decision: {
      decision: trace.decision,
      action,
      reason,
      requires_approval: trace.requires_approval,
      evidence,
      provider: trace.provider,
      agent: trace.agent,
      agent_version: trace.agent_version,
    },
  };
}

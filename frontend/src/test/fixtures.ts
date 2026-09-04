import type {
  FinanceAgentDecisionTrace,
  FinanceAgentRunResponse,
  FinanceControllerDecision,
  FinanceControllerOriginalResult,
  FinanceControllerRunResponse,
  ReconciliationReport,
} from "../types/api";
import { vi } from "vitest";

function makeOrder(
  id: string,
  overrides: Partial<ReconciliationReport["order_results"][number]> = {},
) {
  return {
    order_id: id,
    status: "reconciled" as const,
    reconciled: true,
    confidence_score: 90,
    order_amount_paise: 100000,
    settlement_ids_considered: ["SET_0001"],
    primary_settlement_id: "SET_0001",
    secondary_settlement_ids: [],
    refund_ids: [],
    total_refund_paise: 0,
    bank_transaction_ids_considered: ["BNK_0001"],
    valid_bank_transaction_id: "BNK_0001",
    normalized_references: {},
    amount_comparison: {
      order_amount_paise: 100000,
      settlement_gross_paise: 100000,
      settlement_net_paise: 95000,
      bank_amount_paise: 95000,
      expected_post_refund_gross_paise: 100000,
      total_refund_paise: 0,
      settlement_gross_matches_order: true,
      settlement_reflects_refund: null,
      bank_matches_settlement_net: true,
    },
    timestamp_comparison: {
      settlement_settled_at: "2024-01-01T10:00:00",
      bank_transaction_date: "2024-01-01T11:00:00",
      difference_hours: 1,
      tolerance_hours: 24,
      within_tolerance: true,
    },
    rules_triggered: ["amount_match"],
    exceptions: [],
    audit_trail: ["Order evaluated"],
    ...overrides,
  };
}

export const mockReport: ReconciliationReport = {
  metadata: {
    engine: "recon-engine",
    generated_at: "2024-06-01T12:00:00Z",
    evaluation_grain: "order",
    currency: "INR",
    minor_unit: "paise",
  },
  configuration: {
    timestamp_tolerance_hours: 24,
    reference_normalization: {},
    reconciliation_status_vocabulary: [],
    exception_vocabulary: [],
  },
  summary: {
    total_orders: 15,
    reconciled_orders: 10,
    unreconciled_orders: 5,
    missing_settlements: 1,
    missing_bank_transactions: 1,
    settlement_amount_mismatches: 1,
    bank_amount_mismatches: 0,
    timestamp_violations: 0,
    refund_mismatches: 0,
    refund_adjusted: 0,
    duplicate_settlements: 0,
    duplicate_bank_transactions: 0,
    orphan_bank_transactions: 0,
    reference_variations: 0,
  },
  status_counts: {
    reconciled: 8,
    unreconciled_missing_settlement: 1,
    unreconciled_missing_bank: 1,
    unreconciled_settlement_amount: 1,
  },
  order_results: [
    ...Array.from({ length: 10 }, (_, i) =>
      makeOrder(`ORD_${String(i + 1).padStart(4, "0")}`, {
        confidence_score: 50 + i * 3,
      }),
    ),
    makeOrder("ORD_0011", {
      status: "unreconciled_missing_settlement",
      reconciled: false,
      confidence_score: 30,
      primary_settlement_id: null,
      valid_bank_transaction_id: null,
      exceptions: [
        { type: "MISSING_SETTLEMENT", message: "No settlement found" },
      ],
    }),
    makeOrder("ORD_0012", {
      status: "unreconciled_missing_bank",
      reconciled: false,
      confidence_score: 40,
      valid_bank_transaction_id: null,
      exceptions: [
        { type: "MISSING_BANK_TRANSACTION", message: "No bank transaction found" },
      ],
    }),
    makeOrder("ORD_0013", {
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 85,
      exceptions: [
        {
          type: "SETTLEMENT_AMOUNT_MISMATCH",
          message: "Settlement gross does not match order",
        },
      ],
    }),
    makeOrder("ORD_0014", {
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 20,
      exceptions: [
        {
          type: "SETTLEMENT_AMOUNT_MISMATCH",
          message: "Settlement gross does not match order",
        },
      ],
    }),
    makeOrder("ORD_0015", {
      status: "reconciled",
      reconciled: true,
      confidence_score: 95,
    }),
  ],
  global_exceptions: [],
};

export function mockHookState<T>(data: T) {
  return {
    data,
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
  };
}

export const mockSummary = {
  total_orders: 100,
  reconciled_orders: 52,
  unreconciled_orders: 48,
  status_counts: {
    reconciled: 22,
    reconciled_within_timestamp_tolerance: 30,
    unreconciled_missing_settlement: 8,
    unreconciled_missing_bank: 10,
    unreconciled_settlement_amount: 10,
  },
  exception_counts: {
    missing_settlements: 8,
    missing_bank_transactions: 10,
    settlement_amount_mismatches: 10,
    bank_amount_mismatches: 10,
    timestamp_violations: 2,
    refund_mismatches: 10,
    refund_adjusted: 10,
    duplicate_settlements: 8,
    duplicate_bank_transactions: 10,
    orphan_bank_transactions: 8,
    reference_variations: 10,
  },
};

export function makeFinanceDecision(
  orderId: string,
  decision: string,
  overrides: Partial<FinanceControllerDecision> = {},
): FinanceControllerDecision {
  const requiresApproval = overrides.requires_approval ?? decision !== "NO_ACTION";
  const originalStatus = overrides.original_status ?? "reconciled";
  const originalReconciled = overrides.original_reconciled ?? true;
  const confidence = overrides.confidence_score ?? 90;
  const exceptionTypes = overrides.exception_types ?? [];
  const reason = overrides.reason ?? `Policy decision ${decision} for ${orderId}`;
  const action = overrides.action ?? decision.toLowerCase();
  const evidence = overrides.evidence ?? { exception_types: exceptionTypes };
  return {
    order_id: orderId,
    original_status: originalStatus,
    original_reconciled: originalReconciled,
    confidence_score: confidence,
    exception_types: exceptionTypes,
    decision,
    action,
    reason,
    evidence,
    requires_approval: requiresApproval,
    provider: "deterministic_policy",
    agent: "reconengine-finance-controller",
    agent_version: "1.0.0",
    original_result: {
      order_id: orderId,
      status: originalStatus,
      reconciled: originalReconciled,
      confidence_score: confidence,
      exception_types: exceptionTypes,
    },
    agent_decision: {
      decision,
      action,
      reason,
      requires_approval: requiresApproval,
      evidence,
      provider: "deterministic_policy",
      agent: "reconengine-finance-controller",
      agent_version: "1.0.0",
    },
  };
}

/** Matches the verified live 100-record Finance Controller batch metrics. */
export const mockFinanceControllerBatch: FinanceControllerRunResponse = {
  agent: "reconengine-finance-controller",
  agent_version: "1.0.0",
  provider: "deterministic_policy",
  records_processed: 100,
  no_action_count: 40,
  review_required_count: 60,
  exception_count: 100,
  unresolved_count: 60,
  decisions_by_type: {
    NO_ACTION: 40,
    FLAG_FOR_REVIEW: 32,
    ESCALATE_MISSING_BANK: 10,
    VERIFY_REFUND: 10,
    ESCALATE_MISSING_SETTLEMENT: 8,
  },
  decisions: [
    makeFinanceDecision("ORD_0001", "NO_ACTION"),
    makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_status: "unreconciled_settlement_amount",
      original_reconciled: false,
      exception_types: ["BANK_AMOUNT_MISMATCH"],
    }),
    makeFinanceDecision("ORD_0003", "ESCALATE_MISSING_BANK", {
      original_status: "unreconciled_missing_bank",
      original_reconciled: false,
      exception_types: ["MISSING_BANK_TRANSACTION"],
    }),
    makeFinanceDecision("ORD_0033", "VERIFY_REFUND", {
      original_status: "reconciled_with_refund_adjustment",
      original_reconciled: true,
      exception_types: ["REFUND_ADJUSTED"],
    }),
    makeFinanceDecision("ORD_0024", "ESCALATE_MISSING_SETTLEMENT", {
      original_status: "unreconciled_missing_settlement",
      original_reconciled: false,
      exception_types: ["MISSING_SETTLEMENT"],
    }),
  ],
  data_source: "provided_order_results",
};

function makeDecisionTrace(
  orderId: string,
  decision: string,
  overrides: Partial<FinanceAgentDecisionTrace> = {},
): FinanceAgentDecisionTrace {
  const requiresApproval = overrides.requires_approval ?? decision !== "NO_ACTION";
  const original =
    overrides.original_result ??
    ({
      order_id: orderId,
      status: "reconciled",
      reconciled: true,
      confidence_score: 90,
      exception_types: [],
    } satisfies FinanceControllerOriginalResult);
  const proposed =
    overrides.proposed_action !== undefined
      ? overrides.proposed_action
      : decision === "NO_ACTION"
        ? null
        : decision === "FLAG_FOR_REVIEW"
          ? "RECORD_REVIEW"
          : decision === "VERIFY_REFUND"
            ? "RECORD_REFUND_VERIFICATION"
            : decision === "ESCALATE_MISSING_BANK"
              ? "RECORD_MISSING_BANK_ESCALATION"
              : "RECORD_MISSING_SETTLEMENT_ESCALATION";
  return {
    order_id: orderId,
    original_result: original,
    audit_evidence_summary: overrides.audit_evidence_summary ?? {
      status: original.status,
      reconciled: original.reconciled,
      confidence_score: original.confidence_score,
      exception_types: original.exception_types,
    },
    triggered_exceptions: overrides.triggered_exceptions ?? [...original.exception_types],
    decision,
    rationale:
      overrides.rationale ??
      (decision === "NO_ACTION"
        ? "Reconciliation is successful and no blocking exception requires intervention."
        : `Policy rationale for ${decision}`),
    agent_reason: overrides.agent_reason ?? `Policy decision ${decision} for ${orderId}`,
    requires_approval: requiresApproval,
    proposed_action: proposed,
    timestamp: overrides.timestamp ?? "2026-09-04T12:00:00Z",
    provider: overrides.provider ?? "deterministic_policy",
    agent: overrides.agent ?? "reconengine-finance-controller",
    agent_version: overrides.agent_version ?? "1.0.0",
  };
}

/** Agent workflow envelope matching production 100-record metrics. */
export const mockFinanceAgentRun: FinanceAgentRunResponse = {
  run_id: "FCRUN_test100batch",
  started_at: "2026-09-04T12:00:00Z",
  completed_at: "2026-09-04T12:00:01Z",
  elapsed_seconds: 0.042,
  records_processed: 100,
  no_action_count: 40,
  review_required_count: 60,
  unresolved_count: 60,
  exception_count: 100,
  pending_approval_count: 60,
  decisions_by_type: { ...mockFinanceControllerBatch.decisions_by_type },
  decisions: [
    makeDecisionTrace("ORD_0001", "NO_ACTION"),
    makeDecisionTrace("ORD_0002", "FLAG_FOR_REVIEW", {
      original_result: {
        order_id: "ORD_0002",
        status: "unreconciled_settlement_amount",
        reconciled: false,
        confidence_score: 40,
        exception_types: ["BANK_AMOUNT_MISMATCH"],
      },
      rationale: "Amount mismatch detected; financial result requires human review.",
      proposed_action: "RECORD_REVIEW",
    }),
    makeDecisionTrace("ORD_0003", "ESCALATE_MISSING_BANK", {
      original_result: {
        order_id: "ORD_0003",
        status: "unreconciled_missing_bank",
        reconciled: false,
        confidence_score: 35,
        exception_types: ["MISSING_BANK_TRANSACTION"],
      },
      rationale: "Bank transaction is missing; escalation is required.",
      proposed_action: "RECORD_MISSING_BANK_ESCALATION",
    }),
    makeDecisionTrace("ORD_0033", "VERIFY_REFUND", {
      original_result: {
        order_id: "ORD_0033",
        status: "reconciled_with_refund_adjustment",
        reconciled: true,
        confidence_score: 95,
        exception_types: ["REFUND_ADJUSTED"],
      },
      rationale: "Refund-adjusted exception detected; refund state requires verification.",
      proposed_action: "RECORD_REFUND_VERIFICATION",
    }),
    makeDecisionTrace("ORD_0024", "ESCALATE_MISSING_SETTLEMENT", {
      original_result: {
        order_id: "ORD_0024",
        status: "unreconciled_missing_settlement",
        reconciled: false,
        confidence_score: 20,
        exception_types: ["MISSING_SETTLEMENT"],
      },
      rationale: "Settlement is missing; escalation is required.",
      proposed_action: "RECORD_MISSING_SETTLEMENT_ESCALATION",
    }),
  ],
  data_source: "production_reconciliation_report",
  provider: "deterministic_policy",
  agent: "reconengine-finance-controller",
  agent_version: "1.0.0",
};

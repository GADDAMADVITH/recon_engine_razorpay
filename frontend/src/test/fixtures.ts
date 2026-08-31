import type { ReconciliationReport } from "../types/api";
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
  total_orders: 50,
  reconciled_orders: 26,
  unreconciled_orders: 24,
  status_counts: {
    reconciled: 26,
    unreconciled_missing_settlement: 8,
    unreconciled_missing_bank: 6,
    unreconciled_settlement_amount: 10,
  },
  exception_counts: {
    missing_settlements: 4,
    missing_bank_transactions: 3,
    settlement_amount_mismatches: 2,
    bank_amount_mismatches: 1,
    timestamp_violations: 2,
    refund_mismatches: 1,
    refund_adjusted: 0,
    duplicate_settlements: 1,
    duplicate_bank_transactions: 0,
    orphan_bank_transactions: 0,
    reference_variations: 2,
  },
};

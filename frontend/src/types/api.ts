import type { ExceptionType, ReconciliationStatus } from "./reconciliation";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface ReconciliationSummary {
  total_orders: number;
  reconciled_orders: number;
  unreconciled_orders: number;
  status_counts: Record<string, number>;
  exception_counts: Record<string, number>;
}

export interface AmountComparison {
  order_amount_paise: number;
  settlement_gross_paise: number | null;
  settlement_net_paise: number | null;
  bank_amount_paise: number | null;
  expected_post_refund_gross_paise: number | null;
  total_refund_paise: number;
  settlement_gross_matches_order: boolean | null;
  settlement_reflects_refund: boolean | null;
  bank_matches_settlement_net: boolean | null;
}

export interface TimestampComparison {
  settlement_settled_at: string | null;
  bank_transaction_date: string | null;
  difference_hours: number | null;
  tolerance_hours: number;
  within_tolerance: boolean | null;
}

export interface OrderException {
  type: ExceptionType;
  message: string;
  details?: Record<string, unknown>;
}

export interface OrderResult {
  order_id: string;
  status: ReconciliationStatus;
  reconciled: boolean;
  confidence_score: number;
  order_amount_paise: number;
  settlement_ids_considered: string[];
  primary_settlement_id: string | null;
  secondary_settlement_ids: string[];
  refund_ids: string[];
  total_refund_paise: number;
  bank_transaction_ids_considered: string[];
  valid_bank_transaction_id: string | null;
  normalized_references: Record<string, string>;
  amount_comparison: AmountComparison;
  timestamp_comparison: TimestampComparison;
  rules_triggered: string[];
  exceptions: OrderException[];
  audit_trail: string[];
}

export interface GlobalException {
  type: string;
  message: string;
  bank_transaction_id?: string;
  settlement_ref?: string;
  related_order_id?: string;
  settlement_id?: string;
  order_id?: string;
  amount_paise?: number;
  source_settlement_id?: string;
  is_valid_bank_link?: boolean;
}

export interface ReconciliationReport {
  metadata: {
    engine: string;
    generated_at: string;
    evaluation_grain: string;
    currency: string;
    minor_unit: string;
  };
  configuration: {
    timestamp_tolerance_hours: number;
    reference_normalization: Record<string, string>;
    reconciliation_status_vocabulary: string[];
    exception_vocabulary: string[];
  };
  summary: {
    total_orders: number;
    reconciled_orders: number;
    unreconciled_orders: number;
    missing_settlements: number;
    missing_bank_transactions: number;
    settlement_amount_mismatches: number;
    bank_amount_mismatches: number;
    timestamp_violations: number;
    refund_mismatches: number;
    refund_adjusted: number;
    duplicate_settlements: number;
    duplicate_bank_transactions: number;
    orphan_bank_transactions: number;
    reference_variations: number;
  };
  status_counts: Record<string, number>;
  order_results: OrderResult[];
  global_exceptions: GlobalException[];
}

export interface EvaluationResponse {
  metadata: {
    evaluator: string;
    evaluation_grain: string;
    orders_evaluated: number;
    report_generated_at: string;
    ground_truth_generated_at: string;
    evaluation_policy: Record<string, unknown>;
  };
  summary: {
    orders_evaluated: number;
    binary_accuracy: number;
    binary_precision: number;
    binary_recall: number;
    binary_f1_score: number;
    strict_status_accuracy: number;
    relaxed_status_accuracy: number;
    primary_settlement_match_rate: number;
    primary_bank_match_rate: number;
    valid_bank_set_match_rate: number;
  };
  binary_classification: {
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    true_negatives: number;
    accuracy: number;
    precision: number;
    recall: number;
    f1_score: number;
    mismatch_count: number;
    mismatches: unknown[];
  };
  status_evaluation: {
    strict: {
      correct: number;
      incorrect: number;
      accuracy: number;
      mismatches: unknown[];
    };
    relaxed: {
      equivalence_policy: string[];
      correct: number;
      incorrect: number;
      accuracy: number;
      mismatches: unknown[];
    };
  };
  scenario_evaluation: Record<
    string,
    {
      total_orders: number;
      binary_correct: number;
      binary_accuracy: number;
      strict_status_correct: number;
      strict_status_accuracy: number;
      relaxed_status_correct: number;
      relaxed_status_accuracy: number;
      primary_settlement_match_count: number;
      primary_settlement_match_rate: number;
      primary_bank_match_count: number;
      primary_bank_match_rate: number;
    }
  >;
  link_level_evaluation: Record<string, unknown>;
  global_exception_evaluation: Record<string, unknown>;
  amount_validation: Record<string, unknown>;
}

export interface ApiError {
  detail: string;
}

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

export interface ReconciliationReportMetadata {
  engine: string;
  generated_at: string;
  evaluation_grain: string;
  currency: string;
  minor_unit: string;
  /** Present on API reports: "csv" | "razorpay". Optional for backward compatibility. */
  data_source?: "csv" | "razorpay";
  /** Explicit bank-side provenance when not from the primary data source. */
  bank_source?: string;
  bank_source_note?: string;
  /** Number of bank transaction rows imported (set by the import-bank endpoint). */
  bank_rows_imported?: number;
}

export interface ReconciliationReport {
  metadata: ReconciliationReportMetadata;
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

export type RazorpaySyncStatus = "success" | "empty" | "partial";

/** Compact Razorpay-side entity summaries returned by the sync envelope (not bank rows). */
export interface RazorpaySyncOrderSummary {
  order_id: string;
  amount_paise: number;
  created_at: string;
}

export interface RazorpaySyncSettlementSummary {
  settlement_id: string;
  order_id: string;
  gross_amount_paise: number;
  fee_paise: number;
  tax_paise: number;
  net_amount_paise: number;
  settled_at: string;
}

export interface RazorpaySyncRefundSummary {
  refund_id: string;
  order_id: string;
  refund_amount_paise: number;
  created_at: string;
}

/**
 * Envelope from POST /api/v1/sources/razorpay/sync.
 * Nested `reconciliation` reuses ReconciliationReport when present; never invent bank data.
 */
export interface RazorpaySyncResponse {
  source: "razorpay";
  status: RazorpaySyncStatus;
  orders_fetched: number;
  payments_fetched: number;
  refunds_fetched: number;
  settlements_fetched: number;
  recon_items_fetched: number;
  bank_data_available: boolean;
  bank_transactions_fetched: number;
  orders: RazorpaySyncOrderSummary[];
  settlements: RazorpaySyncSettlementSummary[];
  refunds: RazorpaySyncRefundSummary[];
  mapping_warnings: string[];
  mapping_errors: string[];
  reconciliation: ReconciliationReport | null;
}

/** Structured audit check from GET /api/v1/reconciliation/{order_id}/audit. */
export interface AuditCheck {
  rule: string;
  label: string;
  passed: boolean;
  outcome: string;
  exception_type: string | null;
  exception: OrderException | null;
}

export interface AuditTimestampCheck {
  label: string;
  passed: boolean;
  difference_hours?: number | null;
  tolerance_hours?: number | null;
  outcome?: string;
}

export interface AuditReferences {
  settlement_ids_considered: string[];
  primary_settlement_id: string | null;
  secondary_settlement_ids: string[];
  bank_transaction_ids_considered: string[];
  valid_bank_transaction_id: string | null;
  refund_ids: string[];
  normalized_references: Record<string, string>;
}

export interface AuditAmountSummary {
  order_amount_paise: number | null;
  settlement_gross_paise: number | null;
  settlement_net_paise: number | null;
  bank_amount_paise: number | null;
  total_refund_paise: number;
  settlement_gross_matches_order: boolean | null;
  bank_matches_settlement_net: boolean | null;
  settlement_reflects_refund: boolean | null;
}

/** Structured audit trail response. */
export interface StructuredAuditResponse {
  order_id: string;
  status: string;
  reconciled: boolean;
  confidence_score: number;
  order_amount_paise: number | null;
  checks: AuditCheck[];
  timestamp_check: AuditTimestampCheck | null;
  amount_summary: AuditAmountSummary;
  references: AuditReferences;
  exceptions: OrderException[];
  timeline: string[];
}

/** Grounded natural-language explanation from GET /reconciliation/{order_id}/audit/explain. */
export interface AuditExplanationResponse {
  order_id: string;
  status: string;
  reconciled: boolean;
  confidence_score: number;
  explanation: string;
  provider: "gemini";
  model: string | null;
}

/** Conversational reply from POST /api/v1/chat. */
export interface ChatResponse {
  message: string;
  provider: "gemini";
  model: string | null;
}

/** Scenario outcome from POST /api/v1/sources/razorpay/reconcile-demo. */
export interface RazorpayDemoScenarioResult {
  scenario_id: string;
  order_id: string;
  description: string;
  expected_status: string;
  expected_reconciled: boolean;
  actual_status: string;
  actual_reconciled: boolean;
  matched_expectation: boolean;
}

/**
 * Envelope from POST /api/v1/sources/razorpay/reconcile-demo.
 * Bank rows are synthetic fixtures — never live Razorpay bank data.
 */
export interface RazorpayReconcileDemoResponse {
  source: "razorpay";
  bank_source: string;
  bank_source_note: string;
  status: string;
  scenario_count: number;
  scenarios: RazorpayDemoScenarioResult[];
  reconciliation: ReconciliationReport;
}

/** Allowlisted Finance Controller decisions (advisory / read-only). */
export type FinanceControllerDecisionType =
  | "NO_ACTION"
  | "FLAG_FOR_REVIEW"
  | "VERIFY_REFUND"
  | "ESCALATE_MISSING_BANK"
  | "ESCALATE_MISSING_SETTLEMENT";

/** Original reconciliation facts preserved beside the agent decision. */
export interface FinanceControllerOriginalResult {
  order_id: string;
  status: string;
  reconciled: boolean;
  confidence_score: number;
  exception_types: string[];
}

/** Agent decision envelope — never overwrites reconciliation facts. */
export interface FinanceControllerAgentDecision {
  decision: FinanceControllerDecisionType | string;
  action: string;
  reason: string;
  requires_approval: boolean;
  evidence: Record<string, unknown>;
  provider?: string;
  agent?: string;
  agent_version?: string;
}

/**
 * One order decision from POST /api/v1/finance-controller/run.
 * Flat fields mirror the agent payload; nested envelopes make ORIGINAL vs AGENT explicit.
 */
export interface FinanceControllerDecision {
  order_id: string;
  original_status: string;
  original_reconciled: boolean;
  confidence_score: number;
  exception_types: string[];
  decision: FinanceControllerDecisionType | string;
  action: string;
  reason: string;
  evidence: Record<string, unknown>;
  requires_approval: boolean;
  provider?: string;
  agent?: string;
  agent_version?: string;
  original_result: FinanceControllerOriginalResult;
  agent_decision: FinanceControllerAgentDecision;
}

/** Batch response from POST /api/v1/finance-controller/run. */
export interface FinanceControllerRunResponse {
  agent: string;
  agent_version: string;
  provider: string;
  records_processed: number;
  no_action_count: number;
  review_required_count: number;
  exception_count: number;
  unresolved_count: number;
  decisions_by_type: Record<string, number>;
  decisions: FinanceControllerDecision[];
  data_source?: string;
}

/** Optional body — omit/empty to run on the production reconciliation report. */
export interface FinanceControllerRunRequest {
  order_results?: OrderResult[] | null;
}

/** Simulated, record-only action from POST /api/v1/finance-controller/actions/approve. */
export interface FinanceActionRecordResponse {
  action_id: string;
  order_id: string;
  agent_decision: string;
  action_type: string;
  approval_required: boolean;
  approval_status: "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | string;
  action_status: "PENDING" | "RECORDED" | "REJECTED" | string;
  created_at: string;
  approved_at: string | null;
  evidence: Record<string, unknown>;
  audit_event: Record<string, unknown>;
  simulated: boolean;
  money_moved: boolean;
  note: string;
  idempotent_replay?: boolean;
  original_result_unchanged?: boolean;
}

export interface FinanceControllerApproveRequest {
  order_id: string;
  agent_decision: string;
  order_result?: OrderResult | null;
  run_id?: string | null;
}

export interface FinanceControllerRejectRequest {
  order_id: string;
  agent_decision: string;
  order_result?: OrderResult | null;
  run_id?: string | null;
}

/** One decision trace from POST /api/v1/finance-controller/run-agent. */
export interface FinanceAgentDecisionTrace {
  order_id: string;
  original_result: FinanceControllerOriginalResult;
  audit_evidence_summary: Record<string, unknown>;
  triggered_exceptions: string[];
  decision: FinanceControllerDecisionType | string;
  rationale: string;
  agent_reason?: string;
  requires_approval: boolean;
  proposed_action: string | null;
  timestamp: string;
  provider?: string;
  agent?: string;
  agent_version?: string;
}

/** Agent workflow envelope from POST /api/v1/finance-controller/run-agent. */
export interface FinanceAgentRunResponse {
  run_id: string;
  started_at: string;
  completed_at: string;
  elapsed_seconds: number;
  records_processed: number;
  no_action_count: number;
  review_required_count: number;
  unresolved_count: number;
  exception_count?: number;
  pending_approval_count: number;
  decisions_by_type: Record<string, number>;
  decisions: FinanceAgentDecisionTrace[];
  data_source?: string;
  provider?: string;
  agent?: string;
  agent_version?: string;
}

/** Human-in-the-loop lifecycle metrics for a run. */
export interface FinanceLifecycleMetrics {
  run_id: string | null;
  timestamp?: string;
  total_decisions: number;
  no_action: number;
  pending_approval: number;
  approved: number;
  rejected: number;
  recorded: number;
  unresolved: number;
  review_required?: number;
  decisions_by_type?: Record<string, number>;
}

export interface FinanceApprovalQueueItem {
  run_id: string;
  order_id: string;
  decision: string;
  rationale: string;
  proposed_action: string | null;
  exceptions: string[];
  original_result: FinanceControllerOriginalResult;
  requires_approval: boolean;
  approval_status: string;
  action_status: string;
  lifecycle_status: string;
  timestamp: string;
}

export interface FinanceApprovalQueueResponse {
  run_id: string | null;
  pending_count: number;
  items: FinanceApprovalQueueItem[];
  lifecycle: FinanceLifecycleMetrics;
}

export interface FinanceAgentRunHistoryItem {
  run_id: string;
  timestamp: string;
  records_processed: number;
  no_action_count: number;
  review_required_count: number;
  pending_approval_count: number;
  unresolved_count: number;
  decisions_by_type: Record<string, number>;
  completed_action_count: number;
  approved_action_count: number;
  rejected_action_count: number;
  recorded_action_count: number;
  pending_action_count: number;
}

/** Batch analysis from POST /api/v1/finance-controller/agent-plan. */
export interface FinanceBatchAnalysis {
  records_processed: number;
  reconciled_count: number;
  exception_count: number;
  unresolved_count: number;
  decisions_by_type: Record<string, number>;
  approval_required_count: number;
  no_action_count?: number;
  review_required_count?: number;
}

export interface FinanceWorkQueueItem {
  order_id: string;
  priority: number;
  priority_reason?: string;
  decision: string;
  exceptions: string[];
  rationale: string;
  proposed_action: string | null;
  requires_approval: boolean;
  original_result: FinanceControllerOriginalResult;
  evidence_reference?: Record<string, unknown>;
  timestamp?: string;
}

export interface FinanceAgentPlanBody {
  objective: string;
  observations: string[];
  prioritized_work: Array<{
    order_id: string;
    priority: number;
    decision: string;
    proposed_action: string | null;
    rationale: string;
  }>;
  proposed_actions: Array<{ action: string; count: number }>;
  unresolved_cases: {
    count: number;
    by_decision: Record<string, number>;
    by_exception: Record<string, number>;
  };
  human_approval_requirements: {
    required_count: number;
    rule: string;
    state_machine?: string;
    money_moved: boolean;
  };
  note?: string;
}

export interface FinanceAgentPlanResponse {
  run_id: string;
  records_processed: number;
  batch_analysis: FinanceBatchAnalysis;
  prioritized_work_queue: FinanceWorkQueueItem[];
  agent_plan: FinanceAgentPlanBody;
  decisions_by_type: Record<string, number>;
  unresolved_count: number;
  pending_approval_count: number;
  unresolved_groups?: {
    by_decision: Record<string, string[]>;
    by_exception: Record<string, string[]>;
    decision_group_counts: Record<string, number>;
    exception_group_counts: Record<string, number>;
  };
  money_moved?: boolean;
  data_source?: string;
}

/** Held-out Finance Controller evaluation (separate from operational batch). */
export interface FinanceControllerEvaluationResponse {
  dataset: string;
  held_out: boolean;
  label_source?: string;
  measurement_note: string;
  records_evaluated: number;
  correct_decisions: number;
  incorrect_decisions: number;
  accuracy: number;
  throughput?: {
    records_processed: number;
    elapsed_seconds: number;
    records_per_second: number | null;
  };
  per_decision?: Record<string, unknown>;
  errors?: unknown[];
}

export interface FinanceDemoStatusResponse {
  ready: boolean;
  checks: {
    api_reachable: boolean;
    reconciliation_data_available: boolean;
    agent_endpoint_available: boolean;
    evaluation_endpoint_available: boolean;
  };
  operational_batch: { label: string; records: number };
  held_out_evaluation: {
    label: string;
    records_evaluated: number;
    accuracy: number | null;
    measurement_note?: string;
  };
  money_moved: boolean;
  simulated_actions_only: boolean;
  human_approval_required: boolean;
  gemini_in_decision_path: boolean;
  secrets_exposed: boolean;
}

export interface FinanceDemoResetResponse {
  reset: boolean;
  scope: string;
  datasets_untouched: boolean;
  evaluation_untouched: boolean;
  policy_untouched: boolean;
  reconciliation_untouched: boolean;
  money_moved: boolean;
  secrets_exposed: boolean;
  note: string;
}

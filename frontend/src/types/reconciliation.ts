export type ReconciliationStatus =
  | "reconciled"
  | "reconciled_within_timestamp_tolerance"
  | "unreconciled_timestamp_exceeded"
  | "unreconciled_settlement_amount"
  | "unreconciled_missing_settlement"
  | "unreconciled_missing_bank"
  | "reconciled_with_refund_adjustment"
  | "unreconciled_refund_not_adjusted"
  | "reconciled_with_reference_variation"
  | "partially_reconciled_duplicate_settlement";

export type ExceptionType =
  | "MISSING_SETTLEMENT"
  | "MISSING_BANK_TRANSACTION"
  | "SETTLEMENT_AMOUNT_MISMATCH"
  | "BANK_AMOUNT_MISMATCH"
  | "TIMESTAMP_OUTSIDE_TOLERANCE"
  | "TIMESTAMP_WITHIN_TOLERANCE"
  | "REFUND_NOT_REFLECTED"
  | "REFUND_ADJUSTED"
  | "DUPLICATE_SETTLEMENT"
  | "DUPLICATE_BANK_TRANSACTION"
  | "ORPHAN_BANK_TRANSACTION"
  | "REFERENCE_VARIATION";

export const SEVERE_EXCEPTIONS: ExceptionType[] = [
  "MISSING_SETTLEMENT",
  "MISSING_BANK_TRANSACTION",
  "SETTLEMENT_AMOUNT_MISMATCH",
  "BANK_AMOUNT_MISMATCH",
  "TIMESTAMP_OUTSIDE_TOLERANCE",
  "REFUND_NOT_REFLECTED",
  "DUPLICATE_SETTLEMENT",
  "DUPLICATE_BANK_TRANSACTION",
  "ORPHAN_BANK_TRANSACTION",
];

export const INFO_EXCEPTIONS: ExceptionType[] = [
  "TIMESTAMP_WITHIN_TOLERANCE",
  "REFUND_ADJUSTED",
  "REFERENCE_VARIATION",
];

import { clsx, type ClassValue } from "clsx";
import { INFO_EXCEPTIONS, SEVERE_EXCEPTIONS, type ExceptionType } from "../types/reconciliation";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatPaise(paise: number, currency = "INR"): string {
  const amount = paise / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatStatusLabel(status: string): string {
  const words = status
    .replace(/^unreconciled_/, "")
    .replace(/^reconciled_/, "")
    .replace(/_/g, " ")
    .toLowerCase();
  return words.replace(/^\w/, (c) => c.toUpperCase());
}

/** Sentence-case label for exception enum types (e.g. MISSING_SETTLEMENT → "Missing settlement"). */
export function formatExceptionLabel(type: string): string {
  const words = type.replace(/_/g, " ").toLowerCase();
  return words.replace(/^\w/, (c) => c.toUpperCase());
}

/** Human-readable Finance Controller decision (e.g. FLAG_FOR_REVIEW → "Flag for review"). */
export function formatAgentDecisionLabel(decision: string): string {
  const words = decision.replace(/_/g, " ").toLowerCase();
  return words.replace(/^\w/, (c) => c.toUpperCase());
}

export function getPrimaryException(
  exceptions: { type: string }[],
): string | null {
  if (!exceptions.length) return null;
  const severe = exceptions.find((e) =>
    SEVERE_EXCEPTIONS.includes(e.type as ExceptionType),
  );
  return (severe ?? exceptions[0]).type;
}

export function getExceptionSeverity(
  type: string,
): "critical" | "warning" | "info" {
  if (SEVERE_EXCEPTIONS.includes(type as ExceptionType)) return "critical";
  if (INFO_EXCEPTIONS.includes(type as ExceptionType)) return "info";
  return "warning";
}

const SUMMARY_EXCEPTION_LABELS: Record<string, string> = {
  missing_settlements: "Missing settlements",
  missing_bank_transactions: "Missing bank transactions",
  settlement_amount_mismatches: "Settlement amount mismatch",
  bank_amount_mismatches: "Bank amount mismatch",
  timestamp_violations: "Timestamp violations",
  refund_mismatches: "Refund mismatch",
  refund_adjusted: "Refund adjusted",
  duplicate_settlements: "Duplicate settlements",
  duplicate_bank_transactions: "Duplicate bank transactions",
  orphan_bank_transactions: "Orphan bank transactions",
  reference_variations: "Reference variations",
};

/** Maps report summary keys to exception type filters used on the Exceptions page. */
export const SUMMARY_TO_EXCEPTION_FILTER: Record<string, string> = {
  missing_settlements: "MISSING_SETTLEMENT",
  missing_bank_transactions: "MISSING_BANK_TRANSACTION",
  settlement_amount_mismatches: "SETTLEMENT_AMOUNT_MISMATCH",
  bank_amount_mismatches: "BANK_AMOUNT_MISMATCH",
  timestamp_violations: "TIMESTAMP_OUTSIDE_TOLERANCE",
  refund_mismatches: "REFUND_NOT_REFLECTED",
  refund_adjusted: "REFUND_ADJUSTED",
  duplicate_settlements: "DUPLICATE_SETTLEMENT",
  duplicate_bank_transactions: "DUPLICATE_BANK_TRANSACTION",
  orphan_bank_transactions: "ORPHAN_BANK_TRANSACTION",
  reference_variations: "REFERENCE_VARIATION",
};

export function formatSummaryExceptionLabel(key: string): string {
  return SUMMARY_EXCEPTION_LABELS[key] ?? key.replace(/_/g, " ");
}

export function getSummaryExceptions(
  summary: Record<string, number>,
): { key: string; label: string; count: number; severity: "critical" | "warning" | "info" }[] {
  const skip = new Set(["total_orders", "reconciled_orders", "unreconciled_orders"]);
  const severityMap: Record<string, "critical" | "warning" | "info"> = {
    missing_settlements: "critical",
    missing_bank_transactions: "critical",
    settlement_amount_mismatches: "critical",
    bank_amount_mismatches: "critical",
    refund_mismatches: "critical",
    duplicate_settlements: "warning",
    duplicate_bank_transactions: "warning",
    orphan_bank_transactions: "warning",
    timestamp_violations: "warning",
    refund_adjusted: "info",
    reference_variations: "info",
  };

  return Object.entries(summary)
    .filter(([key, count]) => !skip.has(key) && count > 0)
    .map(([key, count]) => ({
      key,
      label: formatSummaryExceptionLabel(key),
      count,
      severity: severityMap[key] ?? "warning",
    }))
    .sort((a, b) => b.count - a.count);
}

export const CONSOLE_PATHS = {
  home: "/console",
  dashboard: "/console",
  reconciliation: "/console/reconciliation",
  exceptions: "/console/exceptions",
  evaluation: "/console/evaluation",
  bankImport: "/console/bank-import",
  settings: "/console/settings",
} as const;

export const ROUTE_META: Record<
  string,
  { title: string; subtitle: string; group: string }
> = {
  "/console": {
    title: "Command Center",
    subtitle: "Monitor transaction integrity and reconciliation health",
    group: "Overview",
  },
  "/console/dashboard": {
    title: "Command Center",
    subtitle: "Monitor transaction integrity and reconciliation health",
    group: "Overview",
  },
  "/console/reconciliation": {
    title: "Reconciliation",
    subtitle: "Review order-level reconciliation outcomes",
    group: "Operations",
  },
  "/console/exceptions": {
    title: "Exceptions",
    subtitle: "Investigate reconciliation failures and anomalies",
    group: "Operations",
  },
  "/console/evaluation": {
    title: "Engine Evaluation",
    subtitle: "Measure reconciliation engine correctness",
    group: "Operations",
  },
  "/console/bank-import": {
    title: "Bank CSV Import",
    subtitle: "Deterministic demo CSV — not live Razorpay settlements",
    group: "Operations",
  },
  "/console/settings": {
    title: "Settings",
    subtitle: "System configuration and connection details",
    group: "System",
  },
};

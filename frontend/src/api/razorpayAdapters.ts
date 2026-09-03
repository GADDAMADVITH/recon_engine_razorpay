import type { RazorpaySyncResponse, ReconciliationReport } from "../types/api";

/**
 * Unwrap the nested reconciliation report from a Razorpay sync envelope.
 *
 * Returns null when the sync produced no report (empty dataset or missing
 * reconciliation). Does not fabricate orders, settlements, refunds, or bank
 * transactions. Does not interpret settlement_utr.
 */
export function unwrapRazorpayReconciliation(
  response: RazorpaySyncResponse,
): ReconciliationReport | null {
  if (response.status === "empty") {
    return null;
  }

  const report = response.reconciliation;
  if (report == null) {
    return null;
  }

  return report;
}

/**
 * True when the sync envelope explicitly reports that Razorpay did not supply
 * bank-side transactions (expected for live sync).
 */
export function razorpayBankDataUnavailable(response: RazorpaySyncResponse): boolean {
  return response.bank_data_available === false || response.bank_transactions_fetched === 0;
}

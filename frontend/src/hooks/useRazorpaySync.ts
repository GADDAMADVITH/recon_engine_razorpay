import { useCallback, useState } from "react";
import { api, ApiClientError } from "../api/client";
import { unwrapRazorpayReconciliation } from "../api/razorpayAdapters";
import type { RazorpaySyncResponse, ReconciliationReport } from "../types/api";

export interface RazorpaySyncState {
  /** Unwrapped reconciliation report, or null when empty / not yet synced. */
  report: ReconciliationReport | null;
  /** Full sync envelope preserved for Phase 4B.3 (bank flags, warnings, status). */
  response: RazorpaySyncResponse | null;
  loading: boolean;
  error: string | null;
  /** True when sync completed with no usable reconciliation report. */
  empty: boolean;
  /** Explicitly trigger POST /api/v1/sources/razorpay/sync. Never runs on mount. */
  sync: () => Promise<void>;
  /** Clear report, envelope, error, and empty flag. */
  reset: () => void;
}

/**
 * Explicit Razorpay sync operation for the console.
 * Does not auto-fetch on mount. Does not fabricate bank transactions.
 */
export function useRazorpaySync(): RazorpaySyncState {
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [response, setResponse] = useState<RazorpaySyncResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  const reset = useCallback(() => {
    setReport(null);
    setResponse(null);
    setError(null);
    setEmpty(false);
    setLoading(false);
  }, []);

  const sync = useCallback(async () => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    try {
      const envelope = await api.razorpaySync();
      setResponse(envelope);
      const unwrapped = unwrapRazorpayReconciliation(envelope);
      setReport(unwrapped);
      setEmpty(unwrapped === null);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : "Unable to connect to ReconEngine API.";
      setError(message);
      setReport(null);
      setResponse(null);
      setEmpty(false);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    report,
    response,
    loading,
    error,
    empty,
    sync,
    reset,
  };
}

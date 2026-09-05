import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import type {
  EvaluationResponse,
  FinanceAgentRunResponse,
  FinanceControllerRunResponse,
  HealthResponse,
  OrderResult,
  ReconciliationReport,
  ReconciliationSummary,
} from "../types/api";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refetch: (options?: { silent?: boolean }) => Promise<void>;
}

function useAsyncData<T>(loader: () => Promise<T>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dataRef = useRef<T | null>(null);
  dataRef.current = data;

  const refetch = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent === true && dataRef.current !== null;
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const result = await loader();
      setData(result);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : "Unable to connect to ReconEngine API.";
      setError(message);
      if (!silent) {
        setData(null);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [loader]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { data, loading, refreshing, error, refetch };
}

export function useReconciliationReport() {
  const loader = useCallback(() => api.reconciliationReport(), []);
  return useAsyncData<ReconciliationReport>(loader);
}

export function useReconciliationSummary() {
  const loader = useCallback(() => api.reconciliationSummary(), []);
  return useAsyncData<ReconciliationSummary>(loader);
}

export function useEvaluation() {
  const loader = useCallback(() => api.evaluation(), []);
  return useAsyncData<EvaluationResponse>(loader);
}

export function useHealth() {
  const loader = useCallback(() => api.health(), []);
  return useAsyncData<HealthResponse>(loader);
}

/**
 * Run the Finance Controller on engine-computed order results.
 * Pass null to skip loading. Uses the same order_results shown in the UI —
 * the agent never invents reconciliation facts.
 */
export function useFinanceControllerBatch(orderResults: OrderResult[] | null) {
  const [data, setData] = useState<FinanceControllerRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const orderResultsRef = useRef(orderResults);
  orderResultsRef.current = orderResults;

  const orderKey = orderResults
    ? `${orderResults.length}:${orderResults.map((o) => `${o.order_id}:${o.status}:${o.confidence_score}`).join("|")}`
    : "";

  const refetch = useCallback(async () => {
    const current = orderResultsRef.current;
    if (!current || current.length === 0) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.runFinanceController({ order_results: current });
      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to run Finance Controller.",
      );
    } finally {
      setLoading(false);
    }
  }, [orderKey]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}

/** Production batch: empty POST → current reconciliation report. */
export function useFinanceControllerProduction() {
  const loader = useCallback(() => api.runFinanceController(), []);
  return useAsyncData<FinanceControllerRunResponse>(loader);
}

/**
 * Agent workflow run with decision traces (POST /finance-controller/run-agent).
 * Pass null to skip. Uses the same order_results shown in the UI.
 * Set autoRun=false for demo dashboards that require an explicit Run click.
 */
export function useFinanceControllerAgentRun(
  orderResults: OrderResult[] | null,
  options?: { autoRun?: boolean },
) {
  const autoRun = options?.autoRun !== false;
  const [data, setData] = useState<FinanceAgentRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const orderResultsRef = useRef(orderResults);
  orderResultsRef.current = orderResults;

  const orderKey = orderResults
    ? `${orderResults.length}:${orderResults.map((o) => `${o.order_id}:${o.status}:${o.confidence_score}`).join("|")}`
    : "";

  const refetch = useCallback(async () => {
    const current = orderResultsRef.current;
    if (!current || current.length === 0) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.runFinanceControllerAgent({ order_results: current });
      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to run Finance Controller agent.",
      );
    } finally {
      setLoading(false);
    }
  }, [orderKey]);

  useEffect(() => {
    if (!autoRun) {
      setLoading(false);
      return;
    }
    void refetch();
  }, [refetch, autoRun]);

  return { data, setData, loading, error, refetch };
}

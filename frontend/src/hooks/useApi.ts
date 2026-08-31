import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import type {
  EvaluationResponse,
  HealthResponse,
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

import type {
  EvaluationResponse,
  HealthResponse,
  ReconciliationReport,
  ReconciliationSummary,
} from "../types/api";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8001";

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  const contentType = response.headers.get("content-type") ?? "";

  if (!response.ok) {
    if (contentType.includes("application/json")) {
      const body = (await response.json()) as { detail?: string };
      throw new ApiClientError(
        body.detail || "The service is temporarily unavailable.",
        response.status,
      );
    }
    throw new ApiClientError(
      "The service is temporarily unavailable.",
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE_URL,
  health: () => request<HealthResponse>("/health"),
  reconciliationReport: () =>
    request<ReconciliationReport>("/api/v1/reconciliation/report"),
  reconciliationSummary: () =>
    request<ReconciliationSummary>("/api/v1/reconciliation/summary"),
  evaluation: () => request<EvaluationResponse>("/api/v1/evaluation"),
};

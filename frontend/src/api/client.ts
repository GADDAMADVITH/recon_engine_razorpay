import type {
  EvaluationResponse,
  HealthResponse,
  RazorpayReconcileDemoResponse,
  RazorpaySyncResponse,
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

async function parseErrorResponse(response: Response): Promise<ApiClientError> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const body = (await response.json()) as { detail?: string };
    return new ApiClientError(
      body.detail || "The service is temporarily unavailable.",
      response.status,
    );
  }
  return new ApiClientError("The service is temporarily unavailable.", response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    throw await parseErrorResponse(response);
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
  /**
   * Trigger server-side Razorpay sync. Credentials remain on the server;
   * the frontend never sends or receives Razorpay secrets.
   */
  razorpaySync: () =>
    request<RazorpaySyncResponse>("/api/v1/sources/razorpay/sync", {
      method: "POST",
      headers: { Accept: "application/json" },
    }),
  /**
   * Phase 4A demo with synthetic bank fixtures. Does not call live Razorpay.
   * Distinct from razorpaySync — do not merge demo results into live sync state.
   */
  razorpayReconcileDemo: () =>
    request<RazorpayReconcileDemoResponse>("/api/v1/sources/razorpay/reconcile-demo", {
      method: "POST",
      headers: { Accept: "application/json" },
    }),
};

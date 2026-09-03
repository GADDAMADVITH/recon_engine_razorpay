import type {
  EvaluationResponse,
  HealthResponse,
  OrderResult,
  RazorpayReconcileDemoResponse,
  RazorpaySyncResponse,
  ReconciliationReport,
  ReconciliationSummary,
  AuditExplanationResponse,
  ChatResponse,
  StructuredAuditResponse,
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

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

export const api = {
  baseUrl: API_BASE_URL,
  health: () => request<HealthResponse>("/health"),
  reconciliationReport: () =>
    request<ReconciliationReport>("/api/v1/reconciliation/report"),
  reconciliationSummary: () =>
    request<ReconciliationSummary>("/api/v1/reconciliation/summary"),
  /** Structured audit trail for a specific order (production report lookup). */
  orderAudit: (orderId: string) =>
    request<StructuredAuditResponse>(`/api/v1/reconciliation/${encodeURIComponent(orderId)}/audit`),
  /**
   * Structured audit from an already-computed order_result (bank-import / drawer).
   * Prefer this when the UI has a specific run's order payload.
   */
  orderAuditFromResult: (orderResult: OrderResult) =>
    postJson<StructuredAuditResponse>("/api/v1/reconciliation/audit", {
      order_result: orderResult,
    }),
  /** Grounded AI explanation of a specific order audit trail (production report). */
  orderAuditExplanation: (orderId: string) =>
    request<AuditExplanationResponse>(
      `/api/v1/reconciliation/${encodeURIComponent(orderId)}/audit/explain`,
    ),
  /** AI explanation grounded on a provided order_result (bank-import / drawer). */
  orderAuditExplanationFromResult: (orderResult: OrderResult) =>
    postJson<AuditExplanationResponse>("/api/v1/reconciliation/audit/explain", {
      order_result: orderResult,
    }),
  /**
   * ReconEngine AI chatbot — grounded on engine/audit context.
   * Optional order_result must be engine-computed (bank-import / drawer).
   */
  chat: (body: {
    message: string;
    order_id?: string | null;
    order_result?: OrderResult | null;
    page_context?: Record<string, string> | null;
  }) =>
    postJson<ChatResponse>("/api/v1/chat", {
      message: body.message,
      order_id: body.order_id ?? undefined,
      order_result: body.order_result ?? undefined,
      page_context: body.page_context ?? undefined,
    }),
  /**
   * Upload a bank CSV and reconcile against production orders/settlements.
   * Returns a full ReconciliationReport with bank_source metadata.
   */
  importBankCsv: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<ReconciliationReport>("/api/v1/reconciliation/import-bank", {
      method: "POST",
      body: formData,
    });
  },
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

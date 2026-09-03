import { afterEach, describe, expect, it, vi } from "vitest";
import { unwrapRazorpayReconciliation, razorpayBankDataUnavailable } from "./razorpayAdapters";
import type { RazorpaySyncResponse, ReconciliationReport } from "../types/api";

function minimalReport(overrides?: Partial<ReconciliationReport>): ReconciliationReport {
  return {
    metadata: {
      engine: "recon_engine",
      generated_at: "2026-08-02T10:00:00",
      evaluation_grain: "order",
      currency: "INR",
      minor_unit: "paise",
      data_source: "razorpay",
    },
    configuration: {
      timestamp_tolerance_hours: 24,
      reference_normalization: {},
      reconciliation_status_vocabulary: [],
      exception_vocabulary: [],
    },
    summary: {
      total_orders: 1,
      reconciled_orders: 0,
      unreconciled_orders: 1,
      missing_settlements: 0,
      missing_bank_transactions: 1,
      settlement_amount_mismatches: 0,
      bank_amount_mismatches: 0,
      timestamp_violations: 0,
      refund_mismatches: 0,
      refund_adjusted: 0,
      duplicate_settlements: 0,
      duplicate_bank_transactions: 0,
      orphan_bank_transactions: 0,
      reference_variations: 0,
    },
    status_counts: { unreconciled_missing_bank: 1 },
    order_results: [],
    global_exceptions: [],
    ...overrides,
  };
}

function envelope(
  overrides: Partial<RazorpaySyncResponse> & Pick<RazorpaySyncResponse, "status">,
): RazorpaySyncResponse {
  return {
    source: "razorpay",
    orders_fetched: 0,
    payments_fetched: 0,
    refunds_fetched: 0,
    settlements_fetched: 0,
    recon_items_fetched: 0,
    bank_data_available: false,
    bank_transactions_fetched: 0,
    orders: [],
    settlements: [],
    refunds: [],
    mapping_warnings: [],
    mapping_errors: [],
    reconciliation: null,
    ...overrides,
  };
}

describe("unwrapRazorpayReconciliation", () => {
  it("unwraps reconciliation from a successful sync response", () => {
    const report = minimalReport();
    const response = envelope({
      status: "success",
      orders_fetched: 1,
      reconciliation: report,
    });

    const unwrapped = unwrapRazorpayReconciliation(response);
    expect(unwrapped).toBe(report);
    expect(unwrapped?.metadata.data_source).toBe("razorpay");
    expect(unwrapped?.summary.total_orders).toBe(1);
  });

  it("returns null for empty sync status", () => {
    const response = envelope({
      status: "empty",
      reconciliation: null,
      mapping_warnings: ["No Razorpay orders returned; reconciliation was not run."],
    });

    expect(unwrapRazorpayReconciliation(response)).toBeNull();
  });

  it("returns null for empty status even if reconciliation were accidentally present", () => {
    const response = envelope({
      status: "empty",
      reconciliation: minimalReport(),
    });

    expect(unwrapRazorpayReconciliation(response)).toBeNull();
  });

  it("unwraps reconciliation from a partial sync response when present", () => {
    const report = minimalReport({
      summary: {
        ...minimalReport().summary,
        total_orders: 2,
        unreconciled_orders: 2,
      },
    });
    const response = envelope({
      status: "partial",
      orders_fetched: 2,
      mapping_errors: ["refund: missing order_id"],
      reconciliation: report,
    });

    expect(unwrapRazorpayReconciliation(response)).toBe(report);
  });

  it("returns null when reconciliation is missing on success/partial", () => {
    expect(
      unwrapRazorpayReconciliation(envelope({ status: "success", reconciliation: null })),
    ).toBeNull();
    expect(
      unwrapRazorpayReconciliation(envelope({ status: "partial", reconciliation: null })),
    ).toBeNull();
  });

  it("does not fabricate bank transactions from the envelope", () => {
    const response = envelope({
      status: "success",
      bank_data_available: false,
      bank_transactions_fetched: 0,
      reconciliation: minimalReport(),
    });
    const unwrapped = unwrapRazorpayReconciliation(response);
    expect(unwrapped).not.toBeNull();
    expect(response.bank_transactions_fetched).toBe(0);
    expect(razorpayBankDataUnavailable(response)).toBe(true);
    // Adapter never invents bank rows on the report
    expect(unwrapped!.order_results.every((o) => o.valid_bank_transaction_id == null)).toBe(true);
  });
});

describe("api.razorpaySync client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("POSTs to the Razorpay sync endpoint and returns the envelope", async () => {
    const payload = envelope({
      status: "success",
      orders_fetched: 1,
      reconciliation: minimalReport(),
    });

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("./client");
    const result = await api.razorpaySync();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/sources\/razorpay\/sync$/);
    expect(init.method).toBe("POST");
    expect(result.status).toBe("success");
    expect(unwrapRazorpayReconciliation(result)?.metadata.data_source).toBe("razorpay");
  });

  it("preserves existing ApiClientError handling on non-OK responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Razorpay credentials are not configured on the server" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { api, ApiClientError } = await import("./client");
    try {
      await api.razorpaySync();
      expect.fail("expected ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      expect(err).toMatchObject({
        name: "ApiClientError",
        status: 503,
        message: "Razorpay credentials are not configured on the server",
      });
    }
  });

  it("does not reference Razorpay secrets in the client module source contract", async () => {
    const { api } = await import("./client");
    const serialized = JSON.stringify(api);
    expect(serialized).not.toMatch(/KEY_SECRET/i);
    expect(serialized).not.toMatch(/key_secret/i);
    expect(serialized).not.toMatch(/RAZORPAY_KEY_SECRET/);
  });
});

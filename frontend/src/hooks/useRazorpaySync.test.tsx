import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RazorpaySyncResponse, ReconciliationReport } from "../types/api";
import { useDataSource } from "./useDataSource";
import { useRazorpaySync } from "./useRazorpaySync";

const razorpaySyncMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      razorpaySync: (...args: unknown[]) => razorpaySyncMock(...args),
    },
  };
});

function minimalReport(): ReconciliationReport {
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
    mapping_warnings: ["Razorpay data cannot be mapped to NormalizedBankTransaction"],
    mapping_errors: [],
    reconciliation: null,
    ...overrides,
  };
}

describe("useDataSource", () => {
  it("defaults to csv", () => {
    const { result } = renderHook(() => useDataSource());
    expect(result.current.source).toBe("csv");
    expect(result.current.isCsv).toBe(true);
    expect(result.current.isRazorpay).toBe(false);
  });

  it("switches from csv to razorpay", () => {
    const { result } = renderHook(() => useDataSource());
    act(() => {
      result.current.setSource("razorpay");
    });
    expect(result.current.source).toBe("razorpay");
    expect(result.current.isCsv).toBe(false);
    expect(result.current.isRazorpay).toBe(true);
  });
});

describe("useRazorpaySync", () => {
  afterEach(() => {
    razorpaySyncMock.mockReset();
  });

  it("does not call Razorpay sync on mount", () => {
    renderHook(() => useRazorpaySync());
    expect(razorpaySyncMock).not.toHaveBeenCalled();
  });

  it("starts idle with null report and empty=false", () => {
    const { result } = renderHook(() => useRazorpaySync());
    expect(result.current.report).toBeNull();
    expect(result.current.response).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.empty).toBe(false);
  });

  it("sync() calls api.razorpaySync and exposes unwrapped report plus envelope", async () => {
    const report = minimalReport();
    const payload = envelope({
      status: "success",
      orders_fetched: 1,
      bank_data_available: false,
      bank_transactions_fetched: 0,
      mapping_warnings: ["bank unavailable"],
      mapping_errors: [],
      reconciliation: report,
    });
    razorpaySyncMock.mockResolvedValue(payload);

    const { result } = renderHook(() => useRazorpaySync());
    await act(async () => {
      await result.current.sync();
    });

    expect(razorpaySyncMock).toHaveBeenCalledTimes(1);
    expect(result.current.report).toBe(report);
    expect(result.current.response).toBe(payload);
    expect(result.current.response?.bank_data_available).toBe(false);
    expect(result.current.response?.bank_transactions_fetched).toBe(0);
    expect(result.current.response?.mapping_warnings).toEqual(["bank unavailable"]);
    expect(result.current.response?.status).toBe("success");
    expect(result.current.empty).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("empty sync produces report=null and empty=true", async () => {
    razorpaySyncMock.mockResolvedValue(
      envelope({
        status: "empty",
        reconciliation: null,
      }),
    );

    const { result } = renderHook(() => useRazorpaySync());
    await act(async () => {
      await result.current.sync();
    });

    expect(result.current.report).toBeNull();
    expect(result.current.empty).toBe(true);
    expect(result.current.response?.status).toBe("empty");
    expect(result.current.error).toBeNull();
  });

  it("missing reconciliation is treated as empty", async () => {
    razorpaySyncMock.mockResolvedValue(
      envelope({
        status: "success",
        orders_fetched: 1,
        reconciliation: null,
      }),
    );

    const { result } = renderHook(() => useRazorpaySync());
    await act(async () => {
      await result.current.sync();
    });

    expect(result.current.report).toBeNull();
    expect(result.current.empty).toBe(true);
    expect(result.current.response).not.toBeNull();
  });

  it("API errors expose error state and clear report/envelope", async () => {
    const { ApiClientError } = await import("../api/client");
    razorpaySyncMock.mockRejectedValue(
      new ApiClientError("Razorpay credentials are not configured on the server", 503),
    );

    const { result } = renderHook(() => useRazorpaySync());
    await act(async () => {
      await result.current.sync();
    });

    expect(result.current.error).toBe(
      "Razorpay credentials are not configured on the server",
    );
    expect(result.current.report).toBeNull();
    expect(result.current.response).toBeNull();
    expect(result.current.empty).toBe(false);
    expect(result.current.loading).toBe(false);
  });

  it("sets loading true during sync and false afterward", async () => {
    let resolveSync: (value: RazorpaySyncResponse) => void = () => undefined;
    razorpaySyncMock.mockImplementation(
      () =>
        new Promise<RazorpaySyncResponse>((resolve) => {
          resolveSync = resolve;
        }),
    );

    const { result } = renderHook(() => useRazorpaySync());
    let syncPromise: Promise<void> | undefined;
    act(() => {
      syncPromise = result.current.sync();
    });
    expect(result.current.loading).toBe(true);

    await act(async () => {
      resolveSync(
        envelope({
          status: "success",
          reconciliation: minimalReport(),
        }),
      );
      await syncPromise;
    });

    expect(result.current.loading).toBe(false);
  });

  it("reset clears sync state", async () => {
    razorpaySyncMock.mockResolvedValue(
      envelope({
        status: "success",
        reconciliation: minimalReport(),
      }),
    );

    const { result } = renderHook(() => useRazorpaySync());
    await act(async () => {
      await result.current.sync();
    });
    expect(result.current.report).not.toBeNull();

    act(() => {
      result.current.reset();
    });
    expect(result.current.report).toBeNull();
    expect(result.current.response).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.empty).toBe(false);
    expect(result.current.loading).toBe(false);
  });

  it("does not reference Razorpay secrets in hook module exports", async () => {
    const dataSourceModule = await import("./useDataSource");
    const syncModule = await import("./useRazorpaySync");
    const blob = JSON.stringify(dataSourceModule) + JSON.stringify(syncModule);
    expect(blob).not.toMatch(/KEY_SECRET/i);
    expect(blob).not.toMatch(/key_secret/i);
    expect(blob).not.toMatch(/RAZORPAY_KEY_SECRET/);
  });
});

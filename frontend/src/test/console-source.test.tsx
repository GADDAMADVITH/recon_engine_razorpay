import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsoleReportProvider } from "../context/ConsoleReportContext";
import { DashboardPage } from "../pages/DashboardPage";
import { mockHookState, mockReport } from "./fixtures";
import type { RazorpaySyncResponse, ReconciliationReport } from "../types/api";

const syncMock = vi.fn();
const razorpayState = {
  report: null as ReconciliationReport | null,
  response: null as RazorpaySyncResponse | null,
  loading: false,
  error: null as string | null,
  empty: false,
  sync: syncMock,
  reset: vi.fn(),
};

vi.mock("../hooks/useApi", () => ({
  useReconciliationReport: vi.fn(),
  useHealth: vi.fn(() => ({
    data: { status: "ok", service: "recon-engine-api", version: "v1" },
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
  useFinanceControllerBatch: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useFinanceControllerAgentRun: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
}));

vi.mock("../hooks/useRazorpaySync", () => ({
  useRazorpaySync: vi.fn(() => razorpayState),
}));

import { useReconciliationReport } from "../hooks/useApi";

const mockedUseReport = vi.mocked(useReconciliationReport);

function razorpayReport(): ReconciliationReport {
  return {
    ...mockReport,
    metadata: {
      ...mockReport.metadata,
      data_source: "razorpay",
    },
    summary: {
      ...mockReport.summary,
      total_orders: 3,
      reconciled_orders: 0,
      unreconciled_orders: 3,
      missing_bank_transactions: 3,
    },
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ConsoleReportProvider>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
        </Routes>
      </ConsoleReportProvider>
    </MemoryRouter>,
  );
}

describe("Phase 4B.3 console source workflow", () => {
  beforeEach(() => {
    mockedUseReport.mockReturnValue(mockHookState(mockReport));
    razorpayState.report = null;
    razorpayState.response = null;
    razorpayState.loading = false;
    razorpayState.error = null;
    razorpayState.empty = false;
    syncMock.mockReset();
    syncMock.mockResolvedValue(undefined);
  });

  it("defaults to CSV and keeps Run reconciliation CTA", () => {
    renderDashboard();
    expect(screen.getByRole("button", { name: "CSV" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Razorpay" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: /Run reconciliation/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sync from Razorpay/i })).not.toBeInTheDocument();
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("switching to Razorpay does not call sync", async () => {
    const user = userEvent.setup();
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    expect(screen.getByRole("button", { name: "Razorpay" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(syncMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Razorpay source selected/i)).toBeInTheDocument();
    expect(screen.getByText(/Bank data not available from Razorpay/i)).toBeInTheDocument();
  });

  it("Sync from Razorpay CTA calls sync exactly when clicked", async () => {
    const user = userEvent.setup();
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    await user.click(screen.getByRole("button", { name: /Sync from Razorpay/i }));
    expect(syncMock).toHaveBeenCalledTimes(1);
  });

  it("shows loading state while Razorpay sync is in progress", async () => {
    const user = userEvent.setup();
    razorpayState.loading = true;
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
    expect(screen.getByText(/Syncing Razorpay data/i)).toBeInTheDocument();
  });

  it("shows EmptyState for empty Razorpay sync", async () => {
    const user = userEvent.setup();
    razorpayState.empty = true;
    razorpayState.report = null;
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    expect(screen.getByText(/No Razorpay orders to reconcile/i)).toBeInTheDocument();
  });

  it("shows ErrorState for Razorpay API errors", async () => {
    const user = userEvent.setup();
    razorpayState.error = "Razorpay credentials are not configured on the server";
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    expect(screen.getByText(/Unable to load data/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Razorpay credentials are not configured on the server/i),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/RAZORPAY_KEY_SECRET/);
    expect(screen.queryByText(/RAZORPAY_KEY_SECRET/i)).not.toBeInTheDocument();
  });

  it("renders Razorpay reconciliation summary after successful sync", async () => {
    const user = userEvent.setup();
    const report = razorpayReport();
    razorpayState.report = report;
    razorpayState.response = {
      source: "razorpay",
      status: "success",
      orders_fetched: 3,
      payments_fetched: 3,
      refunds_fetched: 0,
      settlements_fetched: 3,
      recon_items_fetched: 3,
      bank_data_available: false,
      bank_transactions_fetched: 0,
      orders: [],
      settlements: [],
      refunds: [],
      mapping_warnings: [],
      mapping_errors: [],
      reconciliation: report,
    };
    renderDashboard();
    await user.click(screen.getByRole("button", { name: "Razorpay" }));
    expect(screen.getByText(/Source · Razorpay/i)).toBeInTheDocument();
    expect(screen.getByText(/Bank · Not available from Razorpay/i)).toBeInTheDocument();
    expect(screen.getByText(/Bank data not available from Razorpay/i)).toBeInTheDocument();
    expect(screen.getByText("Reconciliation Health")).toBeInTheDocument();
    expect(screen.getByText(/INR · 3 orders/i)).toBeInTheDocument();
  });

  it("does not expose Razorpay secrets in the dashboard UI source", () => {
    renderDashboard();
    expect(document.body.textContent).not.toMatch(/KEY_SECRET/i);
    expect(document.body.textContent).not.toMatch(/RAZORPAY_KEY_SECRET/);
  });
});

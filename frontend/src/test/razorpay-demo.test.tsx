import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsoleReportProvider } from "../context/ConsoleReportContext";
import { RazorpayDemoPanel } from "../components/sources/RazorpayDemoPanel";
import { DashboardPage } from "../pages/DashboardPage";
import { mockHookState, mockReport } from "./fixtures";
import type { RazorpayReconcileDemoResponse, RazorpaySyncResponse, ReconciliationReport } from "../types/api";
import { ApiClientError } from "../api/client";

const syncMock = vi.fn();
const demoMock = vi.fn();
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

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      razorpayReconcileDemo: (...args: unknown[]) => demoMock(...args),
      razorpaySync: (...args: unknown[]) => syncMock(...args),
      runFinanceController: vi.fn(async () => ({
        agent: "reconengine-finance-controller",
        agent_version: "1.0.0",
        provider: "deterministic_policy",
        records_processed: 0,
        no_action_count: 0,
        review_required_count: 0,
        exception_count: 0,
        unresolved_count: 0,
        decisions_by_type: {},
        decisions: [],
      })),
      runFinanceControllerAgent: vi.fn(async () => ({
        run_id: "FCRUN_test",
        started_at: "2026-09-04T12:00:00Z",
        completed_at: "2026-09-04T12:00:01Z",
        elapsed_seconds: 0.01,
        records_processed: 0,
        no_action_count: 0,
        review_required_count: 0,
        unresolved_count: 0,
        pending_approval_count: 0,
        decisions_by_type: {},
        decisions: [],
      })),
    },
  };
});

import { useReconciliationReport } from "../hooks/useApi";

const mockedUseReport = vi.mocked(useReconciliationReport);

const DEMO_NOTE =
  "Bank rows are synthetic fixtures for Phase 4A demonstration. They are not produced by Razorpay and are not derived from settlement_utr.";

function demoResponse(): RazorpayReconcileDemoResponse {
  return {
    source: "razorpay",
    bank_source: "synthetic_fixture",
    bank_source_note: DEMO_NOTE,
    status: "success",
    scenario_count: 4,
    scenarios: [
      {
        scenario_id: "successful_reconciliation",
        order_id: "order_demo_ok",
        description: "Order settles and matches synthetic bank net.",
        expected_status: "reconciled",
        expected_reconciled: true,
        actual_status: "reconciled",
        actual_reconciled: true,
        matched_expectation: true,
      },
      {
        scenario_id: "bank_amount_mismatch",
        order_id: "order_demo_bank_mismatch",
        description: "Settlement exists but synthetic bank amount differs.",
        expected_status: "unreconciled_settlement_amount",
        expected_reconciled: false,
        actual_status: "unreconciled_settlement_amount",
        actual_reconciled: false,
        matched_expectation: true,
      },
      {
        scenario_id: "missing_settlement",
        order_id: "order_demo_missing_setl",
        description: "Order has no settlement.",
        expected_status: "unreconciled_missing_settlement",
        expected_reconciled: false,
        actual_status: "unreconciled_missing_settlement",
        actual_reconciled: false,
        matched_expectation: true,
      },
      {
        scenario_id: "refund_adjusted",
        order_id: "order_demo_refund",
        description: "Refund is reflected in settlement and bank.",
        expected_status: "reconciled_with_refund_adjustment",
        expected_reconciled: true,
        actual_status: "reconciled_with_refund_adjustment",
        actual_reconciled: true,
        matched_expectation: true,
      },
    ],
    reconciliation: mockReport,
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

describe("Phase 4B.4 Razorpay reconcile demo UI", () => {
  beforeEach(() => {
    mockedUseReport.mockReturnValue(mockHookState(mockReport));
    razorpayState.report = null;
    razorpayState.response = null;
    razorpayState.loading = false;
    razorpayState.error = null;
    razorpayState.empty = false;
    syncMock.mockReset();
    demoMock.mockReset();
    demoMock.mockResolvedValue(demoResponse());
  });

  it("shows the demo button only in Razorpay context", async () => {
    const user = userEvent.setup();
    renderDashboard();

    expect(screen.queryByRole("button", { name: /run phase 4a demo/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Razorpay" }));

    expect(screen.getByRole("button", { name: /run phase 4a demo/i })).toBeInTheDocument();
    expect(screen.getByText("Demo — Synthetic Bank Data")).toBeInTheDocument();
    expect(
      screen.getByText(/Bank transactions are synthetic fixtures for demonstration only/i),
    ).toBeInTheDocument();
  });

  it("calls reconcile-demo once and never live sync when demo is clicked", async () => {
    const user = userEvent.setup();
    render(<RazorpayDemoPanel />);

    await user.click(screen.getByRole("button", { name: /run phase 4a demo/i }));

    await waitFor(() => expect(demoMock).toHaveBeenCalledTimes(1));
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("shows loading state while the demo request is in flight", async () => {
    const user = userEvent.setup();
    let resolveDemo: (value: RazorpayReconcileDemoResponse) => void = () => undefined;
    demoMock.mockImplementation(
      () =>
        new Promise<RazorpayReconcileDemoResponse>((resolve) => {
          resolveDemo = resolve;
        }),
    );

    render(<RazorpayDemoPanel />);
    await user.click(screen.getByRole("button", { name: /run phase 4a demo/i }));

    expect(screen.getByText(/Running Phase 4A demo scenarios/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run phase 4a demo/i })).toBeDisabled();

    resolveDemo(demoResponse());
    await waitFor(() =>
      expect(screen.getByText(/successful reconciliation/i)).toBeInTheDocument(),
    );
  });

  it("renders all four scenarios with expected and actual statuses", async () => {
    const user = userEvent.setup();
    render(<RazorpayDemoPanel />);

    await user.click(screen.getByRole("button", { name: /run phase 4a demo/i }));

    await waitFor(() => expect(screen.getByText("successful reconciliation")).toBeInTheDocument());

    expect(screen.getByText("bank amount mismatch")).toBeInTheDocument();
    expect(screen.getByText("missing settlement")).toBeInTheDocument();
    expect(screen.getByText("refund adjusted")).toBeInTheDocument();

    expect(screen.getByText("order_demo_ok")).toBeInTheDocument();
    expect(screen.getByText("order_demo_bank_mismatch")).toBeInTheDocument();
    expect(screen.getByText("order_demo_missing_setl")).toBeInTheDocument();
    expect(screen.getByText("order_demo_refund")).toBeInTheDocument();

    expect(screen.getAllByText("Expected")).toHaveLength(4);
    expect(screen.getAllByText("Actual")).toHaveLength(4);

    expect(screen.getAllByText("not reconciled").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Expectation matched")).toHaveLength(4);
  });

  it("shows the synthetic bank warning from the demo response", async () => {
    const user = userEvent.setup();
    render(<RazorpayDemoPanel />);

    await user.click(screen.getByRole("button", { name: /run phase 4a demo/i }));

    await waitFor(() =>
      expect(screen.getByText(/Demo — Synthetic Bank Data \(synthetic_fixture\)/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(DEMO_NOTE)).toBeInTheDocument();
    expect(screen.queryByText(/rzp_test_/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });

  it("handles API errors without calling live sync", async () => {
    const user = userEvent.setup();
    demoMock.mockRejectedValue(new ApiClientError("Demo endpoint unavailable", 503));

    render(<RazorpayDemoPanel />);
    await user.click(screen.getByRole("button", { name: /run phase 4a demo/i }));

    await waitFor(() => expect(screen.getByText("Demo failed")).toBeInTheDocument());
    expect(screen.getByText("Demo endpoint unavailable")).toBeInTheDocument();
    expect(syncMock).not.toHaveBeenCalled();
    expect(demoMock).toHaveBeenCalledTimes(1);
  });
});

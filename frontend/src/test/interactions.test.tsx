import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import { ChatOrderProvider } from "../context/ChatOrderContext";
import { ConsoleReportProvider } from "../context/ConsoleReportContext";
import { DashboardPage } from "../pages/DashboardPage";
import { ExceptionsPage } from "../pages/ExceptionsPage";
import { ReconciliationPage } from "../pages/ReconciliationPage";
import { makeFinanceDecision, mockHookState, mockReport } from "./fixtures";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      runFinanceController: vi.fn(async ({ order_results }: { order_results?: typeof mockReport.order_results }) => ({
        agent: "reconengine-finance-controller",
        agent_version: "1.0.0",
        provider: "deterministic_policy",
        records_processed: order_results?.length ?? 0,
        no_action_count: 0,
        review_required_count: 0,
        exception_count: 0,
        unresolved_count: 0,
        decisions_by_type: {},
        decisions: (order_results ?? []).map((order) =>
          makeFinanceDecision(order.order_id, "NO_ACTION", {
            original_status: order.status,
            original_reconciled: order.reconciled,
            confidence_score: order.confidence_score,
          }),
        ),
      })),
      runFinanceControllerAgent: vi.fn(async ({ order_results }: { order_results?: typeof mockReport.order_results }) => ({
        run_id: "FCRUN_test",
        started_at: "2026-09-04T12:00:00Z",
        completed_at: "2026-09-04T12:00:01Z",
        elapsed_seconds: 0.01,
        records_processed: order_results?.length ?? 0,
        no_action_count: order_results?.length ?? 0,
        review_required_count: 0,
        unresolved_count: 0,
        pending_approval_count: 0,
        decisions_by_type: { NO_ACTION: order_results?.length ?? 0 },
        decisions: (order_results ?? []).map((order) => ({
          order_id: order.order_id,
          original_result: {
            order_id: order.order_id,
            status: order.status,
            reconciled: order.reconciled,
            confidence_score: order.confidence_score,
            exception_types: [],
          },
          audit_evidence_summary: {},
          triggered_exceptions: [],
          decision: "NO_ACTION",
          rationale: "Reconciliation is successful and no blocking exception requires intervention.",
          requires_approval: false,
          proposed_action: null,
          timestamp: "2026-09-04T12:00:00Z",
        })),
      })),
    },
  };
});

vi.mock("../hooks/useApi", () => ({
  useReconciliationReport: vi.fn(),
  useReconciliationSummary: vi.fn(() => ({
    data: {
      total_orders: 50,
      reconciled_orders: 26,
      unreconciled_orders: 24,
      status_counts: {},
      exception_counts: {
        missing_settlements: 4,
        missing_bank_transactions: 3,
        settlement_amount_mismatches: 2,
        bank_amount_mismatches: 1,
        timestamp_violations: 2,
        refund_mismatches: 1,
        duplicate_settlements: 1,
        duplicate_bank_transactions: 0,
        orphan_bank_transactions: 0,
        reference_variations: 2,
      },
    },
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
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
  useEvaluation: vi.fn(() => ({
    data: {
      metadata: { evaluator: "test", evaluation_grain: "order", orders_evaluated: 50, report_generated_at: "", ground_truth_generated_at: "", evaluation_policy: {} },
      summary: {
        orders_evaluated: 50,
        binary_accuracy: 1,
        binary_precision: 1,
        binary_recall: 1,
        binary_f1_score: 1,
        strict_status_accuracy: 0.78,
        relaxed_status_accuracy: 1,
        primary_settlement_match_rate: 1,
        primary_bank_match_rate: 1,
        valid_bank_set_match_rate: 1,
      },
      binary_classification: {
        true_positives: 26,
        false_positives: 0,
        false_negatives: 0,
        true_negatives: 24,
        accuracy: 1,
        precision: 1,
        recall: 1,
        f1_score: 1,
        mismatch_count: 0,
        mismatches: [],
      },
      status_evaluation: {
        strict: { correct: 39, incorrect: 11, accuracy: 0.78, mismatches: [] },
        relaxed: { equivalence_policy: [], correct: 50, incorrect: 0, accuracy: 1, mismatches: [] },
      },
      scenario_evaluation: {
        clean_match: { total_orders: 10, binary_accuracy: 1, binary_correct: 10, strict_status_correct: 10, strict_status_accuracy: 1, relaxed_status_correct: 10, relaxed_status_accuracy: 1, primary_settlement_match_count: 10, primary_settlement_match_rate: 1, primary_bank_match_count: 10, primary_bank_match_rate: 1 },
      },
      link_level_evaluation: {},
      global_exception_evaluation: {},
      amount_validation: {},
    },
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
}));

import { useReconciliationReport } from "../hooks/useApi";

const mockedUseReport = vi.mocked(useReconciliationReport);

function table() {
  return within(screen.getByRole("table"));
}

function renderWithRouter(initialPath = "/console") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>,
  );
}

function renderConsolePage(ui: React.ReactElement, initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ConsoleReportProvider>{ui}</ConsoleReportProvider>
    </MemoryRouter>,
  );
}

describe("frontend interactions", () => {
  beforeEach(() => {
    mockedUseReport.mockReturnValue(mockHookState(mockReport));
  });

  it("navigates via sidebar links", async () => {
    const user = userEvent.setup();
    renderWithRouter("/console");

    expect(
      screen.getByRole("heading", { name: "Reconciliation Command Center" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Reconciliation/i }));
    expect(screen.getByRole("table")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Exceptions/i }));
    expect(screen.getByText(/Investigate reconciliation failures and anomalies\./i)).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Evaluation/i }));
    expect(
      screen.getByText(/Evaluation uses ground truth to measure engine correctness/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Settings/i }));
    expect(screen.getAllByText(/System configuration and connection details/i).length).toBeGreaterThan(0);
  }, 15_000);

  it("navigates to the landing page from ReconEngine branding", async () => {
    const user = userEvent.setup();
    renderWithRouter("/console");

    const brand = screen.getByTestId("console-brand-link");
    expect(brand).toHaveAttribute("href", "/");
    await user.click(brand);
    expect(
      await screen.findByRole("heading", { name: /Reconcile on facts/i }, { timeout: 8000 }),
    ).toBeInTheDocument();
  }, 15_000);

  it("filters reconciliation table by search", async () => {
    const user = userEvent.setup();
    renderConsolePage(<ReconciliationPage />);

    expect(table().getByText("ORD_0001")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Search order ID"), "ORD_0011");
    expect(table().queryByText("ORD_0001")).not.toBeInTheDocument();
    expect(table().getByText("ORD_0011")).toBeInTheDocument();
  });

  it("filters reconciliation table by status", async () => {
    const user = userEvent.setup();
    renderConsolePage(<ReconciliationPage />);

    await user.selectOptions(screen.getAllByRole("combobox")[0], "unreconciled_missing_settlement");
    expect(table().getByText("ORD_0011")).toBeInTheDocument();
    expect(table().queryByText("ORD_0001")).not.toBeInTheDocument();
  });

  it("paginates reconciliation results", async () => {
    const user = userEvent.setup();
    renderConsolePage(<ReconciliationPage />);

    expect(table().getByText("ORD_0001")).toBeInTheDocument();
    expect(table().queryByText("ORD_0015")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(table().getByText("ORD_0015")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(table().getByText("ORD_0001")).toBeInTheDocument();
  });

  it("opens and closes order detail drawer from reconciliation row", async () => {
    const user = userEvent.setup();
    renderConsolePage(<ReconciliationPage />);

    await user.click(table().getByText("ORD_0001"));
    const dialog = await screen.findByRole("dialog", { name: /Order details for ORD_0001/i });
    expect(dialog).toBeInTheDocument();

    await user.click(within(dialog).getByLabelText("Close"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes order drawer via backdrop click", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <ChatOrderProvider>
        <OrderDetailDrawer order={mockReport.order_results[0]} onClose={onClose} />
      </ChatOrderProvider>,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close order details" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("navigates from dashboard exception row to filtered exceptions page", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/console"]}>
        <ConsoleReportProvider>
          <Routes>
            <Route path="/console" element={<DashboardPage />} />
            <Route path="/console/exceptions" element={<ExceptionsPage />} />
          </Routes>
        </ConsoleReportProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: /Missing settlements/i }));
    expect(
      screen.getByText("Investigate reconciliation failures and anomalies."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Missing settlement/i }).length).toBeGreaterThan(0);
  });

  it("expands exception category and opens order drawer", async () => {
    const user = userEvent.setup();
    renderConsolePage(<ExceptionsPage />, "/exceptions?filter=MISSING_SETTLEMENT");

    const rows = screen.getAllByRole("button", { name: /Missing settlement/i });
    const categoryRow = rows.find((el) => el.textContent?.includes("No settlement found"))!;
    await user.click(categoryRow);

    await user.click(screen.getByRole("button", { name: "ORD_0011" }));
    expect(
      await screen.findByRole("dialog", { name: /ORD_0011/i }),
    ).toBeInTheDocument();
  });

  it("run reconciliation triggers silent refetch and success feedback", async () => {
    let resolveRefetch!: () => void;
    const refetch = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRefetch = resolve;
        }),
    );
    mockedUseReport.mockReturnValue({
      ...mockHookState(mockReport),
      refetch,
    });

    const user = userEvent.setup();
    renderConsolePage(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: /Run reconciliation/i }));
    expect(refetch).toHaveBeenCalledWith({ silent: true });
    expect(screen.getByRole("button", { name: /Running reconciliation/i })).toBeDisabled();

    resolveRefetch();
    expect(await screen.findByRole("button", { name: /Reconciliation complete/i })).toBeInTheDocument();
    expect(await screen.findByText("Data refreshed")).toBeInTheDocument();
  });
});

describe("order drawer close handler", () => {
  it("invokes onClose from close button", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <ChatOrderProvider>
        <OrderDetailDrawer order={mockReport.order_results[0]} onClose={onClose} />
      </ChatOrderProvider>,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText("Close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

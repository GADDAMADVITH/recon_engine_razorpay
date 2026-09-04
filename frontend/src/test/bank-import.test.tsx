import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BankImportPage } from "../pages/BankImportPage";
import { ChatOrderProvider } from "../context/ChatOrderContext";
import { mockFinanceAgentRun, mockReport } from "./fixtures";
import { ApiClientError } from "../api/client";

// Mock the api client
const importMock = vi.fn();
const runFinanceControllerAgentMock = vi.fn();
const getFinanceApprovalQueueMock = vi.fn();
const runFinanceControllerAgentPlanMock = vi.fn();
const getFinanceControllerEvaluationMock = vi.fn();
const getFinanceDemoStatusMock = vi.fn();
const resetFinanceDemoActionsMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      importBankCsv: (...args: unknown[]) => importMock(...args),
      runFinanceControllerAgent: (...args: unknown[]) => runFinanceControllerAgentMock(...args),
      getFinanceApprovalQueue: (...args: unknown[]) => getFinanceApprovalQueueMock(...args),
      runFinanceControllerAgentPlan: (...args: unknown[]) =>
        runFinanceControllerAgentPlanMock(...args),
      getFinanceControllerEvaluation: (...args: unknown[]) =>
        getFinanceControllerEvaluationMock(...args),
      getFinanceDemoStatus: (...args: unknown[]) => getFinanceDemoStatusMock(...args),
      resetFinanceDemoActions: (...args: unknown[]) => resetFinanceDemoActionsMock(...args),
    },
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ChatOrderProvider>
        <BankImportPage />
      </ChatOrderProvider>
    </MemoryRouter>,
  );
}

function mockReportWithScenarios() {
  return {
    ...mockReport,
    metadata: {
      ...mockReport.metadata,
      bank_source: "uploaded_csv",
      bank_rows_imported: 3,
    },
    summary: {
      ...mockReport.summary,
      total_orders: 4,
      reconciled_orders: 2,
      unreconciled_orders: 2,
      missing_bank_transactions: 1,
      bank_amount_mismatches: 1,
    },
    order_results: [
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0001",
        status: "reconciled" as const,
        reconciled: true,
        confidence_score: 100,
        primary_settlement_id: "SET_0001",
        valid_bank_transaction_id: "DEMO_BNK_0001",
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0002",
        status: "unreconciled_settlement_amount" as const,
        reconciled: false,
        confidence_score: 40,
        primary_settlement_id: "SET_0002",
        valid_bank_transaction_id: "DEMO_BNK_0002",
        exceptions: [{ type: "BANK_AMOUNT_MISMATCH", message: "Bank amount differs." }],
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0003",
        status: "unreconciled_missing_bank" as const,
        reconciled: false,
        confidence_score: 30,
        primary_settlement_id: "SET_0003",
        valid_bank_transaction_id: null,
        exceptions: [{ type: "MISSING_BANK_TRANSACTION", message: "No bank row." }],
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0033",
        status: "reconciled_with_refund_adjustment" as const,
        reconciled: true,
        confidence_score: 100,
        primary_settlement_id: "SET_0029",
        valid_bank_transaction_id: "DEMO_BNK_0004",
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0024",
        status: "unreconciled_missing_settlement" as const,
        reconciled: false,
        confidence_score: 20,
        primary_settlement_id: null,
        valid_bank_transaction_id: null,
        exceptions: [{ type: "MISSING_SETTLEMENT", message: "No settlement." }],
      },
    ],
  };
}

describe("BankImportPage", () => {
  beforeEach(() => {
    importMock.mockReset();
    importMock.mockResolvedValue(mockReportWithScenarios());
    runFinanceControllerAgentMock.mockReset();
    runFinanceControllerAgentMock.mockResolvedValue({
      ...mockFinanceAgentRun,
      records_processed: 5,
      decisions: mockFinanceAgentRun.decisions,
    });
    getFinanceApprovalQueueMock.mockReset();
    getFinanceApprovalQueueMock.mockResolvedValue({
      run_id: mockFinanceAgentRun.run_id,
      pending_count: 0,
      items: [],
      lifecycle: {
        run_id: mockFinanceAgentRun.run_id,
        total_decisions: 5,
        no_action: 1,
        pending_approval: 0,
        approved: 0,
        rejected: 0,
        recorded: 0,
        unresolved: 4,
      },
    });
    runFinanceControllerAgentPlanMock.mockReset();
    runFinanceControllerAgentPlanMock.mockResolvedValue({
      run_id: mockFinanceAgentRun.run_id,
      records_processed: 5,
      unresolved_count: 4,
      pending_approval_count: 4,
      decisions_by_type: {},
      batch_analysis: {
        records_processed: 5,
        reconciled_count: 1,
        exception_count: 5,
        unresolved_count: 4,
        approval_required_count: 4,
        decisions_by_type: {},
      },
      prioritized_work_queue: [],
      agent_plan: {
        objective: "plan",
        observations: [],
        prioritized_work: [],
        proposed_actions: [],
        unresolved_cases: { count: 4, by_decision: {}, by_exception: {} },
        human_approval_requirements: {
          required_count: 4,
          rule: "approval",
          money_moved: false,
        },
      },
    });
    getFinanceControllerEvaluationMock.mockReset();
    getFinanceControllerEvaluationMock.mockResolvedValue({
      dataset: "held_out_finance_controller_v1",
      held_out: true,
      measurement_note: "Measured on the held-out synthetic evaluation dataset.",
      records_evaluated: 69,
      correct_decisions: 69,
      incorrect_decisions: 0,
      accuracy: 1.0,
    });
    getFinanceDemoStatusMock.mockReset();
    getFinanceDemoStatusMock.mockResolvedValue({
      ready: true,
      checks: {
        api_reachable: true,
        reconciliation_data_available: true,
        agent_endpoint_available: true,
        evaluation_endpoint_available: true,
      },
      operational_batch: { label: "Operational batch", records: 100 },
      held_out_evaluation: {
        label: "Held-out evaluation",
        records_evaluated: 69,
        accuracy: 1.0,
      },
      money_moved: false,
      simulated_actions_only: true,
      human_approval_required: true,
      gemini_in_decision_path: false,
      secrets_exposed: false,
    });
    resetFinanceDemoActionsMock.mockReset();
    resetFinanceDemoActionsMock.mockResolvedValue({
      reset: true,
      scope: "local_demo_action_store",
      datasets_untouched: true,
      evaluation_untouched: true,
      policy_untouched: true,
      reconciliation_untouched: true,
      money_moved: false,
      secrets_exposed: false,
      note: "Cleared.",
    });
  });

  it("renders the upload area and action buttons", () => {
    renderPage();
    expect(screen.getByRole("region", { name: /bank csv upload area/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /load demo csv/i })).toBeInTheDocument();
  });

  it("shows Bank Import in page header", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /bank csv import/i })).toBeInTheDocument();
  });

  it("run reconciliation button is disabled with no file selected", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeDisabled();
  });

  it("load demo csv pre-fills a file and enables run", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    expect(screen.getByRole("button", { name: /run reconciliation/i })).not.toBeDisabled();
    expect(screen.getByText(/demo_bank\.csv/)).toBeInTheDocument();
  });

  it("calls importBankCsv when run reconciliation is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(importMock).toHaveBeenCalledTimes(1));
    const [file] = importMock.mock.calls[0] as [File];
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe("demo_bank.csv");
  });

  it("does not call live razorpay sync when importing", async () => {
    const syncMock = vi.fn();
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(importMock).toHaveBeenCalledTimes(1));
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("shows reconciliation summary after successful import", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByText(/reconciliation summary/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/uploaded_csv/i)).toBeInTheDocument();
  });

  it("renders results table with order rows after import", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("import-results-table")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument();
    expect(screen.getByText(/demo scenarios/i)).toBeInTheDocument();
    expect(screen.getAllByText(/bank amount mismatch/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/missing bank/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/refund adjusted/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/missing settlement/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0001").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0002").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0003").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0033").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("primary-failure-badge")).toHaveTextContent(/Primary failure demo/i);
    expect(screen.getByTestId("demo-walkthrough-hint")).toHaveTextContent(/ORD_0002/i);
  });

  it("clicking a demo scenario opens the order drawer", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: /open ORD_0002/i }));
    expect(
      screen.getByRole("dialog", { name: /order details for ORD_0002/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /audit trail/i })).toBeInTheDocument();
    expect(screen.getAllByText("Bank Amount Mismatch").length).toBeGreaterThanOrEqual(1);
  });

  it("shows all four scenario statuses in results", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument(),
    );
    // Statuses shown via StatusBadge (formatStatusLabel → sentence case)
    // Demo scenarios + full table duplicate badges; MetricCard also says "Reconciled".
    expect(screen.getAllByText("Reconciled").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Settlement amount").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Missing bank/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("With refund adjustment").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Missing settlement/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows error state when import fails", async () => {
    const user = userEvent.setup();
    importMock.mockRejectedValue(new ApiClientError("Server error", 500));
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(screen.getByText(/server error/i)).toBeInTheDocument());
    expect(screen.queryByTestId("import-results-table")).not.toBeInTheDocument();
  });

  it("shows error state when import returns validation error", async () => {
    const user = userEvent.setup();
    importMock.mockRejectedValue(
      new ApiClientError("Bank CSV is missing required columns: description", 400),
    );
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByText(/missing required columns/i)).toBeInTheDocument(),
    );
  });

  it("remove button clears file and resets state", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    expect(screen.getByText(/demo_bank\.csv/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove/i }));
    expect(screen.queryByText(/demo_bank\.csv/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeDisabled();
  });
});

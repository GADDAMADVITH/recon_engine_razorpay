import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentDecisionSection } from "../components/finance/AgentDecisionSection";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import { ChatOrderProvider } from "../context/ChatOrderContext";
import { ConsoleReportProvider } from "../context/ConsoleReportContext";
import { BankImportPage } from "../pages/BankImportPage";
import { DashboardPage } from "../pages/DashboardPage";
import {
  makeFinanceDecision,
  mockFinanceAgentRun,
  mockFinanceControllerBatch,
  mockHookState,
  mockReport,
} from "./fixtures";
import type { FinanceAgentRunResponse, OrderResult } from "../types/api";

const runFinanceControllerMock = vi.fn();
const runFinanceControllerAgentMock = vi.fn();
const getFinanceApprovalQueueMock = vi.fn();
const runFinanceControllerAgentPlanMock = vi.fn();
const getFinanceControllerEvaluationMock = vi.fn();
const getFinanceDemoStatusMock = vi.fn();
const resetFinanceDemoActionsMock = vi.fn();
const importMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      runFinanceController: (...args: unknown[]) => runFinanceControllerMock(...args),
      runFinanceControllerAgent: (...args: unknown[]) => runFinanceControllerAgentMock(...args),
      getFinanceApprovalQueue: (...args: unknown[]) => getFinanceApprovalQueueMock(...args),
      runFinanceControllerAgentPlan: (...args: unknown[]) =>
        runFinanceControllerAgentPlanMock(...args),
      getFinanceControllerEvaluation: (...args: unknown[]) =>
        getFinanceControllerEvaluationMock(...args),
      getFinanceDemoStatus: (...args: unknown[]) => getFinanceDemoStatusMock(...args),
      resetFinanceDemoActions: (...args: unknown[]) => resetFinanceDemoActionsMock(...args),
      importBankCsv: (...args: unknown[]) => importMock(...args),
    },
  };
});

vi.mock("../hooks/useApi", async () => {
  const actual = await vi.importActual<typeof import("../hooks/useApi")>("../hooks/useApi");
  return {
    ...actual,
    useReconciliationReport: vi.fn(),
    useHealth: vi.fn(() => ({
      data: { status: "ok", service: "recon-engine-api", version: "v1" },
      loading: false,
      refreshing: false,
      error: null,
      refetch: vi.fn(),
    })),
  };
});

vi.mock("../hooks/useRazorpaySync", () => ({
  useRazorpaySync: vi.fn(() => ({
    report: null,
    response: null,
    loading: false,
    error: null,
    empty: false,
    sync: vi.fn(),
    reset: vi.fn(),
  })),
}));

import { useReconciliationReport } from "../hooks/useApi";

const mockedUseReport = vi.mocked(useReconciliationReport);

function demoOrders(): OrderResult[] {
  return [
    {
      ...mockReport.order_results[0],
      order_id: "ORD_0001",
      status: "reconciled",
      reconciled: true,
      confidence_score: 100,
      exceptions: [],
    },
    {
      ...mockReport.order_results[0],
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 40,
      exceptions: [{ type: "BANK_AMOUNT_MISMATCH", message: "Bank mismatch" }],
    },
    {
      ...mockReport.order_results[0],
      order_id: "ORD_0003",
      status: "unreconciled_missing_bank",
      reconciled: false,
      confidence_score: 35,
      valid_bank_transaction_id: null,
      exceptions: [{ type: "MISSING_BANK_TRANSACTION", message: "Missing bank" }],
    },
    {
      ...mockReport.order_results[0],
      order_id: "ORD_0033",
      status: "reconciled_with_refund_adjustment",
      reconciled: true,
      confidence_score: 95,
      total_refund_paise: 1000,
      exceptions: [{ type: "REFUND_ADJUSTED", message: "Refund adjusted" }],
    },
    {
      ...mockReport.order_results[0],
      order_id: "ORD_0024",
      status: "unreconciled_missing_settlement",
      reconciled: false,
      confidence_score: 20,
      primary_settlement_id: null,
      exceptions: [{ type: "MISSING_SETTLEMENT", message: "Missing settlement" }],
    },
  ];
}

function demoAgentRun(): FinanceAgentRunResponse {
  return {
    ...mockFinanceAgentRun,
    records_processed: 5,
    no_action_count: 1,
    review_required_count: 4,
    unresolved_count: 4,
    pending_approval_count: 4,
    exception_count: 5,
    decisions_by_type: {
      NO_ACTION: 1,
      FLAG_FOR_REVIEW: 1,
      ESCALATE_MISSING_BANK: 1,
      VERIFY_REFUND: 1,
      ESCALATE_MISSING_SETTLEMENT: 1,
    },
    decisions: mockFinanceAgentRun.decisions,
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ConsoleReportProvider>
        <ChatOrderProvider>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
          </Routes>
        </ChatOrderProvider>
      </ConsoleReportProvider>
    </MemoryRouter>,
  );
}

describe("Finance Controller dashboard panel", () => {
  beforeEach(() => {
    mockedUseReport.mockReturnValue(mockHookState(mockReport));
    runFinanceControllerMock.mockReset();
    runFinanceControllerMock.mockResolvedValue(mockFinanceControllerBatch);
    runFinanceControllerAgentMock.mockReset();
    runFinanceControllerAgentMock.mockResolvedValue(mockFinanceAgentRun);
    getFinanceApprovalQueueMock.mockReset();
    getFinanceApprovalQueueMock.mockResolvedValue({
      run_id: mockFinanceAgentRun.run_id,
      pending_count: 0,
      items: [],
      lifecycle: {
        run_id: mockFinanceAgentRun.run_id,
        total_decisions: 100,
        no_action: 40,
        pending_approval: 0,
        approved: 0,
        rejected: 0,
        recorded: 0,
        unresolved: 60,
      },
    });
    runFinanceControllerAgentPlanMock.mockReset();
    runFinanceControllerAgentPlanMock.mockResolvedValue({
      run_id: mockFinanceAgentRun.run_id,
      records_processed: 100,
      unresolved_count: 60,
      pending_approval_count: 60,
      decisions_by_type: mockFinanceAgentRun.decisions_by_type,
      batch_analysis: {
        records_processed: 100,
        reconciled_count: 52,
        exception_count: 100,
        unresolved_count: 60,
        approval_required_count: 60,
        decisions_by_type: mockFinanceAgentRun.decisions_by_type,
      },
      prioritized_work_queue: [],
      agent_plan: {
        objective: "Close one finance-ops loop.",
        observations: ["Processed 100 records."],
        prioritized_work: [],
        proposed_actions: [],
        unresolved_cases: { count: 60, by_decision: {}, by_exception: {} },
        human_approval_requirements: {
          required_count: 60,
          rule: "Approval required for non-NO_ACTION.",
          money_moved: false,
        },
      },
    });
    getFinanceControllerEvaluationMock.mockReset();
    getFinanceControllerEvaluationMock.mockResolvedValue({
      dataset: "held_out_finance_controller_v1",
      held_out: true,
      measurement_note:
        "Measured on the held-out synthetic evaluation dataset. This is not a claim of production accuracy.",
      records_evaluated: 69,
      correct_decisions: 69,
      incorrect_decisions: 0,
      accuracy: 1.0,
      errors: [],
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
      note: "Cleared simulated finance action records.",
    });
  });

  it("loads Finance Controller metrics from the API", async () => {
    renderDashboard();
    await waitFor(() =>
      expect(screen.getByTestId("finance-controller-panel")).toBeInTheDocument(),
    );
    expect(runFinanceControllerAgentMock).toHaveBeenCalled();
    const metrics = screen.getByTestId("agent-run-metrics");
    expect(within(metrics).getByText("Records processed")).toBeInTheDocument();
    expect(within(metrics).getByText("No action")).toBeInTheDocument();
    expect(within(metrics).getByText("Review required")).toBeInTheDocument();
    expect(within(metrics).getByText("Pending approval")).toBeInTheDocument();
    expect(within(metrics).getByText("Unresolved")).toBeInTheDocument();
    expect(within(metrics).getByText("Latest run duration")).toBeInTheDocument();
    expect(within(metrics).getAllByText("100").length).toBeGreaterThanOrEqual(1);
  });

  it("renders correct metric values from the API response", async () => {
    renderDashboard();
    const metrics = await screen.findByTestId("agent-run-metrics");
    expect(within(metrics).getByText("40")).toBeInTheDocument();
    expect(within(metrics).getAllByText("60")).toHaveLength(3);
    expect(within(metrics).getAllByText("100")).toHaveLength(1);
    const breakdown = screen.getByTestId("finance-controller-breakdown");
    expect(within(breakdown).getByText("NO_ACTION")).toBeInTheDocument();
    expect(within(breakdown).getByText("FLAG_FOR_REVIEW")).toBeInTheDocument();
    expect(within(breakdown).getByText("ESCALATE_MISSING_BANK")).toBeInTheDocument();
    expect(within(breakdown).getByText("VERIFY_REFUND")).toBeInTheDocument();
    expect(within(breakdown).getByText("ESCALATE_MISSING_SETTLEMENT")).toBeInTheDocument();
  });

  it("shows the decision architecture flow", async () => {
    renderDashboard();
    const architecture = await screen.findByTestId("finance-controller-architecture");
    expect(within(architecture).getByText("Reconciliation Engine")).toBeInTheDocument();
    expect(within(architecture).getByText("Finance Controller Agent")).toBeInTheDocument();
    expect(within(architecture).getByText("Agent Orchestration")).toBeInTheDocument();
    expect(within(architecture).getByText(/Human Approval/i)).toBeInTheDocument();
    expect(within(architecture).getByText(/does not alter engine results/i)).toBeInTheDocument();
  });

  it("shows evaluator-facing operational story and held-out separation", async () => {
    renderDashboard();
    expect(await screen.findByTestId("finance-ops-workflow")).toBeInTheDocument();
    expect(screen.getByTestId("money-moved-false-badge")).toHaveTextContent(/Money moved: false/i);
    expect(screen.getByText(/60 require human review/i)).toBeInTheDocument();
    expect(await screen.findByTestId("exception-summary")).toBeInTheDocument();
    expect(await screen.findByTestId("held-out-evaluation")).toBeInTheDocument();
    expect(screen.getByTestId("held-out-agreement-copy")).toHaveTextContent(
      /100% agreement with human-authored labels on 69 synthetic held-out records/i,
    );
    expect(screen.getByTestId("held-out-measurement-note")).toHaveTextContent(
      /not a claim of production accuracy/i,
    );
    expect(await screen.findByTestId("demo-readiness")).toBeInTheDocument();
    expect(screen.getByTestId("demo-readiness-badge")).toHaveTextContent(/Ready/i);
  });

  it("shows loading state while the agent batch is in flight", async () => {
    let resolveBatch: (value: FinanceAgentRunResponse) => void = () => {};
    runFinanceControllerAgentMock.mockImplementation(
      () =>
        new Promise<FinanceAgentRunResponse>((resolve) => {
          resolveBatch = resolve;
        }),
    );
    renderDashboard();
    expect(
      await screen.findByText(/Running Finance Controller on reconciliation results/i),
    ).toBeInTheDocument();
    resolveBatch(mockFinanceAgentRun);
    await waitFor(() =>
      expect(screen.getByTestId("agent-run-metrics")).toBeInTheDocument(),
    );
  });

  it("shows error state when the Finance Controller API fails", async () => {
    runFinanceControllerAgentMock.mockRejectedValue(new Error("boom"));
    renderDashboard();
    expect(await screen.findByText(/Unable to run Finance Controller/i)).toBeInTheDocument();
  });
});

describe("Agent Decision section", () => {
  const order = demoOrders()[0];

  it("NO_ACTION does not require approval", () => {
    const decision = makeFinanceDecision("ORD_0001", "NO_ACTION");
    render(
      <AgentDecisionSection order={order} decision={decision} />,
    );
    expect(screen.getByTestId("agent-decision-type")).toHaveTextContent("NO_ACTION");
    expect(screen.getByTestId("no-approval-badge")).toHaveTextContent(/No action required/i);
    expect(screen.queryByTestId("approval-required-badge")).not.toBeInTheDocument();
  });

  it("non-NO_ACTION requires approval", () => {
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_reconciled: false,
    });
    render(
      <AgentDecisionSection order={demoOrders()[1]} decision={decision} />,
    );
    expect(screen.getByTestId("approval-required-badge")).toHaveTextContent(/Requires approval/i);
    expect(screen.queryByText(/^Approved$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Executed$/i)).not.toBeInTheDocument();
  });

  it("keeps original reconciliation status unchanged beside the agent decision", () => {
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_status: "unreconciled_settlement_amount",
      original_reconciled: false,
      confidence_score: 40,
    });
    render(
      <AgentDecisionSection order={demoOrders()[1]} decision={decision} />,
    );
    const original = screen.getByTestId("original-result-panel");
    expect(within(original).getByText(/Unchanged by the agent/i)).toBeInTheDocument();
    expect(within(original).getByText("40%")).toBeInTheDocument();
    expect(within(original).getByText("No")).toBeInTheDocument();
    expect(screen.getByTestId("agent-decision-type")).toHaveTextContent("FLAG_FOR_REVIEW");
  });
});

describe("Order Detail Drawer agent decision", () => {
  it("loads agent decision from the same order_result payload", async () => {
    const order = demoOrders()[1];
    const trace = mockFinanceAgentRun.decisions[1];
    runFinanceControllerAgentMock.mockResolvedValue({
      ...demoAgentRun(),
      decisions: [trace],
    });

    render(
      <ChatOrderProvider>
        <OrderDetailDrawer order={order} onClose={() => {}} />
      </ChatOrderProvider>,
    );

    expect(await screen.findByTestId("agent-decision-section")).toBeInTheDocument();
    expect(screen.getByTestId("agent-decision-type")).toHaveTextContent("FLAG_FOR_REVIEW");
    expect(screen.getByTestId("approval-required-badge")).toBeInTheDocument();
    expect(runFinanceControllerAgentMock).toHaveBeenCalledWith({ order_results: [order] });
    expect(screen.getByTestId("decision-trace-panel")).toBeInTheDocument();
    expect(screen.getByTestId("decision-trace-proposed-action")).toHaveTextContent("RECORD_REVIEW");
    expect(screen.getByTestId("original-result-panel")).toHaveTextContent(
      String(order.confidence_score),
    );
  });

  it("uses a parent-provided decision without refetching", async () => {
    const order = demoOrders()[2];
    const decision = makeFinanceDecision("ORD_0003", "ESCALATE_MISSING_BANK", {
      original_status: order.status,
      original_reconciled: false,
    });
    runFinanceControllerAgentMock.mockClear();

    render(
      <ChatOrderProvider>
        <OrderDetailDrawer order={order} agentDecision={decision} onClose={() => {}} />
      </ChatOrderProvider>,
    );

    expect(await screen.findByTestId("agent-decision-type")).toHaveTextContent(
      "ESCALATE_MISSING_BANK",
    );
    expect(runFinanceControllerAgentMock).not.toHaveBeenCalled();
  });
});

describe("Bank Import demo scenario agent decisions", () => {
  beforeEach(() => {
    importMock.mockReset();
    runFinanceControllerAgentMock.mockReset();
    getFinanceApprovalQueueMock.mockReset();
    getFinanceApprovalQueueMock.mockResolvedValue({
      run_id: "FCRUN_test100batch",
      pending_count: 4,
      items: [],
      lifecycle: {
        run_id: "FCRUN_test100batch",
        total_decisions: 5,
        no_action: 1,
        pending_approval: 4,
        approved: 0,
        rejected: 0,
        recorded: 0,
        unresolved: 4,
      },
    });
    const orders = demoOrders();
    importMock.mockResolvedValue({
      ...mockReport,
      metadata: {
        ...mockReport.metadata,
        bank_source: "uploaded_csv",
        bank_rows_imported: 3,
      },
      summary: {
        ...mockReport.summary,
        total_orders: orders.length,
        reconciled_orders: 2,
        unreconciled_orders: 3,
      },
      order_results: orders,
    });
    runFinanceControllerAgentMock.mockResolvedValue(demoAgentRun());
  });

  async function runDemoImport() {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatOrderProvider>
          <BankImportPage />
        </ChatOrderProvider>
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(importMock).toHaveBeenCalled());
    await waitFor(() => expect(runFinanceControllerAgentMock).toHaveBeenCalled());
  }

  it("renders demo scenario agent decisions from imported order_results", async () => {
    await runDemoImport();
    expect(await screen.findByTestId("agent-chip-ORD_0001")).toHaveTextContent("NO_ACTION");
    expect(screen.getByTestId("agent-chip-ORD_0002")).toHaveTextContent("FLAG_FOR_REVIEW");
    expect(screen.getByTestId("agent-chip-ORD_0003")).toHaveTextContent("ESCALATE_MISSING_BANK");
    expect(screen.getByTestId("agent-chip-ORD_0033")).toHaveTextContent("VERIFY_REFUND");
    expect(screen.getByTestId("agent-chip-ORD_0024")).toHaveTextContent(
      "ESCALATE_MISSING_SETTLEMENT",
    );
  });

  it("ORD_0002 shows FLAG_FOR_REVIEW with approval required", async () => {
    const user = userEvent.setup();
    await runDemoImport();
    await user.click(screen.getByRole("button", { name: /Open ORD_0002/i }));
    expect(await screen.findByTestId("agent-decision-type")).toHaveTextContent("FLAG_FOR_REVIEW");
    expect(screen.getByTestId("approval-required-badge")).toBeInTheDocument();
    expect(screen.getByTestId("original-result-panel")).toHaveTextContent(/Unchanged by the agent/i);
    expect(screen.getByTestId("decision-trace-panel")).toBeInTheDocument();
  });

  it("ORD_0003 shows ESCALATE_MISSING_BANK", async () => {
    const user = userEvent.setup();
    await runDemoImport();
    await user.click(screen.getByRole("button", { name: /Open ORD_0003/i }));
    expect(await screen.findByTestId("agent-decision-type")).toHaveTextContent(
      "ESCALATE_MISSING_BANK",
    );
  });

  it("ORD_0033 shows VERIFY_REFUND", async () => {
    const user = userEvent.setup();
    await runDemoImport();
    await user.click(screen.getByRole("button", { name: /Open ORD_0033/i }));
    expect(await screen.findByTestId("agent-decision-type")).toHaveTextContent("VERIFY_REFUND");
    expect(screen.getByTestId("approval-required-badge")).toBeInTheDocument();
  });

  it("ORD_0024 shows ESCALATE_MISSING_SETTLEMENT", async () => {
    const user = userEvent.setup();
    await runDemoImport();
    await user.click(screen.getByRole("button", { name: /Open ORD_0024/i }));
    expect(await screen.findByTestId("agent-decision-type")).toHaveTextContent(
      "ESCALATE_MISSING_SETTLEMENT",
    );
  });

  it("calls Finance Controller agent with the same imported order_results", async () => {
    await runDemoImport();
    const call = runFinanceControllerAgentMock.mock.calls[0]?.[0] as {
      order_results: OrderResult[];
    };
    expect(call.order_results.map((o) => o.order_id)).toEqual([
      "ORD_0001",
      "ORD_0002",
      "ORD_0003",
      "ORD_0033",
      "ORD_0024",
    ]);
  });
});

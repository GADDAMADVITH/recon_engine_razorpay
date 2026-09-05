import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentRunLauncher } from "../components/finance/AgentRunLauncher";
import { mockFinanceAgentRun, mockReport } from "./fixtures";
import type { FinanceAgentPlanResponse } from "../types/api";

const runAgentMock = vi.fn();
const planMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      runFinanceControllerAgent: (...args: unknown[]) => runAgentMock(...args),
      runFinanceControllerAgentPlan: (...args: unknown[]) => planMock(...args),
    },
  };
});

function samplePlan(overrides: Partial<FinanceAgentPlanResponse> = {}): FinanceAgentPlanResponse {
  return {
    run_id: mockFinanceAgentRun.run_id,
    records_processed: mockFinanceAgentRun.records_processed,
    unresolved_count: mockFinanceAgentRun.unresolved_count,
    pending_approval_count: mockFinanceAgentRun.pending_approval_count,
    decisions_by_type: mockFinanceAgentRun.decisions_by_type,
    batch_analysis: {
      records_processed: mockFinanceAgentRun.records_processed,
      reconciled_count: 52,
      exception_count: 100,
      unresolved_count: mockFinanceAgentRun.unresolved_count,
      approval_required_count: mockFinanceAgentRun.pending_approval_count,
      decisions_by_type: mockFinanceAgentRun.decisions_by_type,
    },
    prioritized_work_queue: [
      {
        order_id: "ORD_0024",
        priority: 105,
        decision: "ESCALATE_MISSING_SETTLEMENT",
        exceptions: ["MISSING_SETTLEMENT"],
        rationale: "Settlement is missing; escalation is required.",
        proposed_action: "RECORD_MISSING_SETTLEMENT_ESCALATION",
        requires_approval: true,
        original_result: {
          order_id: "ORD_0024",
          status: "unreconciled_missing_settlement",
          reconciled: false,
          confidence_score: 20,
          exception_types: ["MISSING_SETTLEMENT"],
        },
      },
    ],
    agent_plan: {
      objective: "Close one finance-ops loop.",
      observations: ["Processed records from API."],
      prioritized_work: [],
      proposed_actions: [{ action: "RECORD_MISSING_SETTLEMENT_ESCALATION", count: 8 }],
      unresolved_cases: { count: 60, by_decision: {}, by_exception: {} },
      human_approval_requirements: {
        required_count: 60,
        rule: "Approval required.",
        money_moved: false,
      },
    },
    money_moved: false,
    ...overrides,
  };
}

describe("AgentRunLauncher", () => {
  beforeEach(() => {
    runAgentMock.mockReset();
    planMock.mockReset();
    runAgentMock.mockResolvedValue(mockFinanceAgentRun);
    planMock.mockResolvedValue(samplePlan());
  });

  function renderLauncher(
    props: Partial<ComponentProps<typeof AgentRunLauncher>> = {},
  ) {
    const { orderResults = mockReport.order_results, onComplete = vi.fn(), ...rest } = props;
    return render(
      <AgentRunLauncher
        orderResults={orderResults}
        onComplete={onComplete}
        stageDelayMs={0}
        {...rest}
      />,
    );
  }

  it("renders the Run button and ready count from order_results", () => {
    renderLauncher();
    expect(screen.getByTestId("run-finance-controller-agent")).toBeInTheDocument();
    expect(screen.getByTestId("agent-run-ready-count")).toHaveTextContent(
      `${mockReport.order_results.length} records ready`,
    );
    expect(screen.getByTestId("agent-run-idle-status")).toBeInTheDocument();
  });

  it("calls run-agent then agent-plan with order_results and shows API metrics", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    renderLauncher({ onComplete });

    await user.click(screen.getByTestId("run-finance-controller-agent"));

    await waitFor(() => expect(runAgentMock).toHaveBeenCalledTimes(1));
    expect(runAgentMock).toHaveBeenCalledWith({ order_results: mockReport.order_results });
    await waitFor(() => expect(planMock).toHaveBeenCalledTimes(1));
    expect(planMock).toHaveBeenCalledWith({ order_results: mockReport.order_results });

    expect(await screen.findByTestId("agent-run-complete-card")).toBeInTheDocument();
    const summary = screen.getByTestId("agent-run-complete-summary");
    expect(summary).toHaveTextContent(
      `${mockFinanceAgentRun.records_processed} records analyzed`,
    );
    expect(summary).toHaveTextContent(
      `${mockFinanceAgentRun.review_required_count} require human review`,
    );
    expect(summary).toHaveTextContent(
      `${mockFinanceAgentRun.no_action_count} require no action`,
    );

    const decisions = screen.getByTestId("agent-run-complete-decisions");
    for (const [decision, count] of Object.entries(mockFinanceAgentRun.decisions_by_type)) {
      expect(within(decisions).getByText(new RegExp(`${decision}:\\s*${count}`))).toBeInTheDocument();
    }

    expect(screen.getByTestId("agent-work-generated")).toBeInTheDocument();
    expect(screen.getByTestId("agent-highlight-case")).toHaveTextContent("ORD_0024");
    expect(screen.getByTestId("agent-highlight-case")).toHaveTextContent("P105");
    expect(screen.getByTestId("agent-highlight-rationale")).toHaveTextContent(/Settlement is missing/i);
    expect(onComplete).toHaveBeenCalledWith(
      mockFinanceAgentRun,
      expect.objectContaining({
        records_processed: mockFinanceAgentRun.records_processed,
      }),
    );
  });

  it("shows error state and does not show success when run-agent fails", async () => {
    const user = userEvent.setup();
    runAgentMock.mockRejectedValueOnce(new Error("boom"));
    renderLauncher();
    await user.click(screen.getByTestId("run-finance-controller-agent"));
    expect(await screen.findByTestId("agent-run-error")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-run-complete-card")).not.toBeInTheDocument();
    expect(planMock).not.toHaveBeenCalled();
  });

  it("prevents duplicate clicks while executing", async () => {
    const user = userEvent.setup();
    let resolveRun: (value: unknown) => void = () => undefined;
    runAgentMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRun = resolve;
        }),
    );
    renderLauncher();
    const button = screen.getByTestId("run-finance-controller-agent");
    await user.click(button);
    expect(button).toBeDisabled();
    await waitFor(() => expect(runAgentMock).toHaveBeenCalledTimes(1));
    await user.click(button);
    expect(runAgentMock).toHaveBeenCalledTimes(1);
    resolveRun(mockFinanceAgentRun);
    await waitFor(() => expect(planMock).toHaveBeenCalled());
  });

  it("does not hardcode metrics — API counts are rendered as returned", async () => {
    const user = userEvent.setup();
    const smallRun = {
      ...mockFinanceAgentRun,
      records_processed: 3,
      no_action_count: 1,
      review_required_count: 2,
      unresolved_count: 2,
      pending_approval_count: 2,
      decisions_by_type: { NO_ACTION: 1, FLAG_FOR_REVIEW: 2 },
    };
    runAgentMock.mockImplementation(async () => smallRun);
    planMock.mockImplementation(async () =>
      samplePlan({
        records_processed: 3,
        unresolved_count: 2,
        pending_approval_count: 2,
        decisions_by_type: { NO_ACTION: 1, FLAG_FOR_REVIEW: 2 },
        prioritized_work_queue: [],
      }),
    );
    renderLauncher({ orderResults: mockReport.order_results.slice(0, 3) });
    await user.click(screen.getByTestId("run-finance-controller-agent"));
    const summary = await screen.findByTestId("agent-run-complete-summary");
    expect(summary).toHaveTextContent("3 records analyzed");
    expect(summary).toHaveTextContent("2 require human review");
    expect(summary).toHaveTextContent("1 require no action");
    expect(summary).not.toHaveTextContent("100 records analyzed");
  });

  it("shows analyzing progress while the agent API is in flight", async () => {
    const user = userEvent.setup();
    let resolveRun: (value: unknown) => void = () => undefined;
    runAgentMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRun = resolve;
        }),
    );
    renderLauncher();
    await user.click(screen.getByTestId("run-finance-controller-agent"));
    expect(await screen.findByTestId("agent-run-progress")).toBeInTheDocument();
    expect(screen.getByText(/Finance Controller Agent is analyzing/i)).toBeInTheDocument();
    resolveRun(mockFinanceAgentRun);
    expect(await screen.findByTestId("agent-run-complete-card")).toBeInTheDocument();
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentWorkQueue } from "../components/finance/AgentWorkQueue";
import type { FinanceAgentPlanResponse } from "../types/api";
import { mockReport } from "./fixtures";

const planMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      runFinanceControllerAgentPlan: (...args: unknown[]) => planMock(...args),
    },
  };
});

function samplePlan(): FinanceAgentPlanResponse {
  return {
    run_id: "FCRUN_plan",
    records_processed: 100,
    unresolved_count: 60,
    pending_approval_count: 60,
    decisions_by_type: {
      NO_ACTION: 40,
      FLAG_FOR_REVIEW: 32,
      ESCALATE_MISSING_BANK: 10,
      VERIFY_REFUND: 10,
      ESCALATE_MISSING_SETTLEMENT: 8,
    },
    batch_analysis: {
      records_processed: 100,
      reconciled_count: 52,
      exception_count: 100,
      unresolved_count: 60,
      approval_required_count: 60,
      decisions_by_type: {
        NO_ACTION: 40,
        FLAG_FOR_REVIEW: 32,
        ESCALATE_MISSING_BANK: 10,
        VERIFY_REFUND: 10,
        ESCALATE_MISSING_SETTLEMENT: 8,
      },
    },
    prioritized_work_queue: [
      {
        order_id: "ORD_0024",
        priority: 99,
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
      {
        order_id: "ORD_0002",
        priority: 75,
        decision: "FLAG_FOR_REVIEW",
        exceptions: ["BANK_AMOUNT_MISMATCH"],
        rationale: "Amount mismatch detected; financial result requires human review.",
        proposed_action: "RECORD_REVIEW",
        requires_approval: true,
        original_result: {
          order_id: "ORD_0002",
          status: "unreconciled_settlement_amount",
          reconciled: false,
          confidence_score: 40,
          exception_types: ["BANK_AMOUNT_MISMATCH"],
        },
      },
    ],
    agent_plan: {
      objective: "Close one finance-ops loop over the reconciliation batch.",
      observations: ["Processed 100 reconciliation records."],
      prioritized_work: [],
      proposed_actions: [{ action: "RECORD_REVIEW", count: 32 }],
      unresolved_cases: {
        count: 60,
        by_decision: { FLAG_FOR_REVIEW: 32 },
        by_exception: { BANK_AMOUNT_MISMATCH: 10 },
      },
      human_approval_requirements: {
        required_count: 60,
        rule: "Every non-NO_ACTION decision requires human approval.",
        money_moved: false,
      },
    },
  };
}

describe("Agent Work Queue UI", () => {
  beforeEach(() => {
    planMock.mockReset();
    planMock.mockResolvedValue(samplePlan());
  });

  it("renders metrics and top priority cases", async () => {
    render(<AgentWorkQueue orderResults={mockReport.order_results} />);
    expect(await screen.findByTestId("agent-work-queue")).toBeInTheDocument();
    const metrics = screen.getByTestId("agent-work-queue-metrics");
    expect(within(metrics).getByText("Total records")).toBeInTheDocument();
    expect(within(metrics).getByText("100")).toBeInTheDocument();
    expect(within(metrics).getByText("Unresolved")).toBeInTheDocument();
    expect(within(metrics).getByText("Approval required")).toBeInTheDocument();
    expect(within(metrics).getAllByText("60")).toHaveLength(2);
    expect(screen.getByTestId("agent-work-item-ORD_0024")).toHaveTextContent("P99");
    expect(screen.getByTestId("work-approval-ORD_0024")).toHaveTextContent(/Approval required/i);
    expect(screen.getByTestId("agent-work-item-ORD_0002")).toHaveTextContent("RECORD_REVIEW");
  });

  it("expands the agent plan section", async () => {
    const user = userEvent.setup();
    render(<AgentWorkQueue orderResults={mockReport.order_results} />);
    await screen.findByTestId("agent-plan-toggle");
    await user.click(screen.getByTestId("agent-plan-toggle"));
    expect(await screen.findByTestId("agent-plan-body")).toHaveTextContent(/Objective/i);
    expect(screen.getByTestId("agent-plan-body")).toHaveTextContent(
      /What the agent found/i,
    );
    expect(screen.getByTestId("agent-plan-body")).toHaveTextContent(/human approval/i);
  });

  it("shows loading then error states", async () => {
    planMock.mockRejectedValueOnce(new Error("boom"));
    render(<AgentWorkQueue orderResults={mockReport.order_results} />);
    expect(await screen.findByText(/Unable to load the agent work plan/i)).toBeInTheDocument();
  });

  it("calls agent-plan with provided order_results", async () => {
    render(<AgentWorkQueue orderResults={mockReport.order_results} />);
    await waitFor(() => expect(planMock).toHaveBeenCalled());
    expect(planMock.mock.calls[0]?.[0]).toMatchObject({
      order_results: mockReport.order_results,
    });
  });
});

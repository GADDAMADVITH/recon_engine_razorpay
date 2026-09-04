import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentDecisionSection } from "../components/finance/AgentDecisionSection";
import { ApiClientError } from "../api/client";
import { makeFinanceDecision, mockReport } from "./fixtures";

const approveMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      approveFinanceAction: (...args: unknown[]) => approveMock(...args),
    },
    ApiClientError: actual.ApiClientError,
  };
});

const baseOrder = {
  ...mockReport.order_results[0],
  order_id: "ORD_0002",
  status: "unreconciled_settlement_amount" as const,
  reconciled: false,
  confidence_score: 40,
};

describe("Finance action approval UI", () => {
  beforeEach(() => {
    approveMock.mockReset();
  });

  it("shows Approve & Record Action for non-NO_ACTION decisions", () => {
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_reconciled: false,
      confidence_score: 40,
    });
    render(<AgentDecisionSection order={baseOrder} decision={decision} />);
    expect(screen.getByTestId("approve-action-button")).toBeInTheDocument();
    expect(screen.getByTestId("approval-required-badge")).toBeInTheDocument();
  });

  it("NO_ACTION has no approval button", () => {
    const decision = makeFinanceDecision("ORD_0001", "NO_ACTION");
    render(
      <AgentDecisionSection
        order={{ ...baseOrder, order_id: "ORD_0001", reconciled: true, status: "reconciled" }}
        decision={decision}
      />,
    );
    expect(screen.queryByTestId("approve-action-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("no-action-required-copy")).toHaveTextContent(/No action required/i);
  });

  it("shows loading state while approving", async () => {
    let resolveApprove: (value: unknown) => void = () => {};
    approveMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveApprove = resolve;
        }),
    );
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_reconciled: false,
    });
    const user = userEvent.setup();
    render(<AgentDecisionSection order={baseOrder} decision={decision} />);
    await user.click(screen.getByTestId("approve-action-button"));
    expect(screen.getByTestId("approve-loading")).toBeInTheDocument();
    expect(screen.getByTestId("approve-action-button")).toBeDisabled();
    resolveApprove({
      action_id: "ACT_test",
      order_id: "ORD_0002",
      agent_decision: "FLAG_FOR_REVIEW",
      action_type: "RECORD_REVIEW",
      approval_required: true,
      approval_status: "APPROVED",
      action_status: "RECORDED",
      created_at: "2026-01-01T00:00:00Z",
      approved_at: "2026-01-01T00:00:00Z",
      evidence: {},
      audit_event: {},
      simulated: true,
      money_moved: false,
      note: "Simulated",
    });
    expect(await screen.findByTestId("action-recorded-state")).toBeInTheDocument();
  });

  it("shows action-recorded state after successful approval", async () => {
    approveMock.mockResolvedValue({
      action_id: "ACT_abc",
      order_id: "ORD_0002",
      agent_decision: "FLAG_FOR_REVIEW",
      action_type: "RECORD_REVIEW",
      approval_required: true,
      approval_status: "APPROVED",
      action_status: "RECORDED",
      created_at: "2026-01-01T00:00:00Z",
      approved_at: "2026-01-01T00:00:00Z",
      evidence: {},
      audit_event: {},
      simulated: true,
      money_moved: false,
      note: "Simulated",
      idempotent_replay: false,
    });
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_reconciled: false,
      confidence_score: 40,
    });
    const user = userEvent.setup();
    render(<AgentDecisionSection order={baseOrder} decision={decision} />);
    await user.click(screen.getByTestId("approve-action-button"));
    expect(await screen.findByTestId("action-recorded-state")).toHaveTextContent(/Action recorded/i);
    expect(screen.getByTestId("recorded-action-type")).toHaveTextContent("RECORD_REVIEW");
    expect(screen.queryByText(/Refunded/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Money recovered/i)).not.toBeInTheDocument();
    expect(approveMock).toHaveBeenCalledWith({
      order_id: "ORD_0002",
      agent_decision: "FLAG_FOR_REVIEW",
      order_result: baseOrder,
    });
    // Original facts still displayed
    expect(screen.getByTestId("original-confidence")).toHaveTextContent("40%");
    expect(screen.getByTestId("original-engine-status")).toHaveTextContent(
      "unreconciled_settlement_amount",
    );
  });

  it("shows API error state", async () => {
    approveMock.mockRejectedValue(new ApiClientError("Conflict", 409));
    const decision = makeFinanceDecision("ORD_0002", "FLAG_FOR_REVIEW", {
      original_reconciled: false,
    });
    const user = userEvent.setup();
    render(<AgentDecisionSection order={baseOrder} decision={decision} />);
    await user.click(screen.getByTestId("approve-action-button"));
    expect(await screen.findByTestId("approve-error")).toHaveTextContent(/Conflict/i);
    expect(screen.getByTestId("approve-action-button")).toBeInTheDocument();
  });

  it("duplicate-safe UI: second approval still shows recorded state", async () => {
    const recordedPayload = {
      action_id: "ACT_1",
      order_id: "ORD_0003",
      agent_decision: "ESCALATE_MISSING_BANK",
      action_type: "RECORD_MISSING_BANK_ESCALATION",
      approval_required: true,
      approval_status: "APPROVED",
      action_status: "RECORDED",
      created_at: "2026-01-01T00:00:00Z",
      approved_at: "2026-01-01T00:00:00Z",
      evidence: {},
      audit_event: {},
      simulated: true,
      money_moved: false,
      note: "Simulated",
    };
    approveMock
      .mockResolvedValueOnce(recordedPayload)
      .mockResolvedValueOnce({ ...recordedPayload, idempotent_replay: true });

    const order = {
      ...baseOrder,
      order_id: "ORD_0003",
      status: "unreconciled_missing_bank" as const,
    };
    const decision = makeFinanceDecision("ORD_0003", "ESCALATE_MISSING_BANK", {
      original_reconciled: false,
    });
    const user = userEvent.setup();
    const first = render(<AgentDecisionSection order={order} decision={decision} />);
    await user.click(screen.getByTestId("approve-action-button"));
    expect(await screen.findByTestId("action-recorded-state")).toBeInTheDocument();
    first.unmount();

    // Fresh mount — local state empty; server returns the same action idempotently.
    render(<AgentDecisionSection order={order} decision={decision} />);
    await user.click(screen.getByTestId("approve-action-button"));
    expect(await screen.findByTestId("action-recorded-state")).toHaveTextContent(
      /Existing action/i,
    );
    expect(approveMock).toHaveBeenCalledTimes(2);
  });
});

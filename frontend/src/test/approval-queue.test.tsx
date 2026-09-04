import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalQueue } from "../components/finance/ApprovalQueue";
import type { FinanceApprovalQueueResponse, OrderResult } from "../types/api";
import { mockReport } from "./fixtures";

const getQueueMock = vi.fn();
const approveMock = vi.fn();
const rejectMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      getFinanceApprovalQueue: (...args: unknown[]) => getQueueMock(...args),
      approveFinanceAction: (...args: unknown[]) => approveMock(...args),
      rejectFinanceAction: (...args: unknown[]) => rejectMock(...args),
    },
  };
});

function baseQueue(overrides: Partial<FinanceApprovalQueueResponse> = {}): FinanceApprovalQueueResponse {
  return {
    run_id: "FCRUN_test",
    pending_count: 2,
    items: [
      {
        run_id: "FCRUN_test",
        order_id: "ORD_0002",
        decision: "FLAG_FOR_REVIEW",
        rationale: "Amount mismatch detected; financial result requires human review.",
        proposed_action: "RECORD_REVIEW",
        exceptions: ["BANK_AMOUNT_MISMATCH"],
        original_result: {
          order_id: "ORD_0002",
          status: "unreconciled_settlement_amount",
          reconciled: false,
          confidence_score: 40,
          exception_types: ["BANK_AMOUNT_MISMATCH"],
        },
        requires_approval: true,
        approval_status: "PENDING_APPROVAL",
        action_status: "PENDING",
        lifecycle_status: "PENDING",
        timestamp: "2026-09-04T12:00:00Z",
      },
      {
        run_id: "FCRUN_test",
        order_id: "ORD_0003",
        decision: "ESCALATE_MISSING_BANK",
        rationale: "Bank transaction is missing; escalation is required.",
        proposed_action: "RECORD_MISSING_BANK_ESCALATION",
        exceptions: ["MISSING_BANK_TRANSACTION"],
        original_result: {
          order_id: "ORD_0003",
          status: "unreconciled_missing_bank",
          reconciled: false,
          confidence_score: 35,
          exception_types: ["MISSING_BANK_TRANSACTION"],
        },
        requires_approval: true,
        approval_status: "PENDING_APPROVAL",
        action_status: "PENDING",
        lifecycle_status: "PENDING",
        timestamp: "2026-09-04T12:00:00Z",
      },
    ],
    lifecycle: {
      run_id: "FCRUN_test",
      total_decisions: 5,
      no_action: 1,
      pending_approval: 2,
      approved: 0,
      rejected: 0,
      recorded: 0,
      unresolved: 4,
    },
    ...overrides,
  };
}

const orders: OrderResult[] = [
  { ...mockReport.order_results[0], order_id: "ORD_0002" },
  { ...mockReport.order_results[0], order_id: "ORD_0003" },
];

describe("Approval Queue UI", () => {
  beforeEach(() => {
    getQueueMock.mockReset();
    approveMock.mockReset();
    rejectMock.mockReset();
    getQueueMock.mockResolvedValue(baseQueue());
    approveMock.mockResolvedValue({
      action_id: "ACT_1",
      action_status: "RECORDED",
      approval_status: "APPROVED",
      money_moved: false,
    });
    rejectMock.mockResolvedValue({
      action_id: "ACT_2",
      action_status: "REJECTED",
      approval_status: "REJECTED",
      money_moved: false,
    });
  });

  it("renders queue items and lifecycle metrics", async () => {
    render(<ApprovalQueue runId="FCRUN_test" orderResults={orders} />);
    expect(await screen.findByTestId("approval-queue")).toBeInTheDocument();
    expect(screen.getByTestId("approval-queue-pending-count")).toHaveTextContent("2 pending");
    expect(screen.getByTestId("approval-queue-item-ORD_0002")).toHaveTextContent("FLAG_FOR_REVIEW");
    expect(screen.getByTestId("approval-queue-item-ORD_0003")).toHaveTextContent(
      "ESCALATE_MISSING_BANK",
    );
    const metrics = screen.getByTestId("lifecycle-metrics");
    expect(within(metrics).getByText("Pending approval")).toBeInTheDocument();
    expect(within(metrics).getByText("Approved")).toBeInTheDocument();
    expect(within(metrics).getByText("Rejected")).toBeInTheDocument();
  });

  it("approves a pending item and refreshes the queue", async () => {
    const user = userEvent.setup();
    getQueueMock
      .mockResolvedValueOnce(baseQueue())
      .mockResolvedValueOnce(
        baseQueue({
          pending_count: 1,
          items: [
            { ...baseQueue().items[0], lifecycle_status: "RECORDED", action_status: "RECORDED" },
            baseQueue().items[1],
          ],
          lifecycle: {
            run_id: "FCRUN_test",
            total_decisions: 5,
            no_action: 1,
            pending_approval: 1,
            approved: 1,
            rejected: 0,
            recorded: 1,
            unresolved: 4,
          },
        }),
      );

    const onChanged = vi.fn();
    render(<ApprovalQueue runId="FCRUN_test" orderResults={orders} onChanged={onChanged} />);
    await screen.findByTestId("approve-queue-ORD_0002");
    await user.click(screen.getByTestId("approve-queue-ORD_0002"));
    await waitFor(() => expect(approveMock).toHaveBeenCalled());
    expect(approveMock.mock.calls[0]?.[0]).toMatchObject({
      order_id: "ORD_0002",
      agent_decision: "FLAG_FOR_REVIEW",
      run_id: "FCRUN_test",
    });
    await waitFor(() => expect(getQueueMock).toHaveBeenCalledTimes(2));
    expect(onChanged).toHaveBeenCalled();
  });

  it("rejects a pending item", async () => {
    const user = userEvent.setup();
    getQueueMock
      .mockResolvedValueOnce(baseQueue())
      .mockResolvedValueOnce(
        baseQueue({
          pending_count: 1,
          items: [
            baseQueue().items[0],
            { ...baseQueue().items[1], lifecycle_status: "REJECTED", action_status: "REJECTED" },
          ],
          lifecycle: {
            run_id: "FCRUN_test",
            total_decisions: 5,
            no_action: 1,
            pending_approval: 1,
            approved: 0,
            rejected: 1,
            recorded: 0,
            unresolved: 4,
          },
        }),
      );

    render(<ApprovalQueue runId="FCRUN_test" orderResults={orders} />);
    await user.click(await screen.findByTestId("reject-queue-ORD_0003"));
    await waitFor(() => expect(rejectMock).toHaveBeenCalled());
    expect(rejectMock.mock.calls[0]?.[0]).toMatchObject({
      order_id: "ORD_0003",
      agent_decision: "ESCALATE_MISSING_BANK",
    });
  });

  it("shows loading then error states", async () => {
    getQueueMock.mockRejectedValueOnce(new Error("boom"));
    render(<ApprovalQueue runId="FCRUN_test" orderResults={orders} />);
    expect(await screen.findByText(/Unable to load the approval queue/i)).toBeInTheDocument();
  });

  it("shows empty state when nothing is pending", async () => {
    getQueueMock.mockResolvedValue(
      baseQueue({
        pending_count: 0,
        items: [
          { ...baseQueue().items[0], lifecycle_status: "RECORDED" },
          { ...baseQueue().items[1], lifecycle_status: "REJECTED" },
        ],
        lifecycle: {
          run_id: "FCRUN_test",
          total_decisions: 5,
          no_action: 1,
          pending_approval: 0,
          approved: 1,
          rejected: 1,
          recorded: 1,
          unresolved: 4,
        },
      }),
    );
    render(<ApprovalQueue runId="FCRUN_test" orderResults={orders} />);
    expect(await screen.findByTestId("approval-queue-empty")).toBeInTheDocument();
  });
});

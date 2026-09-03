import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "../api/client";
import { AuditTrailPanel } from "../components/audit/AuditTrailPanel";

const orderAuditMock = vi.fn();
const orderAuditExplanationMock = vi.fn();
const orderAuditFromResultMock = vi.fn();
const orderAuditExplanationFromResultMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      orderAudit: (...args: unknown[]) => orderAuditMock(...args),
      orderAuditExplanation: (...args: unknown[]) => orderAuditExplanationMock(...args),
      orderAuditFromResult: (...args: unknown[]) => orderAuditFromResultMock(...args),
      orderAuditExplanationFromResult: (...args: unknown[]) =>
        orderAuditExplanationFromResultMock(...args),
    },
  };
});

const mockAudit = {
  order_id: "ORD_0002",
  status: "unreconciled_settlement_amount",
  reconciled: false,
  confidence_score: 40,
  order_amount_paise: 100000,
  checks: [
    {
      rule: "RULE_2_SETTLEMENT_TO_BANK",
      label: "Settlement -> Bank matching",
      passed: false,
      outcome: "Bank amount mismatch",
      exception_type: "BANK_AMOUNT_MISMATCH",
      exception: { type: "BANK_AMOUNT_MISMATCH", message: "Bank amount differs" },
    },
  ],
  timestamp_check: null,
  amount_summary: {
    order_amount_paise: 100000,
    settlement_gross_paise: 100000,
    settlement_net_paise: 96200,
    bank_amount_paise: 95200,
    total_refund_paise: 0,
    settlement_gross_matches_order: true,
    bank_matches_settlement_net: false,
    settlement_reflects_refund: null,
  },
  references: {
    settlement_ids_considered: ["SET_0002"],
    primary_settlement_id: "SET_0002",
    secondary_settlement_ids: [],
    bank_transaction_ids_considered: ["BNK_0002"],
    valid_bank_transaction_id: "BNK_0002",
    refund_ids: [],
    normalized_references: {},
  },
  exceptions: [{ type: "BANK_AMOUNT_MISMATCH", message: "Bank amount differs" }],
  timeline: ["Order evaluated", "Bank amount mismatch found"],
};

describe("AuditTrailPanel AI explanation", () => {
  beforeEach(() => {
    orderAuditMock.mockReset();
    orderAuditExplanationMock.mockReset();
    orderAuditFromResultMock.mockReset();
    orderAuditExplanationFromResultMock.mockReset();
    orderAuditMock.mockResolvedValue(mockAudit);
    orderAuditFromResultMock.mockResolvedValue(mockAudit);
    const explanation = {
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 40,
      explanation:
        "Summary:\nThis order is unreconciled.\n\nWhy:\n- Bank amount does not match settlement net.\n\nWhat needs attention:\n- Review bank statement mapping.",
      provider: "gemini" as const,
      model: "gemini-3.5-flash",
    };
    orderAuditExplanationMock.mockResolvedValue(explanation);
    orderAuditExplanationFromResultMock.mockResolvedValue(explanation);
  });

  it("renders Explain with AI button", async () => {
    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /explain with ai/i })).toBeInTheDocument();
  });

  it("uses orderResult POST APIs when orderResult is provided", async () => {
    const user = userEvent.setup();
    const orderResult = {
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount" as const,
      reconciled: false,
      confidence_score: 40,
      order_amount_paise: 100000,
      settlement_ids_considered: ["SET_0002"],
      primary_settlement_id: "SET_0002",
      secondary_settlement_ids: [],
      refund_ids: [],
      total_refund_paise: 0,
      bank_transaction_ids_considered: ["BNK_0002"],
      valid_bank_transaction_id: "BNK_0002",
      normalized_references: {},
      amount_comparison: {
        order_amount_paise: 100000,
        settlement_gross_paise: 100000,
        settlement_net_paise: 96200,
        bank_amount_paise: 95200,
        expected_post_refund_gross_paise: null,
        total_refund_paise: 0,
        settlement_gross_matches_order: true,
        bank_matches_settlement_net: false,
        settlement_reflects_refund: null,
      },
      timestamp_comparison: {
        settlement_settled_at: null,
        bank_transaction_date: null,
        within_tolerance: true,
        difference_hours: 1,
        tolerance_hours: 24,
      },
      rules_triggered: ["RULE_2_SETTLEMENT_TO_BANK"],
      exceptions: [{ type: "BANK_AMOUNT_MISMATCH" as const, message: "Bank amount differs" }],
      audit_trail: ["Bank amount mismatch found"],
    };
    render(<AuditTrailPanel orderId="ORD_0002" orderResult={orderResult} />);
    await waitFor(() => expect(orderAuditFromResultMock).toHaveBeenCalledTimes(1));
    expect(orderAuditMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() =>
      expect(orderAuditExplanationFromResultMock).toHaveBeenCalledWith(orderResult),
    );
    expect(orderAuditExplanationMock).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByText(/does not change reconciliation status/i),
      ).toBeInTheDocument(),
    );
  });

  it("clicking button calls explanation endpoint", async () => {
    const user = userEvent.setup();
    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() => expect(orderAuditExplanationMock).toHaveBeenCalledWith("ORD_0002"));
  });

  it("shows loading state while explanation is in progress", async () => {
    const user = userEvent.setup();
    let resolveExplanation: (value: unknown) => void = () => {};
    orderAuditExplanationMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveExplanation = resolve;
        }),
    );

    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generating explanation/i })).toBeInTheDocument(),
    );
    resolveExplanation({
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 40,
      explanation: "Summary:\nDelayed explanation",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });
    await waitFor(() => expect(screen.getByText(/delayed explanation/i)).toBeInTheDocument());
  });

  it("renders explanation card on success", async () => {
    const user = userEvent.setup();
    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() => expect(screen.getByText(/ai explanation/i)).toBeInTheDocument());
    expect(screen.getByText(/this order is unreconciled/i)).toBeInTheDocument();
  });

  it("shows error when explanation API fails", async () => {
    const user = userEvent.setup();
    orderAuditExplanationMock.mockRejectedValue(
      new ApiClientError("Gemini is not configured on the server", 503),
    );
    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() => expect(screen.getByText(/ai explanation unavailable/i)).toBeInTheDocument());
    expect(screen.getByText(/gemini is not configured/i)).toBeInTheDocument();
  });

  it("retry triggers explanation API again", async () => {
    const user = userEvent.setup();
    orderAuditExplanationMock
      .mockRejectedValueOnce(new ApiClientError("Gemini failure", 502))
      .mockResolvedValueOnce({
        order_id: "ORD_0002",
        status: "unreconciled_settlement_amount",
        reconciled: false,
        confidence_score: 40,
        explanation: "Summary:\nRecovered on retry",
        provider: "gemini",
        model: null,
      });
    render(<AuditTrailPanel orderId="ORD_0002" />);
    await waitFor(() => expect(orderAuditMock).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(orderAuditExplanationMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText(/recovered on retry/i)).toBeInTheDocument());
  });
});

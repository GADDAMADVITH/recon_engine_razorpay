import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "../api/client";
import { ReconAIChat } from "../components/chat/ReconAIChat";
import { AuditTrailPanel } from "../components/audit/AuditTrailPanel";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import { ChatOrderProvider } from "../context/ChatOrderContext";
import type { OrderResult } from "../types/api";

const chatMock = vi.fn();
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
      chat: (...args: unknown[]) => chatMock(...args),
      orderAudit: (...args: unknown[]) => orderAuditMock(...args),
      orderAuditExplanation: (...args: unknown[]) => orderAuditExplanationMock(...args),
      orderAuditFromResult: (...args: unknown[]) => orderAuditFromResultMock(...args),
      orderAuditExplanationFromResult: (...args: unknown[]) =>
        orderAuditExplanationFromResultMock(...args),
    },
  };
});

import { mockReport } from "./fixtures";

const sampleOrder: OrderResult = {
  ...mockReport.order_results[0],
  order_id: "ORD_0002",
  status: "unreconciled_settlement_amount",
  reconciled: false,
  confidence_score: 45,
  exceptions: [{ type: "BANK_AMOUNT_MISMATCH", message: "Bank amount differs" }],
  amount_comparison: {
    ...mockReport.order_results[0].amount_comparison,
    bank_matches_settlement_net: false,
  },
};

function renderChat(ui?: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={["/console"]}>
      <ChatOrderProvider>
        <Routes>
          <Route path="/console" element={ui ?? <ReconAIChat />} />
        </Routes>
      </ChatOrderProvider>
    </MemoryRouter>,
  );
}

describe("ReconEngine AI chatbot", () => {
  beforeEach(() => {
    chatMock.mockReset();
    orderAuditMock.mockReset();
    orderAuditExplanationMock.mockReset();
    orderAuditFromResultMock.mockReset();
    orderAuditExplanationFromResultMock.mockReset();
  });

  it("renders floating chatbot button", () => {
    renderChat();
    expect(screen.getByTestId("recon-ai-chat-button")).toBeInTheDocument();
  });

  it("opens chat panel on click", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    expect(screen.getByTestId("recon-ai-chat-panel")).toBeInTheDocument();
    expect(screen.getByText("ReconEngine AI")).toBeInTheDocument();
    expect(screen.getByText("Your reconciliation assistant")).toBeInTheDocument();
  });

  it("renders suggested prompts", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    expect(screen.getByRole("button", { name: /Why is ORD_0002 unreconciled/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Show me the main exceptions/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Explain ORD_0033/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /How does reconciliation work/i })).toBeInTheDocument();
  });

  it("sending a message calls POST /chat", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({
      message: "There are 24 unreconciled orders.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.type(screen.getByLabelText(/chat message/i), "How many unreconciled?");
    await user.click(screen.getByLabelText(/send message/i));
    await waitFor(() => expect(chatMock).toHaveBeenCalledTimes(1));
    expect(chatMock.mock.calls[0][0].message).toBe("How many unreconciled?");
  });

  it("shows loading state while waiting", async () => {
    const user = userEvent.setup();
    let resolveChat: (value: unknown) => void = () => {};
    chatMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveChat = resolve;
        }),
    );
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.click(screen.getByRole("button", { name: /How does reconciliation work/i }));
    expect(await screen.findByTestId("recon-ai-typing")).toBeInTheDocument();
    resolveChat({
      message: "ReconEngine matches orders to settlements and bank rows.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });
    await waitFor(() =>
      expect(screen.getByText(/matches orders to settlements/i)).toBeInTheDocument(),
    );
  });

  it("renders successful response", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({
      message: "ORD_0001 is reconciled with confidence 100.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.click(screen.getByRole("button", { name: /How does reconciliation work/i }));
    expect(await screen.findByText(/ORD_0001 is reconciled/i)).toBeInTheDocument();
  });

  it("renders error state", async () => {
    const user = userEvent.setup();
    chatMock.mockRejectedValue(new ApiClientError("Gemini request timed out", 502));
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.click(screen.getByRole("button", { name: /How does reconciliation work/i }));
    expect(await screen.findByText(/Gemini request timed out/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("retry works after error", async () => {
    const user = userEvent.setup();
    chatMock
      .mockRejectedValueOnce(new ApiClientError("temporary failure", 502))
      .mockResolvedValueOnce({
        message: "Recovered answer",
        provider: "gemini",
        model: "gemini-3.5-flash",
      });
    renderChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.click(screen.getByRole("button", { name: /How does reconciliation work/i }));
    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Recovered answer")).toBeInTheDocument();
    expect(chatMock).toHaveBeenCalledTimes(2);
  });

  it("passes current order context when an order is selected", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({
      message: "Bank amount mismatch on ORD_0002.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });

    function Harness() {
      return (
        <>
          <OrderDetailDrawer order={sampleOrder} onClose={() => {}} />
          <ReconAIChat />
        </>
      );
    }

    renderChat(<Harness />);
    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: /order details/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    expect(screen.getByText(/Context: ORD_0002/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/chat message/i), "Why did this fail?");
    await user.click(screen.getByLabelText(/send message/i));
    await waitFor(() => expect(chatMock).toHaveBeenCalledTimes(1));
    const payload = chatMock.mock.calls[0][0];
    expect(payload.order_id).toBe("ORD_0002");
    expect(payload.order_result?.order_id).toBe("ORD_0002");
    expect(payload.message).toBe("Why did this fail?");
  });

  it("keeps existing Explain with AI behavior intact", async () => {
    const user = userEvent.setup();
    const mockAudit = {
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 45,
      order_amount_paise: 100000,
      checks: [],
      timestamp_check: null,
      amount_summary: {
        order_amount_paise: sampleOrder.order_amount_paise,
        settlement_gross_paise: sampleOrder.amount_comparison.settlement_gross_paise,
        settlement_net_paise: sampleOrder.amount_comparison.settlement_net_paise,
        bank_amount_paise: sampleOrder.amount_comparison.bank_amount_paise,
        total_refund_paise: sampleOrder.total_refund_paise,
        settlement_gross_matches_order:
          sampleOrder.amount_comparison.settlement_gross_matches_order,
        bank_matches_settlement_net:
          sampleOrder.amount_comparison.bank_matches_settlement_net,
        settlement_reflects_refund: sampleOrder.amount_comparison.settlement_reflects_refund,
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
      exceptions: sampleOrder.exceptions,
      timeline: ["Order evaluated"],
    };
    orderAuditFromResultMock.mockResolvedValue(mockAudit);
    orderAuditExplanationFromResultMock.mockResolvedValue({
      order_id: "ORD_0002",
      status: "unreconciled_settlement_amount",
      reconciled: false,
      confidence_score: 45,
      explanation: "Summary:\nBank amount mismatch.\n\nWhy:\n- Amounts differ.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });

    render(
      <AuditTrailPanel orderId="ORD_0002" orderResult={sampleOrder} />,
    );
    expect(await screen.findByRole("button", { name: /explain with ai/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /explain with ai/i }));
    await waitFor(() => expect(orderAuditExplanationFromResultMock).toHaveBeenCalledTimes(1));
    expect(chatMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Bank amount mismatch/i)).toBeInTheDocument();
  });
});

describe("ReconEngine AI chatbot on landing page", () => {
  beforeEach(() => {
    chatMock.mockReset();
  });

  function renderLandingChat() {
    return render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ReconAIChat variant="landing" />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("opens chatbot and shows landing welcome state", async () => {
    const user = userEvent.setup();
    renderLandingChat();
    expect(screen.getByRole("button", { name: /Ask ReconEngine AI/i })).toBeInTheDocument();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    expect(screen.getByTestId("recon-ai-chat-panel")).toHaveAttribute("data-variant", "landing");
    expect(
      screen.getByText(/Hi — I'm ReconEngine AI\. Ask me about reconciliation, the platform, or the demo\./i),
    ).toBeInTheDocument();
  });

  it("shows landing suggested questions", async () => {
    const user = userEvent.setup();
    renderLandingChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    expect(screen.getByRole("button", { name: /What is ReconEngine\?/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /How does the demo work\?/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Explain reconciliation/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Why is ORD_0002 unreconciled/i })).not.toBeInTheDocument();
  });

  it("sends landing page_context and no order_id", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({
      message: "ReconEngine is a deterministic reconciliation engine.",
      provider: "gemini",
      model: "gemini-3.5-flash",
    });
    renderLandingChat();
    await user.click(screen.getByTestId("recon-ai-chat-button"));
    await user.click(screen.getByRole("button", { name: /What is ReconEngine\?/i }));
    await waitFor(() => expect(chatMock).toHaveBeenCalledTimes(1));
    const payload = chatMock.mock.calls[0][0];
    expect(payload.message).toBe("What is ReconEngine?");
    expect(payload.order_id).toBeNull();
    expect(payload.order_result).toBeNull();
    expect(payload.page_context).toEqual({
      page: "landing",
      mode: "product_information",
    });
  });
});

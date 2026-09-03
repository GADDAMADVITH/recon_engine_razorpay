import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TestPaymentPage from "./TestPaymentPage";
import {
  TEST_PAYMENT_DISPLAY_AMOUNT,
  TEST_PAYMENT_ORDER_ID,
} from "./constants";
import { getRazorpayKeyId } from "./razorpay-checkout";

const openTestPaymentCheckout = vi.fn();

vi.mock("./razorpay-checkout", async () => {
  const actual = await vi.importActual<typeof import("./razorpay-checkout")>("./razorpay-checkout");
  return {
    ...actual,
    getRazorpayKeyId: vi.fn(() => "rzp_test_public_key"),
    openTestPaymentCheckout: (...args: unknown[]) => openTestPaymentCheckout(...args),
    verifyPaymentWithBackend: vi.fn(async () => ({
      verified: true,
      message: "Payment signature verified by backend",
    })),
  };
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/test-payment"]}>
      <Routes>
        <Route path="/test-payment" element={<TestPaymentPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TestPaymentPage", () => {
  beforeEach(() => {
    openTestPaymentCheckout.mockReset();
    openTestPaymentCheckout.mockImplementation(async (_keyId, onSuccess) => {
      onSuccess({
        razorpay_payment_id: "pay_test123",
        razorpay_order_id: TEST_PAYMENT_ORDER_ID,
        razorpay_signature: "sig_test",
      });
    });
  });

  it("renders the temporary checkout utility", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "ReconEngine Test Payment" })).toBeInTheDocument();
    expect(screen.getByText(TEST_PAYMENT_DISPLAY_AMOUNT)).toBeInTheDocument();
    expect(screen.getByText(TEST_PAYMENT_ORDER_ID)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pay ₹500 \(Test Mode\)/i })).toBeInTheDocument();
    expect(screen.getByText("TEST MODE — Temporary Dev Utility")).toBeInTheDocument();
  });

  it("opens Razorpay Checkout for the fixed existing order", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /Pay ₹500 \(Test Mode\)/i }));

    expect(openTestPaymentCheckout).toHaveBeenCalledWith(
      "rzp_test_public_key",
      expect.any(Function),
      expect.any(Function),
    );
    expect(await screen.findByText("Checkout completed")).toBeInTheDocument();
    expect(screen.getByText("pay_test123")).toBeInTheDocument();
    expect(await screen.findByText("Payment verified by backend")).toBeInTheDocument();
  });
});

describe("TestPaymentPage without key", () => {
  it("disables pay when VITE_RAZORPAY_KEY_ID is missing", () => {
    vi.mocked(getRazorpayKeyId).mockReturnValue(undefined);
    renderPage();
    expect(screen.getByRole("button", { name: /Pay ₹500 \(Test Mode\)/i })).toBeDisabled();
    expect(screen.getByText(/VITE_RAZORPAY_KEY_ID/i)).toBeInTheDocument();
    vi.mocked(getRazorpayKeyId).mockReturnValue("rzp_test_public_key");
  });
});

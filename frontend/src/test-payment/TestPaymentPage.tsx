import { useState } from "react";
import {
  TEST_PAYMENT_DISPLAY_AMOUNT,
  TEST_PAYMENT_ORDER_ID,
} from "./constants";
import {
  getRazorpayKeyId,
  openTestPaymentCheckout,
  verifyPaymentWithBackend,
  type RazorpayCheckoutSuccessResponse,
} from "./razorpay-checkout";

type CheckoutPhase = "idle" | "opening" | "checkout_completed" | "verifying" | "verified" | "error";

export default function TestPaymentPage() {
  const keyId = getRazorpayKeyId();
  const [phase, setPhase] = useState<CheckoutPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [checkoutResult, setCheckoutResult] = useState<RazorpayCheckoutSuccessResponse | null>(
    null,
  );
  const [backendVerified, setBackendVerified] = useState<boolean | null>(null);
  const [backendMessage, setBackendMessage] = useState<string | null>(null);

  async function handlePayClick() {
    if (!keyId) {
      setError("VITE_RAZORPAY_KEY_ID is not configured in the frontend environment.");
      setPhase("error");
      return;
    }

    setError(null);
    setCheckoutResult(null);
    setBackendVerified(null);
    setBackendMessage(null);
    setPhase("opening");

    try {
      await openTestPaymentCheckout(
        keyId,
        async (response) => {
          setCheckoutResult(response);
          setPhase("checkout_completed");

          setPhase("verifying");
          try {
            const verification = await verifyPaymentWithBackend(response);
            setBackendVerified(verification.verified);
            setBackendMessage(verification.message);
            setPhase(verification.verified ? "verified" : "checkout_completed");
          } catch (verifyError) {
            const message =
              verifyError instanceof Error
                ? verifyError.message
                : "Backend verification request failed";
            setBackendVerified(false);
            setBackendMessage(message);
            setPhase("checkout_completed");
          }
        },
        () => {
          setPhase((current) => (current === "opening" ? "idle" : current));
        },
      );
    } catch (checkoutError) {
      const message =
        checkoutError instanceof Error ? checkoutError.message : "Failed to open Razorpay Checkout";
      setError(message);
      setPhase("error");
    }
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)] px-4 py-10 text-[var(--color-ink)]">
      <div className="mx-auto max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-8 shadow-sm">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
          TEST MODE — Temporary Dev Utility
        </p>
        <h1 className="text-2xl font-semibold">ReconEngine Test Payment</h1>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          Opens Razorpay Checkout for an existing Test Mode order. This page is isolated from the
          production dashboard and landing experience.
        </p>

        <dl className="mt-6 space-y-3 rounded-xl bg-[var(--color-bg)] p-4 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--color-muted)]">Amount</dt>
            <dd className="font-medium">{TEST_PAYMENT_DISPLAY_AMOUNT}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--color-muted)]">Order ID</dt>
            <dd className="break-all font-mono text-xs">{TEST_PAYMENT_ORDER_ID}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--color-muted)]">Key ID configured</dt>
            <dd>{keyId ? "Yes (public key only)" : "No"}</dd>
          </div>
        </dl>

        <button
          type="button"
          onClick={() => void handlePayClick()}
          disabled={!keyId || phase === "opening" || phase === "verifying"}
          className="mt-6 w-full rounded-xl bg-[var(--color-accent-blue)] px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {phase === "opening" || phase === "verifying"
            ? "Opening Razorpay Checkout…"
            : `Pay ${TEST_PAYMENT_DISPLAY_AMOUNT} (Test Mode)`}
        </button>

        {!keyId ? (
          <p className="mt-3 text-sm text-[var(--color-danger)]">
            Set <code className="font-mono">VITE_RAZORPAY_KEY_ID</code> in{" "}
            <code className="font-mono">frontend/.env</code> (Key ID only — never the secret).
          </p>
        ) : null}

        {error ? (
          <p className="mt-4 rounded-lg border border-[var(--color-danger)]/30 bg-red-50 px-3 py-2 text-sm text-[var(--color-danger)]">
            {error}
          </p>
        ) : null}

        {checkoutResult ? (
          <section className="mt-6 space-y-3 rounded-xl border border-[var(--color-border)] p-4 text-sm">
            <h2 className="font-semibold text-[var(--color-success)]">Checkout completed</h2>
            <p className="text-[var(--color-muted)]">
              Razorpay Checkout returned successfully. This does not by itself prove settlement or
              reconciliation.
            </p>
            <dl className="space-y-2">
              <div>
                <dt className="text-[var(--color-muted)]">Payment ID</dt>
                <dd className="break-all font-mono text-xs">{checkoutResult.razorpay_payment_id}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-muted)]">Order ID</dt>
                <dd className="break-all font-mono text-xs">{checkoutResult.razorpay_order_id}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-muted)]">Signature</dt>
                <dd className="break-all font-mono text-xs">{checkoutResult.razorpay_signature}</dd>
              </div>
            </dl>
            <p className="font-medium">Test payment completed</p>
          </section>
        ) : null}

        {backendVerified !== null ? (
          <section
            className={`mt-4 rounded-xl border p-4 text-sm ${
              backendVerified
                ? "border-[var(--color-success)]/30 bg-green-50"
                : "border-[var(--color-warning)]/30 bg-amber-50"
            }`}
          >
            <h2 className="font-semibold">
              {backendVerified ? "Payment verified by backend" : "Backend verification pending/failed"}
            </h2>
            <p className="mt-1 text-[var(--color-muted)]">{backendMessage}</p>
          </section>
        ) : null}
      </div>
    </div>
  );
}

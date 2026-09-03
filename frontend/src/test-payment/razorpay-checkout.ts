import {
  RAZORPAY_CHECKOUT_SCRIPT_URL,
  TEST_PAYMENT_AMOUNT_PAISE,
  TEST_PAYMENT_CURRENCY,
  TEST_PAYMENT_ORDER_ID,
} from "./constants";

export interface RazorpayCheckoutSuccessResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayCheckoutOptions {
  key: string;
  amount: number;
  currency: string;
  order_id: string;
  name: string;
  description: string;
  theme?: { color?: string };
  handler: (response: RazorpayCheckoutSuccessResponse) => void;
  modal?: {
    ondismiss?: () => void;
  };
}

export interface RazorpayCheckoutInstance {
  open: () => void;
  on: (event: string, handler: (response: unknown) => void) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayCheckoutOptions) => RazorpayCheckoutInstance;
  }
}

let scriptPromise: Promise<void> | null = null;

export function loadRazorpayCheckoutScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Razorpay Checkout requires a browser environment"));
  }
  if (window.Razorpay) {
    return Promise.resolve();
  }
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>(
        `script[src="${RAZORPAY_CHECKOUT_SCRIPT_URL}"]`,
      );
      if (existing) {
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", () =>
          reject(new Error("Failed to load Razorpay Checkout script")),
        );
        return;
      }

      const script = document.createElement("script");
      script.src = RAZORPAY_CHECKOUT_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load Razorpay Checkout script"));
      document.body.appendChild(script);
    });
  }
  return scriptPromise;
}

export function getRazorpayKeyId(): string | undefined {
  const keyId = import.meta.env.VITE_RAZORPAY_KEY_ID?.trim();
  return keyId || undefined;
}

export async function openTestPaymentCheckout(
  keyId: string,
  onSuccess: (response: RazorpayCheckoutSuccessResponse) => void,
  onDismiss?: () => void,
): Promise<void> {
  await loadRazorpayCheckoutScript();
  if (!window.Razorpay) {
    throw new Error("Razorpay Checkout is unavailable");
  }

  const checkout = new window.Razorpay({
    key: keyId,
    amount: TEST_PAYMENT_AMOUNT_PAISE,
    currency: TEST_PAYMENT_CURRENCY,
    order_id: TEST_PAYMENT_ORDER_ID,
    name: "ReconEngine",
    description: "Test Mode payment for reconciliation dev utility",
    theme: { color: "#2563eb" },
    handler: onSuccess,
    modal: {
      ondismiss: onDismiss,
    },
  });

  checkout.open();
}

export interface BackendVerificationResult {
  verified: boolean;
  message: string;
}

export async function verifyPaymentWithBackend(
  response: RazorpayCheckoutSuccessResponse,
): Promise<BackendVerificationResult> {
  const baseUrl =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8001";
  const res = await fetch(`${baseUrl}/api/v1/sources/razorpay/verify-payment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      razorpay_order_id: response.razorpay_order_id,
      razorpay_payment_id: response.razorpay_payment_id,
      razorpay_signature: response.razorpay_signature,
    }),
  });

  if (!res.ok) {
    const payload = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail || `Verification request failed (${res.status})`);
  }

  return (await res.json()) as BackendVerificationResult;
}

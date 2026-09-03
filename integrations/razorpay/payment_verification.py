"""Server-side Razorpay Checkout payment signature verification."""

from __future__ import annotations

import hashlib
import hmac


def verify_payment_signature(
    *,
    order_id: str,
    payment_id: str,
    signature: str,
    key_secret: str,
) -> bool:
    """Verify Razorpay Checkout HMAC SHA256 signature (order_id|payment_id)."""
    if not order_id.strip() or not payment_id.strip() or not signature.strip():
        return False
    if not key_secret.strip():
        return False

    payload = f"{order_id}|{payment_id}"
    expected = hmac.new(
        key_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

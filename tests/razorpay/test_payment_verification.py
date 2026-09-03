"""Tests for Razorpay Checkout payment signature verification."""

from __future__ import annotations

import hashlib
import hmac

from integrations.razorpay.payment_verification import verify_payment_signature


def _sign(order_id: str, payment_id: str, secret: str) -> str:
    payload = f"{order_id}|{payment_id}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def test_verify_payment_signature_valid() -> None:
    secret = "test_secret_value"
    order_id = "order_TWLUxskAKIz7zq"
    payment_id = "pay_TestPayment001"
    signature = _sign(order_id, payment_id, secret)

    assert verify_payment_signature(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
        key_secret=secret,
    )


def test_verify_payment_signature_invalid() -> None:
    assert not verify_payment_signature(
        order_id="order_TWLUxskAKIz7zq",
        payment_id="pay_TestPayment001",
        signature="invalid_signature",
        key_secret="test_secret_value",
    )


def test_verify_payment_signature_rejects_empty_fields() -> None:
    assert not verify_payment_signature(
        order_id="",
        payment_id="pay_x",
        signature="sig",
        key_secret="secret",
    )

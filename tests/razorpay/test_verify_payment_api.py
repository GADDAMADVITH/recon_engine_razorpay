"""API tests for Razorpay Checkout payment verification endpoint."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

import api
from api import app
from integrations.razorpay.client import RazorpayConfig, RazorpayCredentialsError

client = TestClient(app)


def _sign(order_id: str, payment_id: str, secret: str) -> str:
    payload = f"{order_id}|{payment_id}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def test_verify_payment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "server_side_secret_only"
    monkeypatch.setattr(
        api.RazorpayConfig,
        "from_env",
        classmethod(
            lambda cls: RazorpayConfig(key_id="rzp_test_key", key_secret=secret)
        ),
    )

    order_id = "order_TWLUxskAKIz7zq"
    payment_id = "pay_Abc123"
    signature = _sign(order_id, payment_id, secret)

    response = client.post(
        "/api/v1/sources/razorpay/verify-payment",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert "verified by backend" in body["message"]
    assert secret not in response.text
    assert "rzp_test_key" not in response.text


def test_verify_payment_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.RazorpayConfig,
        "from_env",
        classmethod(
            lambda cls: RazorpayConfig(key_id="rzp_test_key", key_secret="secret123")
        ),
    )

    response = client.post(
        "/api/v1/sources/razorpay/verify-payment",
        json={
            "razorpay_order_id": "order_TWLUxskAKIz7zq",
            "razorpay_payment_id": "pay_Abc123",
            "razorpay_signature": "not_valid",
        },
    )
    assert response.status_code == 200
    assert response.json()["verified"] is False


def test_verify_payment_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_credentials() -> RazorpayConfig:
        raise RazorpayCredentialsError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set")

    monkeypatch.setattr(api.RazorpayConfig, "from_env", raise_credentials)
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.post(
        "/api/v1/sources/razorpay/verify-payment",
        json={
            "razorpay_order_id": "order_x",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "sig_x",
        },
    )
    assert response.status_code == 503
    assert "RAZORPAY_KEY_SECRET" not in response.text

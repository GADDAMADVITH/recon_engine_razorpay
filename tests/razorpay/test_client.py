"""Unit tests for the read-only Razorpay client (mocked HTTP only)."""

from __future__ import annotations

import httpx
import pytest

from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayClient,
    RazorpayConfig,
    RazorpayCredentialsError,
    RazorpayNetworkError,
)
from integrations.razorpay.models import PaginationParams, SettlementReconParams


def _make_client(handler: httpx.MockTransport) -> RazorpayClient:
    config = RazorpayConfig(key_id="rzp_test_key", key_secret="super_secret_value")
    http = httpx.Client(
        base_url=config.base_url,
        auth=(config.key_id, config.key_secret),
        transport=handler,
    )
    return RazorpayClient(config, http_client=http)


def test_config_from_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    monkeypatch.setenv("RAZORPAY_BASE_URL", "https://example.test/v1")

    config = RazorpayConfig.from_env()
    assert config.key_id == "rzp_test_abc"
    assert config.key_secret == "secret123"
    assert config.base_url == "https://example.test/v1"


def test_config_from_env_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(RazorpayCredentialsError):
        RazorpayConfig.from_env()


def test_fetch_orders_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        assert "super_secret_value" not in request.headers["Authorization"]
        assert request.url.path.endswith("/orders")
        assert request.url.params["count"] == "2"
        assert request.url.params["skip"] == "0"
        return httpx.Response(
            200,
            json={
                "entity": "collection",
                "count": 1,
                "items": [{"id": "order_123", "amount": 50000, "status": "paid"}],
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    result = client.fetch_orders(PaginationParams(count=2, skip=0))
    assert result.entity == "collection"
    assert result.count == 1
    assert result.items[0]["id"] == "order_123"
    client.close()


def test_fetch_payment_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/payments/pay_abc")
        return httpx.Response(200, json={"id": "pay_abc", "status": "captured", "amount": 1000})

    client = _make_client(httpx.MockTransport(handler))
    payment = client.fetch_payment("pay_abc")
    assert payment["id"] == "pay_abc"
    client.close()


def test_fetch_refunds_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/refunds")
        return httpx.Response(
            200,
            json={"entity": "collection", "count": 1, "items": [{"id": "rfnd_1"}]},
        )

    client = _make_client(httpx.MockTransport(handler))
    refunds = client.fetch_refunds()
    assert refunds.items[0]["id"] == "rfnd_1"
    client.close()


def test_fetch_settlements_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/settlements")
        return httpx.Response(
            200,
            json={"entity": "collection", "count": 1, "items": [{"id": "setl_1"}]},
        )

    client = _make_client(httpx.MockTransport(handler))
    settlements = client.fetch_settlements()
    assert settlements.items[0]["id"] == "setl_1"
    client.close()


def test_fetch_settlement_recon_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/settlements/recon/combined")
        assert request.url.params["year"] == "2024"
        assert request.url.params["month"] == "6"
        assert request.url.params["day"] == "11"
        return httpx.Response(
            200,
            json={
                "entity": "collection",
                "count": 1,
                "items": [{"settlement_id": "setl_99", "type": "payment"}],
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    recon = client.fetch_settlement_recon(
        SettlementReconParams(year=2024, month=6, day=11),
    )
    assert recon.items[0]["settlement_id"] == "setl_99"
    client.close()


def test_api_error_does_not_leak_secret() -> None:
    secret = "super_secret_value"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": f"Authentication failed for key_secret={secret}",
                }
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(RazorpayAPIError) as exc_info:
        client.fetch_orders()

    message = str(exc_info.value)
    assert secret not in message
    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "BAD_REQUEST_ERROR"
    client.close()


def test_network_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(RazorpayNetworkError, match="timed out"):
        client.fetch_payments()
    client.close()


def test_pagination_iter_orders() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params.get("skip", "0"))
        calls.append(f"skip={skip}")
        if skip == 0:
            items = [{"id": f"order_{i}"} for i in range(2)]
        else:
            items = [{"id": "order_2"}]
        return httpx.Response(
            200,
            json={"entity": "collection", "count": len(items), "items": items},
        )

    client = _make_client(httpx.MockTransport(handler))
    ids = [item["id"] for item in client.iter_orders(page_size=2, max_pages=2)]
    assert ids == ["order_0", "order_1", "order_2"]
    assert calls == ["skip=0", "skip=2"]
    client.close()


def test_request_uses_basic_auth_not_querystring() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(
            200,
            json={"entity": "collection", "count": 0, "items": []},
        )

    config = RazorpayConfig(key_id="rzp_test_key", key_secret="secret_for_auth")
    http = httpx.Client(
        base_url=config.base_url,
        auth=(config.key_id, config.key_secret),
        transport=httpx.MockTransport(handler),
    )
    client = RazorpayClient(config, http_client=http)
    client.fetch_orders()
    assert captured["auth"].startswith("Basic ")
    assert "secret_for_auth" not in captured["auth"]
    client.close()


def test_invalid_pagination_raises_before_request() -> None:
    client = _make_client(
        httpx.MockTransport(lambda _request: httpx.Response(500, json={"error": {}}))
    )
    with pytest.raises(ValueError, match="count must be between"):
        client.fetch_orders(PaginationParams(count=0))
    client.close()

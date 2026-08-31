"""Unit tests for Razorpay sync service (mocked client only)."""

from __future__ import annotations

from typing import Any, Iterator

import httpx
import pytest

from integrations.razorpay.adapter import BANK_TRANSACTIONS_NOT_SUPPORTED
from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayClient,
    RazorpayConfig,
    RazorpayNetworkError,
)
from integrations.razorpay.models import PaginatedList, SettlementReconParams
from integrations.razorpay.sync import RazorpaySyncResult, RazorpaySyncService
from tests.razorpay.test_adapter import (
    SAMPLE_ORDER,
    SAMPLE_PAYMENT,
    SAMPLE_RECON_PAYMENT,
    SAMPLE_REFUND,
)


class MockRazorpayClient:
    """Minimal stand-in for RazorpayClient used by RazorpaySyncService."""

    def __init__(
        self,
        *,
        orders: list[dict[str, Any]] | None = None,
        payments: list[dict[str, Any]] | None = None,
        refunds: list[dict[str, Any]] | None = None,
        recon_by_month: dict[tuple[int, int], list[dict[str, Any]]] | None = None,
        recon_error: Exception | None = None,
    ) -> None:
        self.orders = orders or []
        self.payments = payments or []
        self.refunds = refunds or []
        self.recon_by_month = recon_by_month or {}
        self.recon_error = recon_error

    def iter_orders(self, **_: Any) -> Iterator[dict[str, Any]]:
        yield from self.orders

    def iter_payments(self, **_: Any) -> Iterator[dict[str, Any]]:
        yield from self.payments

    def iter_refunds(self, **_: Any) -> Iterator[dict[str, Any]]:
        yield from self.refunds

    def fetch_settlement_recon(self, params: SettlementReconParams) -> PaginatedList[dict[str, Any]]:
        if self.recon_error is not None:
            raise self.recon_error
        items = self.recon_by_month.get((params.year, params.month), [])
        return PaginatedList(entity="collection", count=len(items), items=items)

    def close(self) -> None:
        return None


def _recon_month_for(order: dict[str, Any]) -> tuple[int, int]:
    from datetime import datetime, timezone

    ts = int(order["created_at"])
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.year, dt.month


def test_sync_empty_dataset() -> None:
    service = RazorpaySyncService(MockRazorpayClient())
    result = service.sync()

    assert isinstance(result, RazorpaySyncResult)
    assert result.source == "razorpay"
    assert result.status == "empty"
    assert result.orders_fetched == 0
    assert result.orders == []
    assert result.settlements == []
    assert result.refunds == []
    assert result.bank_data_available is False
    assert any("No Razorpay orders" in w for w in result.mapping_warnings)

    payload = result.to_api_dict(reconciliation=None)
    assert payload["status"] == "empty"
    assert payload["reconciliation"] is None
    assert payload["bank_transactions_fetched"] == 0


def test_sync_single_order_with_settlement_recon() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        payments=[SAMPLE_PAYMENT],
        recon_by_month={month: [SAMPLE_RECON_PAYMENT]},
    )
    result = RazorpaySyncService(client).sync()

    assert result.status == "success"
    assert result.orders_fetched == 1
    assert result.payments_fetched == 1
    assert len(result.orders) == 1
    assert result.orders[0].order_id == "order_Mabc123xyz"
    assert len(result.settlements) == 1
    assert result.settlements[0].order_id == "order_Mabc123xyz"
    assert result.bank_data_available is False


def test_sync_multiple_orders() -> None:
    order_b = {
        **SAMPLE_ORDER,
        "id": "order_Second0001",
        "amount": 63112,
        "created_at": SAMPLE_ORDER["created_at"] + 86400,
    }
    payment_b = {**SAMPLE_PAYMENT, "id": "pay_Second0001", "order_id": "order_Second0001", "amount": 63112}
    recon_b = {
        **SAMPLE_RECON_PAYMENT,
        "entity_id": "pay_Second0001",
        "payment_id": "pay_Second0001",
        "order_id": "order_Second0001",
        "settlement_id": "setl_Second0001",
        "amount": 63112,
        "credit": 60714,
    }
    month = _recon_month_for(SAMPLE_ORDER)
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER, order_b],
        payments=[SAMPLE_PAYMENT, payment_b],
        recon_by_month={
            month: [SAMPLE_RECON_PAYMENT, recon_b],
        },
    )
    result = RazorpaySyncService(client).sync()

    assert result.orders_fetched == 2
    assert len(result.orders) == 2
    assert len(result.settlements) == 2


def test_sync_refund_mapping_with_payment_lookup() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        payments=[SAMPLE_PAYMENT],
        refunds=[SAMPLE_REFUND],
        recon_by_month={month: [SAMPLE_RECON_PAYMENT]},
    )
    result = RazorpaySyncService(client).sync()

    assert len(result.refunds) == 1
    assert result.refunds[0].refund_id == "rfnd_Jkl012mno"
    assert result.refunds[0].order_id == "order_Mabc123xyz"


def test_sync_refund_skipped_without_order_link() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    orphan_refund = {**SAMPLE_REFUND, "id": "rfnd_orphan", "payment_id": "pay_unknown"}
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        payments=[SAMPLE_PAYMENT],
        refunds=[orphan_refund],
        recon_by_month={month: [SAMPLE_RECON_PAYMENT]},
    )
    result = RazorpaySyncService(client).sync()

    assert result.refunds_fetched == 1
    assert result.refunds == []
    assert any("refund" in err for err in result.mapping_errors)


def test_sync_malformed_order_skipped() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    client = MockRazorpayClient(
        orders=[{"entity": "order"}, SAMPLE_ORDER],
        recon_by_month={month: [SAMPLE_RECON_PAYMENT]},
    )
    result = RazorpaySyncService(client).sync()

    assert result.orders_fetched == 2
    assert len(result.orders) == 1
    assert any("order:" in err for err in result.mapping_errors)


def test_sync_all_orders_unmappable_returns_empty_status() -> None:
    client = MockRazorpayClient(orders=[{"entity": "order"}, {"id": "order_x", "amount": 0}])
    result = RazorpaySyncService(client).sync()

    assert result.status == "empty"
    assert result.orders == []


def test_sync_does_not_fabricate_bank_transactions() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    recon_with_utr = {**SAMPLE_RECON_PAYMENT, "settlement_utr": "UTR123456789012"}
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        recon_by_month={month: [recon_with_utr]},
    )
    result = RazorpaySyncService(client).sync()

    assert result.bank_data_available is False
    payload = result.to_api_dict()
    assert payload["bank_transactions_fetched"] == 0
    assert payload["bank_data_available"] is False
    assert any(BANK_TRANSACTIONS_NOT_SUPPORTED in w for w in result.mapping_warnings)


def test_sync_api_dict_never_includes_credentials() -> None:
    secret = "super_secret_sync_value"
    config = RazorpayConfig(key_id="rzp_test_key", key_secret=secret)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"entity": "collection", "count": 0, "items": []},
        )

    http = httpx.Client(
        base_url=config.base_url,
        auth=(config.key_id, config.key_secret),
        transport=httpx.MockTransport(handler),
    )
    client = RazorpayClient(config, http_client=http)
    try:
        result = RazorpaySyncService(client).sync()
        payload = result.to_api_dict()
        serialized = str(payload)
        assert secret not in serialized
        assert config.key_id not in serialized
        assert "Authorization" not in serialized
    finally:
        client.close()


def test_sync_recon_api_failure_propagates() -> None:
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        recon_error=RazorpayAPIError("upstream failure", status_code=502),
    )
    with pytest.raises(RazorpayAPIError, match="upstream failure"):
        RazorpaySyncService(client).sync()


def test_sync_recon_network_failure_propagates() -> None:
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        recon_error=RazorpayNetworkError("timed out"),
    )
    with pytest.raises(RazorpayNetworkError, match="timed out"):
        RazorpaySyncService(client).sync()


def test_sync_partial_settlement_recon_recorded() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    partial_recon = {k: v for k, v in SAMPLE_RECON_PAYMENT.items() if k != "order_id"}
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        recon_by_month={month: [partial_recon]},
    )
    result = RazorpaySyncService(client).sync()

    assert result.settlements == []
    assert any("partial" in err for err in result.mapping_errors)


def test_sync_deduplicates_settlements() -> None:
    month = _recon_month_for(SAMPLE_ORDER)
    duplicate_recon = [SAMPLE_RECON_PAYMENT, dict(SAMPLE_RECON_PAYMENT)]
    client = MockRazorpayClient(
        orders=[SAMPLE_ORDER],
        recon_by_month={month: duplicate_recon},
    )
    result = RazorpaySyncService(client).sync()

    assert len(result.settlements) == 1

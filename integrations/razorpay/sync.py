"""Fetch Razorpay data and map it to ReconEngine normalized records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from integrations.razorpay.adapter import (
    BANK_TRANSACTIONS_NOT_SUPPORTED,
    MappingResult,
    PartialMappingResult,
    RazorpayAdapter,
    RazorpayMappingError,
)
from integrations.razorpay.client import RazorpayClient
from integrations.razorpay.models import ReconPaginationParams, SettlementReconParams
from recon_engine import (
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
)

RazorpaySyncStatus = Literal["empty", "success", "partial"]


@dataclass
class RazorpaySyncResult:
    """Result of a Razorpay fetch-and-map cycle."""

    source: Literal["razorpay"] = "razorpay"
    status: RazorpaySyncStatus = "empty"
    orders_fetched: int = 0
    payments_fetched: int = 0
    refunds_fetched: int = 0
    settlements_fetched: int = 0
    recon_items_fetched: int = 0
    orders: list[NormalizedOrder] = field(default_factory=list)
    settlements: list[NormalizedSettlement] = field(default_factory=list)
    refunds: list[NormalizedRefund] = field(default_factory=list)
    bank_data_available: bool = False
    mapping_warnings: list[str] = field(default_factory=list)
    mapping_errors: list[str] = field(default_factory=list)

    @property
    def has_orders(self) -> bool:
        return len(self.orders) > 0

    def to_api_dict(self, *, reconciliation: dict[str, Any] | None = None) -> dict[str, Any]:
        """Serialize for the HTTP API without exposing credentials."""
        return {
            "source": self.source,
            "status": self.status,
            "orders_fetched": self.orders_fetched,
            "payments_fetched": self.payments_fetched,
            "refunds_fetched": self.refunds_fetched,
            "settlements_fetched": self.settlements_fetched,
            "recon_items_fetched": self.recon_items_fetched,
            "bank_data_available": self.bank_data_available,
            "bank_transactions_fetched": 0,
            "orders": [_serialize_order(order) for order in self.orders],
            "settlements": [_serialize_settlement(s) for s in self.settlements],
            "refunds": [_serialize_refund(r) for r in self.refunds],
            "mapping_warnings": list(self.mapping_warnings),
            "mapping_errors": list(self.mapping_errors),
            "reconciliation": reconciliation,
        }


class RazorpaySyncService:
    """FETCH → VALIDATE → MAP → RETURN for Razorpay data."""

    def __init__(
        self,
        client: RazorpayClient,
        adapter: RazorpayAdapter | None = None,
    ) -> None:
        self._client = client
        self._adapter = adapter or RazorpayAdapter()

    def sync(self, *, max_pages: int | None = None) -> RazorpaySyncResult:
        result = RazorpaySyncResult()

        raw_orders = list(self._client.iter_orders(max_pages=max_pages))
        raw_payments = list(self._client.iter_payments(max_pages=max_pages))
        raw_refunds = list(self._client.iter_refunds(max_pages=max_pages))

        result.orders_fetched = len(raw_orders)
        result.payments_fetched = len(raw_payments)
        result.refunds_fetched = len(raw_refunds)

        if not raw_orders:
            result.status = "empty"
            result.mapping_warnings.append(
                "No Razorpay orders returned; reconciliation was not run."
            )
            result.mapping_warnings.append(BANK_TRANSACTIONS_NOT_SUPPORTED)
            return result

        payments_by_id = {
            payment["id"]: payment
            for payment in raw_payments
            if isinstance(payment.get("id"), str)
        }

        order_ids: set[str] = set()
        for raw_order in raw_orders:
            try:
                mapped = self._adapter.map_order(raw_order)
            except RazorpayMappingError as exc:
                result.mapping_errors.append(f"order: {exc}")
                continue
            result.orders.append(mapped.record)
            order_ids.add(mapped.record.order_id)
            result.mapping_warnings.extend(mapped.warnings)

        if not result.orders:
            result.status = "empty"
            result.mapping_warnings.append(
                "Razorpay orders were fetched but none could be mapped."
            )
            return result

        for raw_refund in raw_refunds:
            payment_id = raw_refund.get("payment_id")
            payment = payments_by_id.get(payment_id) if isinstance(payment_id, str) else None
            try:
                mapped = self._adapter.map_refund(raw_refund, payment=payment)
            except RazorpayMappingError as exc:
                result.mapping_errors.append(f"refund: {exc}")
                continue
            if mapped.record.order_id not in order_ids:
                result.mapping_errors.append(
                    f"refund {mapped.record.refund_id}: order_id "
                    f"{mapped.record.order_id!r} not in fetched orders"
                )
                continue
            result.refunds.append(mapped.record)
            result.mapping_warnings.extend(mapped.warnings)

        recon_items = self._fetch_settlement_recon_items(raw_orders, max_pages=max_pages)
        result.recon_items_fetched = len(recon_items)

        seen_settlements: set[tuple[str, str]] = set()
        for item in recon_items:
            mapped = self._adapter.map_settlement_recon_item(item)
            if isinstance(mapped, PartialMappingResult):
                result.mapping_warnings.extend(mapped.warnings)
                result.mapping_errors.append(
                    f"settlement_recon partial: missing {', '.join(mapped.missing_recon_fields)}"
                )
                continue
            if not isinstance(mapped, MappingResult):
                continue
            settlement = mapped.record
            if not isinstance(settlement, NormalizedSettlement):
                result.mapping_warnings.extend(mapped.warnings)
                continue
            if settlement.order_id not in order_ids:
                result.mapping_errors.append(
                    f"settlement {settlement.settlement_id}: order_id "
                    f"{settlement.order_id!r} not in fetched orders"
                )
                continue
            key = (settlement.settlement_id, settlement.order_id)
            if key in seen_settlements:
                continue
            seen_settlements.add(key)
            result.settlements.append(settlement)
            result.mapping_warnings.extend(mapped.warnings)

        result.settlements_fetched = len(result.settlements)
        result.bank_data_available = False
        result.mapping_warnings.append(BANK_TRANSACTIONS_NOT_SUPPORTED)
        result.status = "success" if not result.mapping_errors else "partial"
        return result

    def _fetch_settlement_recon_items(
        self,
        raw_orders: list[dict[str, Any]],
        *,
        max_pages: int | None,
    ) -> list[dict[str, Any]]:
        months = _months_from_orders(raw_orders)
        items: list[dict[str, Any]] = []
        for year, month in sorted(months):
            skip = 0
            pages = 0
            while True:
                params = SettlementReconParams(
                    year=year,
                    month=month,
                    pagination=ReconPaginationParams(count=100, skip=skip),
                )
                page = self._client.fetch_settlement_recon(params)
                items.extend(page.items)
                if len(page.items) < 100:
                    break
                skip += 100
                pages += 1
                if max_pages is not None and pages >= max_pages:
                    break
        return items


def _months_from_orders(raw_orders: list[dict[str, Any]]) -> set[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    for order in raw_orders:
        created_at = order.get("created_at")
        if created_at is None:
            continue
        try:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
        except (TypeError, ValueError):
            continue
        months.add((dt.year, dt.month))
    if not months:
        now = datetime.now(tz=timezone.utc)
        months.add((now.year, now.month))
    return months


def _serialize_order(order: NormalizedOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "amount_paise": order.amount_paise,
        "created_at": order.created_at.isoformat(),
    }


def _serialize_settlement(settlement: NormalizedSettlement) -> dict[str, Any]:
    return {
        "settlement_id": settlement.settlement_id,
        "order_id": settlement.order_id,
        "gross_amount_paise": settlement.gross_amount_paise,
        "fee_paise": settlement.fee_paise,
        "tax_paise": settlement.tax_paise,
        "net_amount_paise": settlement.net_amount_paise,
        "settled_at": settlement.settled_at.isoformat(),
    }


def _serialize_refund(refund: NormalizedRefund) -> dict[str, Any]:
    return {
        "refund_id": refund.refund_id,
        "order_id": refund.order_id,
        "refund_amount_paise": refund.refund_amount_paise,
        "created_at": refund.created_at.isoformat(),
    }

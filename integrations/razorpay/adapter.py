"""Map Razorpay API payloads to ReconEngine normalized records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from recon_engine import (
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
    normalize_id,
)

T = TypeVar("T")

BANK_TRANSACTIONS_NOT_SUPPORTED = (
    "Razorpay data cannot be mapped to NormalizedBankTransaction; "
    "bank-side records require separate bank CSV or bank API input."
)


class RazorpayMappingError(ValueError):
    """Raised when required Razorpay fields are missing or invalid."""

    def __init__(
        self,
        message: str,
        *,
        resource_type: str,
        missing_fields: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.resource_type = resource_type
        self.missing_fields = list(missing_fields or [])


@dataclass(frozen=True)
class MappingResult(Generic[T]):
    """Successful mapping with explicit metadata about unmapped Razorpay fields."""

    record: T
    source_resource: str
    unmapped_razorpay_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PartialMappingResult:
    """Explicit record when a full ReconEngine entity cannot be produced."""

    source_resource: str
    available_fields: dict[str, Any]
    missing_recon_fields: tuple[str, ...]
    unmapped_razorpay_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MappedPaymentContext:
    """Payment context for reconciliation; ReconEngine has no NormalizedPayment type."""

    payment_id: str
    order_id: str
    amount_paise: int
    created_at: datetime
    status: str | None = None
    currency: str | None = None
    fee_paise: int | None = None
    tax_paise: int | None = None
    settlement_id: str | None = None
    unmapped_razorpay_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MappedSettlementReconContext:
    """Settlement recon line item that does not map to NormalizedSettlement."""

    entity_id: str
    recon_type: str
    settlement_id: str | None
    order_id: str | None
    payment_id: str | None
    amount_paise: int | None
    fee_paise: int | None
    tax_paise: int | None
    settlement_utr: str | None
    settled_at: datetime | None
    unmapped_razorpay_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def unix_to_datetime(value: Any, field_name: str, *, resource_type: str = "timestamp") -> datetime:
    """Convert Razorpay Unix epoch seconds to naive UTC datetime (ISO-compatible)."""
    if value is None:
        raise RazorpayMappingError(
            f"Missing timestamp field {field_name!r}",
            resource_type=resource_type,
            missing_fields=[field_name],
        )
    try:
        ts = int(value)
    except (TypeError, ValueError) as exc:
        raise RazorpayMappingError(
            f"Invalid Unix timestamp for {field_name}: {value!r}",
            resource_type=resource_type,
            missing_fields=[field_name],
        ) from exc
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def _require_str(payload: dict[str, Any], key: str, resource_type: str) -> str:
    raw = payload.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise RazorpayMappingError(
            f"Missing required field {key!r}",
            resource_type=resource_type,
            missing_fields=[key],
        )
    return normalize_id(str(raw))


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    raw = payload.get(key)
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text else None


def _require_positive_int(payload: dict[str, Any], key: str, resource_type: str) -> int:
    raw = payload.get(key)
    if raw is None:
        raise RazorpayMappingError(
            f"Missing required amount field {key!r}",
            resource_type=resource_type,
            missing_fields=[key],
        )
    try:
        amount = int(raw)
    except (TypeError, ValueError) as exc:
        raise RazorpayMappingError(
            f"Invalid amount for {key!r}: {raw!r}",
            resource_type=resource_type,
            missing_fields=[key],
        ) from exc
    if amount <= 0:
        raise RazorpayMappingError(
            f"Amount must be positive for {key!r}: {amount}",
            resource_type=resource_type,
            missing_fields=[key],
        )
    return amount


def _non_negative_int(payload: dict[str, Any], key: str, default: int = 0) -> int:
    raw = payload.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(0, value)


def _known_unmapped(payload: dict[str, Any], consumed: set[str]) -> tuple[str, ...]:
    return tuple(sorted(key for key in payload if key not in consumed))


class RazorpayAdapter:
    """Convert Razorpay API dict payloads into ReconEngine normalized types."""

    bank_transactions_not_supported: str = BANK_TRANSACTIONS_NOT_SUPPORTED

    def map_order(self, order: dict[str, Any]) -> MappingResult[NormalizedOrder]:
        resource = "order"
        if not isinstance(order, dict):
            raise RazorpayMappingError(
                "Expected order payload to be a dict",
                resource_type=resource,
            )

        order_id = _require_str(order, "id", resource)
        amount_paise = _require_positive_int(order, "amount", resource)
        created_at = unix_to_datetime(order.get("created_at"), "created_at", resource_type=resource)

        warnings: list[str] = []
        currency = _optional_str(order, "currency")
        if currency and currency.upper() != "INR":
            warnings.append(
                f"Non-INR currency {currency!r}; amount treated as smallest currency unit"
            )

        consumed = {"id", "amount", "created_at"}
        record = NormalizedOrder(
            order_id=order_id,
            amount_paise=amount_paise,
            created_at=created_at,
        )
        return MappingResult(
            record=record,
            source_resource=resource,
            unmapped_razorpay_fields=_known_unmapped(order, consumed),
            warnings=tuple(warnings),
        )

    def map_payment(self, payment: dict[str, Any]) -> MappingResult[MappedPaymentContext]:
        resource = "payment"
        if not isinstance(payment, dict):
            raise RazorpayMappingError(
                "Expected payment payload to be a dict",
                resource_type=resource,
            )

        payment_id = _require_str(payment, "id", resource)
        order_id = _require_str(payment, "order_id", resource)
        amount_paise = _require_positive_int(payment, "amount", resource)
        created_at = unix_to_datetime(
            payment.get("created_at"), "created_at", resource_type=resource
        )

        fee_raw = payment.get("fee")
        tax_raw = payment.get("tax")
        fee_paise = int(fee_raw) if fee_raw is not None else None
        tax_paise = int(tax_raw) if tax_raw is not None else None

        consumed = {
            "id",
            "order_id",
            "amount",
            "created_at",
        }
        context = MappedPaymentContext(
            payment_id=payment_id,
            order_id=order_id,
            amount_paise=amount_paise,
            created_at=created_at,
            status=_optional_str(payment, "status"),
            currency=_optional_str(payment, "currency"),
            fee_paise=fee_paise,
            tax_paise=tax_paise,
            settlement_id=_optional_str(payment, "settlement_id"),
            unmapped_razorpay_fields=_known_unmapped(payment, consumed),
        )
        return MappingResult(
            record=context,
            source_resource=resource,
            unmapped_razorpay_fields=context.unmapped_razorpay_fields,
            warnings=(
                "ReconEngine has no NormalizedPayment entity; "
                "MappedPaymentContext is for linkage and settlement derivation.",
            ),
        )

    def map_refund(
        self,
        refund: dict[str, Any],
        *,
        order_id: str | None = None,
        payment: dict[str, Any] | None = None,
    ) -> MappingResult[NormalizedRefund]:
        resource = "refund"
        if not isinstance(refund, dict):
            raise RazorpayMappingError(
                "Expected refund payload to be a dict",
                resource_type=resource,
            )

        refund_id = _require_str(refund, "id", resource)
        refund_amount_paise = _require_positive_int(refund, "amount", resource)
        created_at = unix_to_datetime(
            refund.get("created_at"), "created_at", resource_type=resource
        )

        resolved_order_id = (
            order_id
            or _optional_str(refund, "order_id")
            or (payment and _optional_str(payment, "order_id"))
        )
        if not resolved_order_id:
            raise RazorpayMappingError(
                "Cannot map refund without order_id; "
                "provide order_id or payment payload containing order_id",
                resource_type=resource,
                missing_fields=["order_id"],
            )

        warnings: list[str] = []
        if order_id is None and refund.get("order_id") is None:
            warnings.append("order_id resolved from payment lookup parameter")

        consumed = {
            "id",
            "amount",
            "created_at",
            "order_id",
        }
        record = NormalizedRefund(
            refund_id=refund_id,
            order_id=normalize_id(resolved_order_id),
            refund_amount_paise=refund_amount_paise,
            created_at=created_at,
        )
        return MappingResult(
            record=record,
            source_resource=resource,
            unmapped_razorpay_fields=_known_unmapped(refund, consumed),
            warnings=tuple(warnings),
        )

    def map_settlement(
        self,
        settlement: dict[str, Any],
        *,
        order_id: str | None = None,
    ) -> MappingResult[NormalizedSettlement] | PartialMappingResult:
        """Map a Razorpay settlement entity (batch bank payout).

        Razorpay settlement list/detail objects aggregate many orders and usually
        omit ``order_id``. When ``order_id`` is absent this returns PartialMappingResult
        instead of fabricating per-order fields. Prefer ``map_settlement_recon_item``
        for per-order settlement rows.
        """
        resource = "settlement"
        if not isinstance(settlement, dict):
            raise RazorpayMappingError(
                "Expected settlement payload to be a dict",
                resource_type=resource,
            )

        settlement_id = _require_str(settlement, "id", resource)
        resolved_order_id = order_id or _optional_str(settlement, "order_id")

        consumed = {
            "id",
            "amount",
            "fees",
            "tax",
            "settled_at",
            "created_at",
            "order_id",
        }

        if not resolved_order_id:
            amount_raw = settlement.get("amount")
            fees_raw = settlement.get("fees")
            tax_raw = settlement.get("tax")
            settled_raw = settlement.get("settled_at") or settlement.get("created_at")
            settled_at: datetime | None = None
            if settled_raw is not None:
                settled_at = unix_to_datetime(
                    settled_raw, "settled_at", resource_type=resource
                )

            return PartialMappingResult(
                source_resource=resource,
                available_fields={
                    "settlement_id": settlement_id,
                    "amount_paise": int(amount_raw) if amount_raw is not None else None,
                    "fee_paise": int(fees_raw) if fees_raw is not None else None,
                    "tax_paise": int(tax_raw) if tax_raw is not None else None,
                    "settled_at": settled_at,
                },
                missing_recon_fields=("order_id", "gross_amount_paise", "net_amount_paise"),
                unmapped_razorpay_fields=_known_unmapped(settlement, consumed),
                warnings=(
                    "Razorpay settlement API objects are batch payouts without per-order "
                    "linkage; use settlement recon (type=payment) or supply order_id explicitly.",
                    "settlement.amount is batch-level and must not be treated as order gross.",
                ),
            )

        gross_amount_paise = _require_positive_int(settlement, "amount", resource)
        fee_paise = _non_negative_int(settlement, "fees")
        tax_paise = _non_negative_int(settlement, "tax")
        net_amount_paise = gross_amount_paise - fee_paise - tax_paise
        if net_amount_paise <= 0:
            raise RazorpayMappingError(
                f"Computed net_amount_paise must be positive: {net_amount_paise}",
                resource_type=resource,
                missing_fields=["net_amount"],
            )

        settled_raw = settlement.get("settled_at") or settlement.get("created_at")
        settled_at = unix_to_datetime(settled_raw, "settled_at", resource_type=resource)

        warnings: list[str] = [
            "Settlement entity amount may represent batch totals; "
            "verify against settlement recon when order_id was supplied externally.",
        ]
        if fee_paise == 0 or tax_paise == 0:
            warnings.append("fee_paise or tax_paise is zero; ReconEngine CSV samples use positive fee/tax")

        record = NormalizedSettlement(
            settlement_id=settlement_id,
            order_id=normalize_id(resolved_order_id),
            gross_amount_paise=gross_amount_paise,
            fee_paise=fee_paise,
            tax_paise=tax_paise,
            net_amount_paise=net_amount_paise,
            settled_at=settled_at,
        )
        return MappingResult(
            record=record,
            source_resource=resource,
            unmapped_razorpay_fields=_known_unmapped(settlement, consumed),
            warnings=tuple(warnings),
        )

    def map_settlement_recon_item(
        self,
        item: dict[str, Any],
    ) -> (
        MappingResult[NormalizedSettlement]
        | PartialMappingResult
        | MappingResult[MappedSettlementReconContext]
    ):
        """Map a settlement recon combined line item.

        ``type=payment`` rows with ``order_id`` map to NormalizedSettlement.
        Other types return MappedSettlementReconContext with explicit limitations.
        ``settlement_utr`` is retained in context only — not mapped to bank.csv fields.
        """
        resource = "settlement_recon"
        if not isinstance(item, dict):
            raise RazorpayMappingError(
                "Expected settlement recon item to be a dict",
                resource_type=resource,
            )

        recon_type = (_optional_str(item, "type") or "").lower()
        if recon_type == "payment":
            return self._map_recon_payment_item(item)

        entity_id = _optional_str(item, "entity_id") or _optional_str(item, "payment_id") or ""
        if not entity_id:
            raise RazorpayMappingError(
                "Settlement recon item missing entity_id",
                resource_type=resource,
                missing_fields=["entity_id"],
            )

        settled_raw = item.get("settled_at") or item.get("created_at")
        settled_at: datetime | None = None
        if settled_raw is not None:
            settled_at = unix_to_datetime(settled_raw, "settled_at", resource_type=resource)

        amount_raw = item.get("amount")
        amount_paise = int(amount_raw) if amount_raw is not None else None

        consumed = {
            "type",
            "amount",
            "fee",
            "tax",
            "credit",
            "settlement_id",
            "order_id",
            "settled_at",
            "created_at",
            "entity_id",
            "payment_id",
        }
        context = MappedSettlementReconContext(
            entity_id=entity_id,
            recon_type=recon_type or "unknown",
            settlement_id=_optional_str(item, "settlement_id"),
            order_id=_optional_str(item, "order_id"),
            payment_id=_optional_str(item, "payment_id"),
            amount_paise=amount_paise,
            fee_paise=_non_negative_int(item, "fee") if item.get("fee") is not None else None,
            tax_paise=_non_negative_int(item, "tax") if item.get("tax") is not None else None,
            settlement_utr=_optional_str(item, "settlement_utr"),
            settled_at=settled_at,
            unmapped_razorpay_fields=_known_unmapped(item, consumed),
            warnings=(
                f"Settlement recon type {recon_type!r} does not map to NormalizedSettlement.",
                "settlement_utr is not mapped to NormalizedBankTransaction.",
            ),
        )
        return MappingResult(
            record=context,
            source_resource=resource,
            unmapped_razorpay_fields=context.unmapped_razorpay_fields,
            warnings=context.warnings,
        )

    def _map_recon_payment_item(
        self, item: dict[str, Any]
    ) -> MappingResult[NormalizedSettlement] | PartialMappingResult:
        resource = "settlement_recon"
        settlement_id = _optional_str(item, "settlement_id")
        order_id = _optional_str(item, "order_id")

        consumed = {
            "type",
            "amount",
            "fee",
            "tax",
            "credit",
            "settlement_id",
            "order_id",
            "settled_at",
            "created_at",
            "entity_id",
            "payment_id",
        }

        missing: list[str] = []
        if not settlement_id:
            missing.append("settlement_id")
        if not order_id:
            missing.append("order_id")

        if missing:
            return PartialMappingResult(
                source_resource=resource,
                available_fields={
                    "settlement_id": settlement_id,
                    "order_id": order_id,
                    "amount_paise": item.get("amount"),
                    "fee_paise": item.get("fee"),
                    "tax_paise": item.get("tax"),
                },
                missing_recon_fields=tuple(missing),
                unmapped_razorpay_fields=_known_unmapped(item, consumed),
                warnings=("Payment recon item missing fields required for NormalizedSettlement.",),
            )

        gross_amount_paise = _require_positive_int(item, "amount", resource)
        fee_paise = _non_negative_int(item, "fee")
        tax_paise = _non_negative_int(item, "tax")

        credit_raw = item.get("credit")
        if credit_raw is not None:
            net_amount_paise = int(credit_raw)
        else:
            net_amount_paise = gross_amount_paise - fee_paise - tax_paise

        if net_amount_paise <= 0:
            raise RazorpayMappingError(
                f"Computed net_amount_paise must be positive: {net_amount_paise}",
                resource_type=resource,
                missing_fields=["net_amount"],
            )

        settled_raw = item.get("settled_at") or item.get("created_at")
        settled_at = unix_to_datetime(settled_raw, "settled_at", resource_type=resource)

        warnings: list[str] = []
        if item.get("settlement_utr"):
            warnings.append(
                "settlement_utr present but not mapped to bank transactions "
                f"({self.bank_transactions_not_supported})"
            )

        record = NormalizedSettlement(
            settlement_id=normalize_id(settlement_id),
            order_id=normalize_id(order_id),
            gross_amount_paise=gross_amount_paise,
            fee_paise=fee_paise,
            tax_paise=tax_paise,
            net_amount_paise=net_amount_paise,
            settled_at=settled_at,
        )
        return MappingResult(
            record=record,
            source_resource=resource,
            unmapped_razorpay_fields=_known_unmapped(item, consumed),
            warnings=tuple(warnings),
        )

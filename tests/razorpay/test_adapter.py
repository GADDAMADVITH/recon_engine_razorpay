"""Unit tests for Razorpay → ReconEngine adapter (fixture payloads only)."""

from __future__ import annotations

from datetime import datetime

import pytest

from integrations.razorpay.adapter import (
    BANK_TRANSACTIONS_NOT_SUPPORTED,
    MappedPaymentContext,
    MappedSettlementReconContext,
    MappingResult,
    PartialMappingResult,
    RazorpayAdapter,
    RazorpayMappingError,
    unix_to_datetime,
)
from recon_engine import NormalizedOrder, NormalizedRefund, NormalizedSettlement


@pytest.fixture
def adapter() -> RazorpayAdapter:
    return RazorpayAdapter()


# ------------------------------------------------------------------
# Fixtures — representative Razorpay API shapes (no live API)
# ------------------------------------------------------------------

SAMPLE_ORDER = {
    "id": "order_Mabc123xyz",
    "entity": "order",
    "amount": 385243,
    "amount_paid": 385243,
    "amount_due": 0,
    "currency": "INR",
    "receipt": "rcpt_001",
    "status": "paid",
    "attempts": 1,
    "notes": {},
    "created_at": 1722938160,
}

SAMPLE_PAYMENT = {
    "id": "pay_Def456uvw",
    "entity": "payment",
    "amount": 385243,
    "currency": "INR",
    "status": "captured",
    "order_id": "order_Mabc123xyz",
    "method": "card",
    "fee": 7704,
    "tax": 6934,
    "created_at": 1722938200,
    "settlement_id": "setl_Ghi789rst",
}

SAMPLE_REFUND = {
    "id": "rfnd_Jkl012mno",
    "entity": "refund",
    "amount": 40478,
    "currency": "INR",
    "payment_id": "pay_Def456uvw",
    "status": "processed",
    "created_at": 1724870460,
    "notes": {"reason": "customer_request"},
}

SAMPLE_SETTLEMENT_BATCH = {
    "id": "setl_Ghi789rst",
    "entity": "settlement",
    "amount": 5000000,
    "fees": 120000,
    "tax": 18000,
    "status": "processed",
    "created_at": 1723023360,
    "settled_at": 1723109760,
}

SAMPLE_RECON_PAYMENT = {
    "entity_id": "pay_Def456uvw",
    "type": "payment",
    "amount": 385243,
    "debit": 0,
    "credit": 370605,
    "fee": 7704,
    "tax": 6934,
    "currency": "INR",
    "settlement_id": "setl_Ghi789rst",
    "order_id": "order_Mabc123xyz",
    "payment_id": "pay_Def456uvw",
    "settled_at": 1723023360,
    "settlement_utr": "UTR123456789012",
    "method": "card",
}

SAMPLE_RECON_REFUND = {
    "entity_id": "rfnd_Jkl012mno",
    "type": "refund",
    "amount": 40478,
    "debit": 40478,
    "credit": 0,
    "fee": 0,
    "tax": 0,
    "settlement_id": "setl_Ghi789rst",
    "order_id": "order_Mabc123xyz",
    "payment_id": "pay_Def456uvw",
    "settled_at": 1724870460,
    "settlement_utr": "UTR987654321098",
}


# ------------------------------------------------------------------
# Order mapping
# ------------------------------------------------------------------


def test_map_order_success(adapter: RazorpayAdapter) -> None:
    result = adapter.map_order(SAMPLE_ORDER)
    assert isinstance(result.record, NormalizedOrder)
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.record.amount_paise == 385243
    assert result.record.created_at == unix_to_datetime(SAMPLE_ORDER["created_at"], "created_at")
    assert "status" in result.unmapped_razorpay_fields
    assert "currency" in result.unmapped_razorpay_fields
    assert result.warnings == ()


def test_map_order_preserves_identifier_exactly(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_ORDER, "id": "  order_trim_test  "}
    result = adapter.map_order(payload)
    assert result.record.order_id == "order_trim_test"


def test_map_order_non_inr_warning(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_ORDER, "currency": "USD"}
    result = adapter.map_order(payload)
    assert any("Non-INR" in w for w in result.warnings)


def test_map_order_missing_id(adapter: RazorpayAdapter) -> None:
    payload = {k: v for k, v in SAMPLE_ORDER.items() if k != "id"}
    with pytest.raises(RazorpayMappingError, match="Missing required field 'id'"):
        adapter.map_order(payload)


def test_map_order_invalid_amount(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_ORDER, "amount": "not-a-number"}
    with pytest.raises(RazorpayMappingError, match="Invalid amount"):
        adapter.map_order(payload)


def test_map_order_zero_amount(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_ORDER, "amount": 0}
    with pytest.raises(RazorpayMappingError, match="must be positive"):
        adapter.map_order(payload)


def test_map_order_malformed_payload(adapter: RazorpayAdapter) -> None:
    with pytest.raises(RazorpayMappingError, match="Expected order payload"):
        adapter.map_order([])  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Payment mapping
# ------------------------------------------------------------------


def test_map_payment_success(adapter: RazorpayAdapter) -> None:
    result = adapter.map_payment(SAMPLE_PAYMENT)
    assert isinstance(result.record, MappedPaymentContext)
    assert result.record.payment_id == "pay_Def456uvw"
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.record.amount_paise == 385243
    assert result.record.fee_paise == 7704
    assert result.record.tax_paise == 6934
    assert result.record.settlement_id == "setl_Ghi789rst"
    assert result.record.created_at == unix_to_datetime(SAMPLE_PAYMENT["created_at"], "created_at")
    assert any("NormalizedPayment" in w for w in result.warnings)


def test_map_payment_missing_order_id(adapter: RazorpayAdapter) -> None:
    payload = {k: v for k, v in SAMPLE_PAYMENT.items() if k != "order_id"}
    with pytest.raises(RazorpayMappingError, match="order_id"):
        adapter.map_payment(payload)


# ------------------------------------------------------------------
# Refund mapping
# ------------------------------------------------------------------


def test_map_refund_with_explicit_order_id(adapter: RazorpayAdapter) -> None:
    result = adapter.map_refund(SAMPLE_REFUND, order_id="order_Mabc123xyz")
    assert isinstance(result.record, NormalizedRefund)
    assert result.record.refund_id == "rfnd_Jkl012mno"
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.record.refund_amount_paise == 40478
    assert result.record.created_at == unix_to_datetime(SAMPLE_REFUND["created_at"], "created_at")
    assert "payment_id" in result.unmapped_razorpay_fields
    assert "status" in result.unmapped_razorpay_fields


def test_map_refund_resolves_order_id_from_payment(adapter: RazorpayAdapter) -> None:
    result = adapter.map_refund(SAMPLE_REFUND, payment=SAMPLE_PAYMENT)
    assert result.record.order_id == "order_Mabc123xyz"
    assert any("payment lookup" in w for w in result.warnings)


def test_map_refund_with_order_id_on_payload(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_REFUND, "order_id": "order_Mabc123xyz"}
    result = adapter.map_refund(payload)
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.warnings == ()


def test_map_refund_missing_order_id(adapter: RazorpayAdapter) -> None:
    with pytest.raises(RazorpayMappingError, match="order_id"):
        adapter.map_refund(SAMPLE_REFUND)


# ------------------------------------------------------------------
# Settlement mapping (batch entity)
# ------------------------------------------------------------------


def test_map_settlement_batch_without_order_id_is_partial(adapter: RazorpayAdapter) -> None:
    result = adapter.map_settlement(SAMPLE_SETTLEMENT_BATCH)
    assert isinstance(result, PartialMappingResult)
    assert result.available_fields["settlement_id"] == "setl_Ghi789rst"
    assert result.available_fields["amount_paise"] == 5000000
    assert result.available_fields["fee_paise"] == 120000
    assert result.available_fields["tax_paise"] == 18000
    assert result.available_fields["settled_at"] == unix_to_datetime(
        SAMPLE_SETTLEMENT_BATCH["settled_at"], "settled_at"
    )
    assert "order_id" in result.missing_recon_fields
    assert any("batch payout" in w for w in result.warnings)


def test_map_settlement_with_explicit_order_id(adapter: RazorpayAdapter) -> None:
    # Smaller amounts so net stays positive after fees
    payload = {
        **SAMPLE_SETTLEMENT_BATCH,
        "amount": 385243,
        "fees": 7704,
        "tax": 6934,
    }
    result = adapter.map_settlement(payload, order_id="order_Mabc123xyz")
    assert isinstance(result, MappingResult)
    assert isinstance(result.record, NormalizedSettlement)
    assert result.record.settlement_id == "setl_Ghi789rst"
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.record.gross_amount_paise == 385243
    assert result.record.net_amount_paise == 370605
    assert any("batch totals" in w for w in result.warnings)


# ------------------------------------------------------------------
# Settlement recon mapping
# ------------------------------------------------------------------


def test_map_settlement_recon_payment_item(adapter: RazorpayAdapter) -> None:
    result = adapter.map_settlement_recon_item(SAMPLE_RECON_PAYMENT)
    assert isinstance(result, MappingResult)
    assert isinstance(result.record, NormalizedSettlement)
    assert result.record.settlement_id == "setl_Ghi789rst"
    assert result.record.order_id == "order_Mabc123xyz"
    assert result.record.gross_amount_paise == 385243
    assert result.record.fee_paise == 7704
    assert result.record.tax_paise == 6934
    assert result.record.net_amount_paise == 370605
    assert result.record.settled_at == unix_to_datetime(
        SAMPLE_RECON_PAYMENT["settled_at"], "settled_at"
    )
    assert any("settlement_utr" in w for w in result.warnings)


def test_map_settlement_recon_refund_item(adapter: RazorpayAdapter) -> None:
    result = adapter.map_settlement_recon_item(SAMPLE_RECON_REFUND)
    assert isinstance(result, MappingResult)
    assert isinstance(result.record, MappedSettlementReconContext)
    assert result.record.recon_type == "refund"
    assert result.record.settlement_utr == "UTR987654321098"
    assert any("NormalizedSettlement" in w for w in result.warnings)
    assert any("NormalizedBankTransaction" in w for w in result.warnings)


def test_map_settlement_recon_payment_missing_order_id(adapter: RazorpayAdapter) -> None:
    payload = {k: v for k, v in SAMPLE_RECON_PAYMENT.items() if k != "order_id"}
    result = adapter.map_settlement_recon_item(payload)
    assert isinstance(result, PartialMappingResult)
    assert "order_id" in result.missing_recon_fields


def test_map_settlement_recon_net_from_credit(adapter: RazorpayAdapter) -> None:
    payload = {**SAMPLE_RECON_PAYMENT, "credit": 99999}
    result = adapter.map_settlement_recon_item(payload)
    assert isinstance(result, MappingResult)
    assert result.record.net_amount_paise == 99999


# ------------------------------------------------------------------
# Timestamp and amount conversion
# ------------------------------------------------------------------


def test_unix_to_datetime_conversion() -> None:
    dt = unix_to_datetime(1722938160, "created_at")
    assert dt == unix_to_datetime(SAMPLE_ORDER["created_at"], "created_at")
    assert dt.tzinfo is None


def test_unix_to_datetime_invalid() -> None:
    with pytest.raises(RazorpayMappingError, match="Invalid Unix timestamp"):
        unix_to_datetime("not-a-ts", "created_at")


def test_unix_to_datetime_missing() -> None:
    with pytest.raises(RazorpayMappingError, match="Missing timestamp"):
        unix_to_datetime(None, "created_at")


# ------------------------------------------------------------------
# Bank transactions explicitly not supported
# ------------------------------------------------------------------


def test_bank_transactions_not_derived(adapter: RazorpayAdapter) -> None:
    assert "NormalizedBankTransaction" in adapter.bank_transactions_not_supported
    assert BANK_TRANSACTIONS_NOT_SUPPORTED == adapter.bank_transactions_not_supported

    # settlement_utr must not become a bank transaction
    result = adapter.map_settlement_recon_item(SAMPLE_RECON_PAYMENT)
    assert isinstance(result, MappingResult)
    assert not hasattr(result.record, "bank_transaction_id")
    assert any("settlement_utr" in w for w in result.warnings)


def test_no_map_bank_transaction_method(adapter: RazorpayAdapter) -> None:
    assert not hasattr(adapter, "map_bank_transaction")

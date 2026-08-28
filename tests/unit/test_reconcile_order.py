"""Behavioral tests for reconcile_order."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from recon_engine import normalize_amount, normalize_timestamp
from tests.conftest import (
    DT_BASE,
    compute_settlement_amounts,
    make_bank_tx,
    make_order,
    make_refund,
    make_settlement,
    minimal_valid_csv_dict,
    reconcile_single,
    write_csv_dataset,
)


def _clean_chain(same_time: bool = True):
    gross = 100_000
    fee, tax, net = compute_settlement_amounts(gross)
    settled = DT_BASE + timedelta(hours=1)
    tx_date = settled if same_time else settled + timedelta(hours=5)
    order = make_order(amount_paise=gross)
    settlement = make_settlement(gross_amount_paise=gross, settled_at=settled)
    bank = make_bank_tx(amount_paise=net, transaction_date=tx_date)
    return order, [settlement], [], [bank]


def test_exact_reconciliation_zero_timestamp():
    order, settlements, refunds, banks = _clean_chain(same_time=True)
    result = reconcile_single(order, settlements, refunds, banks)
    assert result.status == "reconciled"
    assert result.reconciled is True
    assert result.confidence_score == 100


def test_timestamp_within_tolerance():
    order, settlements, refunds, banks = _clean_chain(same_time=False)
    result = reconcile_single(order, settlements, refunds, banks)
    assert result.status == "reconciled_within_timestamp_tolerance"
    assert result.reconciled is True


def test_timestamp_exactly_24h():
    gross = 100_000
    _, _, net = compute_settlement_amounts(gross)
    settled = DT_BASE
    order = make_order(amount_paise=gross)
    settlement = make_settlement(gross_amount_paise=gross, settled_at=settled)
    bank = make_bank_tx(amount_paise=net, transaction_date=settled + timedelta(hours=24))
    result = reconcile_single(order, [settlement], [], [bank])
    assert result.status == "reconciled_within_timestamp_tolerance"
    assert result.reconciled is True


def test_timestamp_outside_tolerance():
    gross = 100_000
    _, _, net = compute_settlement_amounts(gross)
    settled = DT_BASE
    order = make_order(amount_paise=gross)
    settlement = make_settlement(gross_amount_paise=gross, settled_at=settled)
    bank = make_bank_tx(amount_paise=net, transaction_date=settled + timedelta(hours=25))
    result = reconcile_single(order, [settlement], [], [bank])
    assert result.status == "unreconciled_timestamp_exceeded"
    assert result.reconciled is False


def test_missing_settlement():
    order = make_order()
    result = reconcile_single(order, [], [], [])
    assert result.status == "unreconciled_missing_settlement"
    assert result.confidence_score == 0


def test_missing_bank():
    order, settlements, _, _ = _clean_chain()
    result = reconcile_single(order, settlements, [], [])
    assert result.status == "unreconciled_missing_bank"
    assert result.confidence_score == 40


def test_settlement_amount_mismatch():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=90_000)
    _, _, net = compute_settlement_amounts(90_000)
    bank = make_bank_tx(amount_paise=net)
    result = reconcile_single(order, [settlement], [], [bank])
    assert result.status == "unreconciled_settlement_amount"
    assert any(e["type"] == "SETTLEMENT_AMOUNT_MISMATCH" for e in result.exceptions)


def test_bank_amount_mismatch():
    order, settlements, _, _ = _clean_chain()
    bank = make_bank_tx(amount_paise=1)
    result = reconcile_single(order, settlements, [], [bank])
    assert result.status == "unreconciled_settlement_amount"
    assert any(e["type"] == "BANK_AMOUNT_MISMATCH" for e in result.exceptions)


def test_refund_adjusted():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=90_000)
    _, _, net = compute_settlement_amounts(90_000)
    bank = make_bank_tx(amount_paise=net)
    refund = make_refund(refund_amount_paise=10_000)
    result = reconcile_single(order, [settlement], [refund], [bank])
    assert result.status == "reconciled_with_refund_adjustment"
    assert result.reconciled is True


def test_refund_not_reflected():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=100_000)
    _, _, net = compute_settlement_amounts(100_000)
    bank = make_bank_tx(amount_paise=net)
    refund = make_refund(refund_amount_paise=10_000)
    result = reconcile_single(order, [settlement], [refund], [bank])
    assert result.status == "unreconciled_refund_not_adjusted"


def test_reference_variation():
    order, settlements, _, _ = _clean_chain()
    _, _, net = compute_settlement_amounts(100_000)
    bank = make_bank_tx(
        settlement_ref="STL-0001",
        amount_paise=net,
        ref_category="reference_variation",
        resolved_settlement_id="SET_0001",
    )
    result = reconcile_single(order, settlements, [], [bank])
    assert result.status == "reconciled_with_reference_variation"
    assert result.reconciled is True


def test_orphan_reference_no_match():
    order, settlements, _, _ = _clean_chain()
    orphan = make_bank_tx(
        "BNK_O1",
        "ORPHAN-ORD_0001",
        ref_category="orphan",
        resolved_settlement_id=None,
    )
    result = reconcile_single(order, settlements, [], [orphan])
    assert result.status == "unreconciled_missing_bank"


def test_dup_reference_not_valid_link():
    order, settlements, _, _ = _clean_chain()
    dup = make_bank_tx(
        "BNK_D1",
        "DUP-SET_0001",
        ref_category="duplicate",
        resolved_settlement_id=None,
    )
    result = reconcile_single(order, settlements, [], [dup])
    assert result.status == "unreconciled_missing_bank"


def test_duplicate_settlement():
    order = make_order()
    primary = make_settlement("SET_0001", settled_at=DT_BASE + timedelta(hours=1))
    secondary = make_settlement("SET_0002", settled_at=DT_BASE + timedelta(hours=5))
    _, _, net = compute_settlement_amounts(100_000)
    bank = make_bank_tx(amount_paise=net)
    result = reconcile_single(order, [primary, secondary], [], [bank])
    assert result.status == "partially_reconciled_duplicate_settlement"


def test_duplicate_bank_transaction_flagged():
    order, settlements, _, _ = _clean_chain()
    _, _, net = compute_settlement_amounts(100_000)
    valid = make_bank_tx("BNK_0001", "SET_0001", amount_paise=net, resolved_settlement_id="SET_0001")
    dup = make_bank_tx(
        "BNK_D1",
        "DUP-SET_0001",
        amount_paise=net,
        ref_category="duplicate",
        resolved_settlement_id=None,
    )
    result = reconcile_single(order, settlements, [], [valid, dup])
    assert result.reconciled is True
    assert any(e["type"] == "DUPLICATE_BANK_TRANSACTION" for e in result.exceptions)


def test_multiple_exceptions_recorded():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=90_000)
    settled = DT_BASE
    settlement.settled_at = settled
    bank = make_bank_tx(amount_paise=1, transaction_date=settled + timedelta(hours=30))
    result = reconcile_single(order, [settlement], [], [bank])
    types = {e["type"] for e in result.exceptions}
    assert "SETTLEMENT_AMOUNT_MISMATCH" in types
    assert "BANK_AMOUNT_MISMATCH" in types
    assert "TIMESTAMP_OUTSIDE_TOLERANCE" in types


def test_large_integer_paise():
    amount = 999_999_999
    fee, tax, net = compute_settlement_amounts(amount)
    order = make_order(amount_paise=amount)
    settlement = make_settlement(gross_amount_paise=amount)
    bank = make_bank_tx(amount_paise=net)
    result = reconcile_single(order, [settlement], [], [bank])
    assert result.reconciled is True


def test_invalid_money_raises():
    with pytest.raises(ValueError):
        normalize_amount(0, "order.amount")


def test_invalid_timestamp_raises():
    with pytest.raises(ValueError):
        normalize_timestamp("bad", "order.created_at")


def test_missing_columns_on_validate(tmp_path: Path):
    frames = minimal_valid_csv_dict()
    frames["orders"] = frames["orders"].drop(columns=["amount"])
    write_csv_dataset(tmp_path, frames)
    from recon_engine import load_data, validate_inputs

    with pytest.raises(ValueError, match="orders column mismatch"):
        validate_inputs(load_data(tmp_path))


def test_duplicate_ids_on_validate(tmp_path: Path):
    frames = minimal_valid_csv_dict()
    frames["orders"] = pd.concat([frames["orders"], frames["orders"]], ignore_index=True)
    write_csv_dataset(tmp_path, frames)
    from recon_engine import load_data, validate_inputs

    with pytest.raises(ValueError, match="Duplicate order IDs"):
        validate_inputs(load_data(tmp_path))

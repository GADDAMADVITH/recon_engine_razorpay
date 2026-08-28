"""Tests for amount and timestamp comparison."""

from __future__ import annotations

from datetime import timedelta

from recon_engine import compare_amounts, compare_timestamps
from tests.conftest import DT_BASE, compute_settlement_amounts, make_bank_tx, make_order, make_settlement


def test_compare_amounts_exact_match():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=100_000)
    _, _, net = compute_settlement_amounts(100_000)
    bank = make_bank_tx(amount_paise=net)
    result = compare_amounts(order, settlement, bank, 0)
    assert result.settlement_gross_matches_order is True
    assert result.bank_matches_settlement_net is True


def test_compare_amounts_settlement_mismatch():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=90_000)
    result = compare_amounts(order, settlement, None, 0)
    assert result.settlement_gross_matches_order is False


def test_compare_amounts_refund_adjusted():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=90_000)
    result = compare_amounts(order, settlement, None, 10_000)
    assert result.settlement_reflects_refund is True


def test_compare_amounts_refund_not_reflected():
    order = make_order(amount_paise=100_000)
    settlement = make_settlement(gross_amount_paise=100_000)
    result = compare_amounts(order, settlement, None, 10_000)
    assert result.settlement_reflects_refund is False


def test_compare_amounts_bank_mismatch():
    order = make_order()
    settlement = make_settlement()
    bank = make_bank_tx(amount_paise=1)
    result = compare_amounts(order, settlement, bank, 0)
    assert result.bank_matches_settlement_net is False


def test_compare_amounts_missing_settlement():
    order = make_order()
    result = compare_amounts(order, None, None, 0)
    assert result.settlement_gross_paise is None
    assert result.bank_amount_paise is None


def test_compare_timestamps_zero_difference():
    settled = DT_BASE + timedelta(hours=1)
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=settled)
    result = compare_timestamps(settlement, bank, 24)
    assert result.difference_hours == 0.0
    assert result.within_tolerance is True


def test_compare_timestamps_one_second():
    settled = DT_BASE
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=settled + timedelta(seconds=1))
    result = compare_timestamps(settlement, bank, 24)
    assert result.within_tolerance is True
    assert result.difference_hours is not None
    assert result.difference_hours < 0.01


def test_compare_timestamps_23h_59m_59s():
    settled = DT_BASE
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=settled + timedelta(hours=23, minutes=59, seconds=59))
    result = compare_timestamps(settlement, bank, 24)
    assert result.within_tolerance is True


def test_compare_timestamps_exactly_24h():
    settled = DT_BASE
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=settled + timedelta(hours=24))
    result = compare_timestamps(settlement, bank, 24)
    assert result.within_tolerance is True
    assert result.difference_hours == 24.0


def test_compare_timestamps_24h_plus_one_second():
    settled = DT_BASE
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=settled + timedelta(hours=24, seconds=1))
    result = compare_timestamps(settlement, bank, 24)
    assert result.within_tolerance is False


def test_compare_timestamps_negative_raw_difference_uses_abs():
    settled = DT_BASE + timedelta(hours=5)
    settlement = make_settlement(settled_at=settled)
    bank = make_bank_tx(transaction_date=DT_BASE)
    result = compare_timestamps(settlement, bank, 24)
    assert result.difference_hours == 5.0
    assert result.within_tolerance is True

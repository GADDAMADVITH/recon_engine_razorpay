"""Tests for settlement and bank matching."""

from __future__ import annotations

from datetime import timedelta

from recon_engine import calculate_refund_totals, match_bank_for_settlement, match_settlements_for_order
from tests.conftest import DT_BASE, make_bank_tx, make_refund, make_settlement


def test_match_settlements_returns_none_when_missing():
    primary, secondary = match_settlements_for_order("ORD_0001", [])
    assert primary is None
    assert secondary == []


def test_match_settlements_returns_single_primary():
    settlement = make_settlement()
    primary, secondary = match_settlements_for_order("ORD_0001", [settlement])
    assert primary == settlement
    assert secondary == []


def test_match_settlements_picks_earliest_settled_at():
    later = make_settlement(
        "SET_0002", settled_at=DT_BASE + timedelta(hours=5)
    )
    earlier = make_settlement(
        "SET_0001", settled_at=DT_BASE + timedelta(hours=2)
    )
    primary, secondary = match_settlements_for_order("ORD_0001", [later, earlier])
    assert primary.settlement_id == "SET_0001"
    assert len(secondary) == 1


def test_match_settlements_tie_breaks_on_settlement_id():
    s_b = make_settlement("SET_0002", settled_at=DT_BASE + timedelta(hours=2))
    s_a = make_settlement("SET_0001", settled_at=DT_BASE + timedelta(hours=2))
    primary, _ = match_settlements_for_order("ORD_0001", [s_b, s_a])
    assert primary.settlement_id == "SET_0001"


def test_match_bank_prefers_canonical_over_stl():
    canonical = make_bank_tx("BNK_0001", "SET_0001", resolved_settlement_id="SET_0001")
    stl = make_bank_tx(
        "BNK_0002",
        "STL-0001",
        ref_category="reference_variation",
        resolved_settlement_id="SET_0001",
    )
    index = {"SET_0001": [stl, canonical]}
    selected = match_bank_for_settlement("SET_0001", index)
    assert selected.bank_transaction_id == "BNK_0001"


def test_match_bank_returns_none_when_missing():
    assert match_bank_for_settlement("SET_0001", {}) is None


def test_calculate_refund_totals_empty():
    ids, total = calculate_refund_totals("ORD_0001", [])
    assert ids == []
    assert total == 0


def test_calculate_refund_totals_sums_and_sorts():
    refunds = [
        make_refund("REF_0002", refund_amount_paise=20_000),
        make_refund("REF_0001", refund_amount_paise=10_000),
    ]
    ids, total = calculate_refund_totals("ORD_0001", refunds)
    assert ids == ["REF_0001", "REF_0002"]
    assert total == 30_000

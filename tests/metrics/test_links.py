"""Layer C link-level metrics tests."""

from __future__ import annotations

from metrics import _valid_bank_set_match, evaluate_link_level


def _joined(
    *,
    expected_settlement: str | None = "SET_0001",
    actual_settlement: str | None = "SET_0001",
    expected_bank: str | None = "BNK_0001",
    actual_bank: str | None = "BNK_0001",
    expected_valid_ids: list[str] | None = None,
    considered_ids: list[str] | None = None,
):
    if expected_valid_ids is None:
        expected_valid_ids = [expected_bank] if expected_bank else []
    if considered_ids is None:
        considered_ids = list(expected_valid_ids)
    return {
        "order_id": "ORD_0001",
        "ground_truth": {
            "primary_settlement_id": expected_settlement,
            "primary_bank_transaction_id": expected_bank,
            "valid_bank_transaction_ids": expected_valid_ids,
        },
        "report": {
            "primary_settlement_id": actual_settlement,
            "valid_bank_transaction_id": actual_bank,
            "bank_transaction_ids_considered": considered_ids,
        },
    }


def test_link_level_settlement_and_bank_match():
    result = evaluate_link_level([_joined()])
    assert result["primary_settlement_match_rate"] == 1.0
    assert result["primary_bank_match_rate"] == 1.0


def test_valid_bank_set_match_null_expected():
    assert _valid_bank_set_match([], [], None) is True


def test_valid_bank_set_match_expected_empty_actual_none():
    assert _valid_bank_set_match([], [], None) is True

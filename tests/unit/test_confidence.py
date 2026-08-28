"""Tests for heuristic confidence scoring."""

from __future__ import annotations

from recon_engine import AmountComparison, TimestampComparison, calculate_confidence


def _amount() -> AmountComparison:
    return AmountComparison(
        order_amount_paise=100_000,
        settlement_gross_paise=100_000,
        settlement_net_paise=96_200,
        bank_amount_paise=96_200,
        expected_post_refund_gross_paise=None,
        total_refund_paise=0,
        settlement_gross_matches_order=True,
        settlement_reflects_refund=None,
        bank_matches_settlement_net=True,
    )


def _ts() -> TimestampComparison:
    return TimestampComparison(
        settlement_settled_at="2026-01-01T01:00:00",
        bank_transaction_date="2026-01-01T01:00:00",
        difference_hours=0.0,
        tolerance_hours=24,
        within_tolerance=True,
    )


def _exc(exc_type: str) -> list[dict]:
    return [{"type": exc_type, "message": "test"}]


def test_confidence_clean_case_is_heuristic_100():
    score = calculate_confidence([], _amount(), _ts(), True, True)
    assert score == 100


def test_confidence_reference_variation_penalty():
    score = calculate_confidence(_exc("REFERENCE_VARIATION"), _amount(), _ts(), True, True)
    assert score == 95


def test_confidence_timestamp_exceeded_penalty():
    score = calculate_confidence(_exc("TIMESTAMP_OUTSIDE_TOLERANCE"), _amount(), _ts(), True, True)
    assert score == 85


def test_confidence_refund_not_reflected_penalty():
    score = calculate_confidence(_exc("REFUND_NOT_REFLECTED"), _amount(), _ts(), True, True)
    assert score == 80


def test_confidence_bank_mismatch_penalty():
    score = calculate_confidence(_exc("BANK_AMOUNT_MISMATCH"), _amount(), _ts(), True, True)
    assert score == 75


def test_confidence_settlement_mismatch_penalty():
    score = calculate_confidence(_exc("SETTLEMENT_AMOUNT_MISMATCH"), _amount(), _ts(), True, True)
    assert score == 70


def test_confidence_missing_bank_capped_at_40():
    score = calculate_confidence(_exc("MISSING_BANK_TRANSACTION"), _amount(), _ts(), False, True)
    assert score == 40


def test_confidence_missing_settlement_is_zero():
    score = calculate_confidence(_exc("MISSING_SETTLEMENT"), _amount(), _ts(), False, False)
    assert score == 0


def test_confidence_duplicate_settlement_penalty():
    score = calculate_confidence(_exc("DUPLICATE_SETTLEMENT"), _amount(), _ts(), True, True)
    assert score == 90


def test_confidence_combined_penalties_clamped_to_zero():
    score = calculate_confidence(
        _exc("MISSING_SETTLEMENT") + _exc("SETTLEMENT_AMOUNT_MISMATCH"),
        _amount(),
        _ts(),
        False,
        False,
    )
    assert score == 0


def test_confidence_upper_bound_clamped():
    score = calculate_confidence([], _amount(), _ts(), True, True)
    assert score <= 100

"""Tests for determine_status precedence."""

from __future__ import annotations

from recon_engine import AmountComparison, TimestampComparison, determine_status


def _amount(**kwargs) -> AmountComparison:
    defaults = dict(
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
    defaults.update(kwargs)
    return AmountComparison(**defaults)


def _ts(**kwargs) -> TimestampComparison:
    defaults = dict(
        settlement_settled_at="2026-01-01T01:00:00",
        bank_transaction_date="2026-01-01T01:00:00",
        difference_hours=0.0,
        tolerance_hours=24,
        within_tolerance=True,
    )
    defaults.update(kwargs)
    return TimestampComparison(**defaults)


def _exc(exc_type: str) -> list[dict]:
    return [{"type": exc_type, "message": "test"}]


def test_missing_settlement_wins_over_all():
    status, reconciled = determine_status(
        _exc("MISSING_SETTLEMENT") + _exc("SETTLEMENT_AMOUNT_MISMATCH"),
        _amount(),
        _ts(),
        False,
        False,
    )
    assert status == "unreconciled_missing_settlement"
    assert reconciled is False


def test_missing_bank_beats_amount_mismatch():
    status, reconciled = determine_status(
        _exc("MISSING_BANK_TRANSACTION") + _exc("SETTLEMENT_AMOUNT_MISMATCH"),
        _amount(),
        _ts(),
        False,
        False,
    )
    assert status == "unreconciled_missing_bank"
    assert reconciled is False


def test_duplicate_settlement_clean_primary():
    status, reconciled = determine_status(
        _exc("DUPLICATE_SETTLEMENT"),
        _amount(),
        _ts(),
        False,
        True,
    )
    assert status == "partially_reconciled_duplicate_settlement"
    assert reconciled is False


def test_duplicate_settlement_with_timestamp_failure():
    status, reconciled = determine_status(
        _exc("DUPLICATE_SETTLEMENT") + _exc("TIMESTAMP_OUTSIDE_TOLERANCE"),
        _amount(),
        _ts(within_tolerance=False, difference_hours=30.0),
        False,
        True,
    )
    assert status == "partially_reconciled_duplicate_settlement"
    assert reconciled is False


def test_duplicate_settlement_with_refund_not_reflected():
    status, reconciled = determine_status(
        _exc("DUPLICATE_SETTLEMENT") + _exc("REFUND_NOT_REFLECTED"),
        _amount(settlement_reflects_refund=False),
        _ts(),
        False,
        True,
    )
    assert status == "partially_reconciled_duplicate_settlement"
    assert reconciled is False


def test_duplicate_branch_timestamp_failure_without_missing_bank_in_step2():
    """Duplicate + timestamp failure uses partially_reconciled when MISSING_BANK absent at step 2."""
    status, reconciled = determine_status(
        _exc("DUPLICATE_SETTLEMENT") + _exc("TIMESTAMP_OUTSIDE_TOLERANCE"),
        _amount(),
        _ts(within_tolerance=False, difference_hours=30.0),
        False,
        True,
    )
    assert status == "partially_reconciled_duplicate_settlement"
    assert reconciled is False


def test_missing_bank_checked_before_duplicate_block():
    """MISSING_BANK at step 2 wins even if DUPLICATE_SETTLEMENT also present."""
    status, reconciled = determine_status(
        _exc("DUPLICATE_SETTLEMENT") + _exc("MISSING_BANK_TRANSACTION"),
        _amount(),
        _ts(),
        False,
        True,
    )
    assert status == "unreconciled_missing_bank"
    assert reconciled is False


def test_refund_not_reflected_beats_timestamp():
    status, reconciled = determine_status(
        _exc("REFUND_NOT_REFLECTED") + _exc("TIMESTAMP_OUTSIDE_TOLERANCE"),
        _amount(settlement_reflects_refund=False),
        _ts(within_tolerance=False, difference_hours=30.0),
        False,
        False,
    )
    assert status == "unreconciled_refund_not_adjusted"
    assert reconciled is False


def test_settlement_mismatch_beats_timestamp():
    status, reconciled = determine_status(
        _exc("SETTLEMENT_AMOUNT_MISMATCH") + _exc("TIMESTAMP_OUTSIDE_TOLERANCE"),
        _amount(settlement_gross_matches_order=False),
        _ts(within_tolerance=False, difference_hours=30.0),
        False,
        False,
    )
    assert status == "unreconciled_settlement_amount"
    assert reconciled is False


def test_bank_mismatch_status():
    status, reconciled = determine_status(
        _exc("BANK_AMOUNT_MISMATCH"),
        _amount(bank_matches_settlement_net=False),
        _ts(),
        False,
        False,
    )
    assert status == "unreconciled_settlement_amount"
    assert reconciled is False


def test_timestamp_exceeded():
    status, reconciled = determine_status(
        _exc("TIMESTAMP_OUTSIDE_TOLERANCE"),
        _amount(),
        _ts(within_tolerance=False, difference_hours=30.0),
        False,
        False,
    )
    assert status == "unreconciled_timestamp_exceeded"
    assert reconciled is False


def test_refund_adjusted_success():
    status, reconciled = determine_status(
        _exc("REFUND_ADJUSTED"),
        _amount(settlement_reflects_refund=True),
        _ts(),
        False,
        False,
    )
    assert status == "reconciled_with_refund_adjustment"
    assert reconciled is True


def test_reference_variation_success():
    status, reconciled = determine_status(
        _exc("REFERENCE_VARIATION"),
        _amount(),
        _ts(),
        True,
        False,
    )
    assert status == "reconciled_with_reference_variation"
    assert reconciled is True


def test_within_timestamp_tolerance_success():
    status, reconciled = determine_status(
        [],
        _amount(),
        _ts(difference_hours=5.0, within_tolerance=True),
        False,
        False,
    )
    assert status == "reconciled_within_timestamp_tolerance"
    assert reconciled is True


def test_clean_reconciled_zero_timestamp_diff():
    status, reconciled = determine_status([], _amount(), _ts(difference_hours=0.0), False, False)
    assert status == "reconciled"
    assert reconciled is True

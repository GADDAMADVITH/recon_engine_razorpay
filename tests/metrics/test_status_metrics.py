"""Layer B status evaluation metrics tests."""

from __future__ import annotations

from metrics import _statuses_equivalent_relaxed, evaluate_status


def _record(expected_status: str, actual_status: str, order_id: str = "ORD_0001"):
    return {
        "order_id": order_id,
        "ground_truth": {
            "expected_status": expected_status,
            "scenario_type": "exact_match",
        },
        "report": {"status": actual_status},
    }


def test_strict_status_match():
    joined = [_record("reconciled", "reconciled")]
    result = evaluate_status(joined)
    assert result["strict"]["correct"] == 1


def test_strict_status_mismatch():
    joined = [_record("reconciled", "unreconciled_missing_bank")]
    result = evaluate_status(joined)
    assert result["strict"]["incorrect"] == 1
    assert len(result["strict"]["mismatches"]) == 1


def test_relaxed_equivalence_reconciled_and_within_tolerance():
    assert _statuses_equivalent_relaxed("reconciled", "reconciled_within_timestamp_tolerance")
    joined = [_record("reconciled", "reconciled_within_timestamp_tolerance")]
    result = evaluate_status(joined)
    assert result["relaxed"]["correct"] == 1
    assert result["relaxed"]["incorrect"] == 0

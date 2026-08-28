"""Layer A binary classification metrics tests."""

from __future__ import annotations

from metrics import _safe_rate, evaluate_binary_classification


def _joined(expected_reconciled: bool, reconciled: bool, order_id: str = "ORD_0001"):
    return {
        "order_id": order_id,
        "ground_truth": {
            "expected_reconciled": expected_reconciled,
            "expected_status": "reconciled",
            "scenario_type": "exact_match",
        },
        "report": {"reconciled": reconciled, "status": "reconciled"},
    }


def test_binary_tp_fp_fn_tn():
    joined = [
        _joined(True, True, "O1"),
        _joined(False, True, "O2"),
        _joined(True, False, "O3"),
        _joined(False, False, "O4"),
    ]
    result = evaluate_binary_classification(joined)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["true_negatives"] == 1
    assert result["accuracy"] == 0.5
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1_score"] == 0.5


def test_binary_perfect_scores():
    joined = [_joined(True, True, "O1"), _joined(False, False, "O2")]
    result = evaluate_binary_classification(joined)
    assert result["accuracy"] == 1.0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1_score"] == 1.0


def test_safe_rate_zero_denominator():
    assert _safe_rate(0, 0) is None

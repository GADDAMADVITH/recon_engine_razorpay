"""Layer F amount validation metrics tests."""

from __future__ import annotations

from metrics import evaluate_amount_validation


def test_amount_validation_matches_mismatch_details():
    joined = [
        {
            "order_id": "ORD_0001",
            "ground_truth": {
                "scenario_type": "settlement_amount_mismatch",
                "mismatch_details": {
                    "order_amount_paise": 100_000,
                    "settlement_gross_paise": 90_000,
                    "settlement_net_paise": 86_580,
                    "bank_amount_paise": 86_580,
                },
            },
            "report": {
                "amount_comparison": {
                    "order_amount_paise": 100_000,
                    "settlement_gross_paise": 90_000,
                    "settlement_net_paise": 86_580,
                    "bank_amount_paise": 86_580,
                }
            },
        }
    ]
    result = evaluate_amount_validation(joined)
    assert result["mismatch_cases_checked"] == 1
    assert result["mismatch_cases_correctly_represented"] == 1


def test_amount_validation_skips_without_mismatch_details():
    joined = [
        {
            "order_id": "ORD_0001",
            "ground_truth": {"scenario_type": "exact_match"},
            "report": {"amount_comparison": {}},
        }
    ]
    result = evaluate_amount_validation(joined)
    assert result["mismatch_cases_checked"] == 0

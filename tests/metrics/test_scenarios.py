"""Layer D scenario evaluation metrics tests."""

from __future__ import annotations

from metrics import evaluate_scenarios


def test_scenario_grouping_and_accuracy():
    joined = [
        {
            "order_id": "ORD_0001",
            "ground_truth": {
                "scenario_type": "exact_match",
                "expected_reconciled": True,
                "expected_status": "reconciled",
                "primary_settlement_id": "SET_0001",
                "primary_bank_transaction_id": "BNK_0001",
            },
            "report": {
                "reconciled": True,
                "status": "reconciled",
                "primary_settlement_id": "SET_0001",
                "valid_bank_transaction_id": "BNK_0001",
            },
        },
        {
            "order_id": "ORD_0002",
            "ground_truth": {
                "scenario_type": "missing_bank_transaction",
                "expected_reconciled": False,
                "expected_status": "unreconciled_missing_bank",
                "primary_settlement_id": "SET_0002",
                "primary_bank_transaction_id": None,
            },
            "report": {
                "reconciled": False,
                "status": "unreconciled_missing_bank",
                "primary_settlement_id": "SET_0002",
                "valid_bank_transaction_id": None,
            },
        },
    ]
    result = evaluate_scenarios(joined)
    assert set(result.keys()) == {"exact_match", "missing_bank_transaction"}
    assert result["exact_match"]["binary_accuracy"] == 1.0
    assert result["missing_bank_transaction"]["binary_accuracy"] == 1.0

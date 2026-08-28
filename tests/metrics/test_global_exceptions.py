"""Layer E global exception evaluation tests."""

from __future__ import annotations

from metrics import evaluate_global_exceptions


def test_global_orphan_and_duplicate_detection():
    ground_truth = {
        "special_records": {
            "orphan_bank_transactions": [{"bank_transaction_id": "BNK_O1"}],
            "duplicate_bank_transactions": [{"bank_transaction_id": "BNK_D1"}],
            "settlements_without_bank": ["SET_0099"],
        }
    }
    report = {
        "global_exceptions": [
            {"type": "ORPHAN_BANK_TRANSACTION", "bank_transaction_id": "BNK_O1"},
            {"type": "DUPLICATE_BANK_TRANSACTION", "bank_transaction_id": "BNK_D1"},
            {"type": "MISSING_BANK_TRANSACTION", "settlement_id": "SET_0099"},
        ]
    }
    result = evaluate_global_exceptions(ground_truth, report)
    assert result["orphan_bank_transactions"]["detection_rate"] == 1.0
    assert result["duplicate_bank_transactions"]["detection_rate"] == 1.0
    assert result["settlements_without_bank"]["detection_rate"] == 1.0

"""Schema validation and join tests for metrics."""

from __future__ import annotations

import pytest

from metrics import EXPECTED_ORDER_COUNT, join_records, validate_schemas


def _minimal_gt_scenario(order_id: str = "ORD_0001") -> dict:
    return {
        "order_id": order_id,
        "scenario_type": "exact_match",
        "expected_status": "reconciled",
        "expected_reconciled": True,
        "evaluation_grain": "order",
        "primary_settlement_id": "SET_0001",
        "primary_bank_transaction_id": "BNK_0001",
        "valid_bank_transaction_ids": ["BNK_0001"],
    }


def _minimal_report_order(order_id: str = "ORD_0001") -> dict:
    return {
        "order_id": order_id,
        "status": "reconciled",
        "reconciled": True,
        "primary_settlement_id": "SET_0001",
        "valid_bank_transaction_id": "BNK_0001",
        "bank_transaction_ids_considered": ["BNK_0001"],
        "amount_comparison": {},
    }


def _full_gt_and_report():
    scenarios = [_minimal_gt_scenario(f"ORD_{i:04d}") for i in range(1, EXPECTED_ORDER_COUNT + 1)]
    orders = [_minimal_report_order(f"ORD_{i:04d}") for i in range(1, EXPECTED_ORDER_COUNT + 1)]
    gt = {"metadata": {"evaluation_grain": "order"}, "scenarios": scenarios}
    report = {"metadata": {"evaluation_grain": "order"}, "order_results": orders}
    return gt, report


def test_validate_schemas_rejects_missing_field():
    gt, report = _full_gt_and_report()
    del report["order_results"][0]["status"]
    with pytest.raises(ValueError, match="missing status"):
        validate_schemas(gt, report)


def test_validate_schemas_rejects_count_mismatch():
    gt, report = _full_gt_and_report()
    report["order_results"].pop()
    with pytest.raises(ValueError, match=f"Expected {EXPECTED_ORDER_COUNT}"):
        validate_schemas(gt, report)


def test_join_records_sorted_by_order_id():
    gt = {
        "scenarios": [_minimal_gt_scenario("ORD_0002"), _minimal_gt_scenario("ORD_0001")],
    }
    report = {
        "order_results": [_minimal_report_order("ORD_0001"), _minimal_report_order("ORD_0002")],
    }
    joined = join_records(gt, report)
    assert [r["order_id"] for r in joined] == ["ORD_0001", "ORD_0002"]

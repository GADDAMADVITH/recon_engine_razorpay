"""Ground truth schema and consistency tests."""

from __future__ import annotations

import json
from pathlib import Path

from data_gen import (
    EXPECTED_RECONCILED_BY_STATUS,
    REQUIRED_GROUND_TRUTH_ORDER_FIELDS,
    build_ground_truth,
    generate_bank_transactions,
    generate_orders,
    generate_refunds,
    generate_settlements,
    reset_random_state,
)

FIXTURE_GT = Path(__file__).resolve().parents[2] / "data" / "ground_truth.json"


def test_committed_ground_truth_has_required_fields():
    with FIXTURE_GT.open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    for scenario in ground_truth["scenarios"]:
        for field in REQUIRED_GROUND_TRUTH_ORDER_FIELDS:
            assert field in scenario


def test_expected_reconciled_consistent_with_status():
    with FIXTURE_GT.open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    for scenario in ground_truth["scenarios"]:
        expected_status = scenario["expected_status"]
        assert scenario["expected_reconciled"] == EXPECTED_RECONCILED_BY_STATUS[expected_status]


def test_build_ground_truth_in_memory():
    reset_random_state()
    orders = generate_orders()
    settlements = generate_settlements(orders)
    refunds = generate_refunds(orders)
    bank = generate_bank_transactions(settlements, orders)
    gt = build_ground_truth(orders, settlements, refunds, bank)
    assert len(gt["scenarios"]) == 100
    assert len(gt["scenario_counts"]) == 10

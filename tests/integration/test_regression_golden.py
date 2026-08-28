"""Full 50-order golden regression test."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from metrics import build_evaluation
from tests.conftest import FIXTURE_DATA_DIR, run_engine_pipeline

pytestmark = pytest.mark.integration


@pytest.fixture
def full_fixture_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "data"
    dest.mkdir()
    for name in (
        "orders.csv",
        "settlements.csv",
        "refunds.csv",
        "bank.csv",
        "ground_truth.json",
    ):
        shutil.copy2(FIXTURE_DATA_DIR / name, dest / name)
    return dest


def test_golden_regression_contract(full_fixture_copy: Path):
    report = run_engine_pipeline(full_fixture_copy)
    with (full_fixture_copy / "ground_truth.json").open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    evaluation = build_evaluation(ground_truth, report)

    binary = evaluation["binary_classification"]
    status = evaluation["status_evaluation"]
    links = evaluation["link_level_evaluation"]
    scenarios = evaluation["scenario_evaluation"]
    global_exc = evaluation["global_exception_evaluation"]

    assert evaluation["summary"]["orders_evaluated"] == 50
    assert binary["true_positives"] == 26
    assert binary["false_positives"] == 0
    assert binary["false_negatives"] == 0
    assert binary["true_negatives"] == 24
    assert binary["accuracy"] == 1.0
    assert binary["precision"] == 1.0
    assert binary["recall"] == 1.0
    assert binary["f1_score"] == 1.0

    assert status["strict"]["correct"] == 39
    assert status["relaxed"]["correct"] == 50

    for scenario_type, metrics in scenarios.items():
        assert metrics["binary_accuracy"] == 1.0, scenario_type

    assert links["primary_settlement_match_rate"] == 1.0
    assert links["primary_bank_match_rate"] == 1.0
    assert links["valid_bank_set_match_rate"] == 1.0

    assert global_exc["orphan_bank_transactions"]["detection_rate"] == 1.0
    assert global_exc["duplicate_bank_transactions"]["detection_rate"] == 1.0
    assert global_exc["settlements_without_bank"]["detection_rate"] == 1.0


def test_reconciliation_deterministic(full_fixture_copy: Path):
    first = run_engine_pipeline(full_fixture_copy)
    second = run_engine_pipeline(full_fixture_copy)
    assert first == second


def test_evaluation_deterministic(full_fixture_copy: Path):
    report = run_engine_pipeline(full_fixture_copy)
    with (full_fixture_copy / "ground_truth.json").open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    first = build_evaluation(ground_truth, report)
    second = build_evaluation(ground_truth, report)
    assert first == second


def test_generated_at_from_input_timestamps(full_fixture_copy: Path):
    report = run_engine_pipeline(full_fixture_copy)
    generated_at = report["metadata"]["generated_at"]
    assert generated_at == "2026-09-02T10:49:00"


def test_reconcile_all_order_stability(full_fixture_copy: Path):
    report = run_engine_pipeline(full_fixture_copy)
    order_ids = [r["order_id"] for r in report["order_results"]]
    assert order_ids == sorted(order_ids)

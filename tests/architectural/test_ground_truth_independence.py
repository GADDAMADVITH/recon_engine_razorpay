"""Ground-truth architectural independence tests."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from tests.conftest import minimal_valid_csv_dict, run_engine_pipeline, write_csv_dataset


def test_recon_engine_source_has_no_ground_truth_literal():
    source = (Path(__file__).resolve().parents[2] / "recon_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "ground_truth.json" not in literals
    assert "ground_truth" not in literals


def test_recon_engine_does_not_import_metrics_or_data_gen():
    recon = importlib.import_module("recon_engine")
    assert "metrics" not in recon.__dict__
    assert "data_gen" not in recon.__dict__


def test_metrics_does_not_import_recon_engine():
    import metrics

    assert "recon_engine" not in metrics.__dict__


def test_reconciliation_unchanged_when_ground_truth_mutated(tmp_path: Path):
    write_csv_dataset(tmp_path, minimal_valid_csv_dict())
    report_before = run_engine_pipeline(tmp_path)

    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(
        json.dumps(
            {
                "metadata": {"evaluation_grain": "order"},
                "scenarios": [
                    {
                        "order_id": "ORD_0001",
                        "expected_status": "unreconciled_missing_settlement",
                        "expected_reconciled": False,
                        "scenario_type": "tampered",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report_after = run_engine_pipeline(tmp_path)
    assert report_before == report_after


def test_reconciliation_unchanged_when_ground_truth_deleted(tmp_path: Path):
    frames = minimal_valid_csv_dict()
    write_csv_dataset(tmp_path, frames)
    report_before = run_engine_pipeline(tmp_path)
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text("{}", encoding="utf-8")
    gt_path.unlink()
    report_after = run_engine_pipeline(tmp_path)
    assert report_before == report_after

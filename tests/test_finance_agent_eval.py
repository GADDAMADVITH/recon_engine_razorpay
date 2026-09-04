"""Tests for Finance Controller held-out evaluation harness."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
    run_finance_controller,
)
from finance_agent_eval import (
    DATASET_ID,
    EVAL_DATASET_PATH,
    LABELING_GUIDE,
    build_held_out_dataset,
    evaluate_finance_controller,
    format_evaluation_summary,
    load_held_out_dataset,
    write_held_out_dataset,
)

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dataset_file_exists_and_loads():
    assert EVAL_DATASET_PATH.exists()
    dataset = load_held_out_dataset()
    assert dataset["dataset_id"] == DATASET_ID
    assert dataset["held_out"] is True
    assert dataset["record_count"] >= 50
    assert len(dataset["records"]) >= 50


def test_dataset_is_held_out_not_demo():
    dataset = load_held_out_dataset()
    assert dataset["held_out"] is True
    assert "demo" in dataset.get("demo_data_note", "").lower()
    # Held-out records use FCEVAL_* IDs — not the demo ORD_* narrative path.
    for rec in dataset["records"]:
        assert str(rec["record_id"]).startswith("FCEVAL_")
        assert str(rec["order_result"]["order_id"]).startswith("FCEVAL_")
        # No demo bank rows embedded as evaluation fixtures.
        assert "DEMO_BNK" not in json.dumps(rec["order_result"])


def test_expected_labels_independent_from_agent_output():
    """Labels must be pre-authored in the dataset — not filled by calling the agent."""
    dataset = load_held_out_dataset()
    assert "expected_decision" in dataset["records"][0]
    assert dataset["label_source"]
    assert "without calling" in dataset["label_source"].lower()

    rec = copy.deepcopy(dataset["records"][0])
    stored_expected = rec["expected_decision"]
    assert stored_expected in {
        DECISION_NO_ACTION,
        DECISION_FLAG_FOR_REVIEW,
        DECISION_VERIFY_REFUND,
        DECISION_ESCALATE_MISSING_BANK,
        "ESCALATE_MISSING_SETTLEMENT",
    }
    assert "label_rationale" in rec

    # Builder assigns expected=... literals; it must not invoke the agent.
    import inspect

    import finance_agent_eval as eval_mod

    src = inspect.getsource(eval_mod.build_held_out_records)
    assert "decide_for_order(" not in src
    assert "run_finance_controller(" not in src
    assert "expected=" in src


def test_labeling_guide_documents_fp_fn():
    assert "false_positive" in LABELING_GUIDE["definitions"]
    assert "false_negative" in LABELING_GUIDE["definitions"]


def test_build_dataset_has_all_decision_classes():
    dataset = build_held_out_dataset()
    counts = dataset["expected_decision_counts"]
    for key in (
        "NO_ACTION",
        "FLAG_FOR_REVIEW",
        "VERIFY_REFUND",
        "ESCALATE_MISSING_BANK",
        "ESCALATE_MISSING_SETTLEMENT",
    ):
        assert counts.get(key, 0) >= 1, f"Missing support for {key}"


def test_accuracy_calculation_perfect_on_aligned_labels():
    result = evaluate_finance_controller()
    assert result["records_evaluated"] == (
        result["correct_decisions"] + result["incorrect_decisions"]
    )
    assert result["accuracy"] == (
        result["correct_decisions"] / result["records_evaluated"]
    )


def test_incorrect_prediction_detection_with_mock():
    dataset = load_held_out_dataset()

    def always_flag(_order: dict) -> str:
        return DECISION_FLAG_FOR_REVIEW

    result = evaluate_finance_controller(dataset, predict_fn=always_flag)
    assert result["incorrect_decisions"] > 0
    assert result["accuracy"] < 1.0
    assert len(result["errors"]) == result["incorrect_decisions"]
    expected_flag = sum(
        1
        for r in dataset["records"]
        if r["expected_decision"] == DECISION_FLAG_FOR_REVIEW
    )
    assert result["correct_decisions"] == expected_flag


def test_precision_recall_f1_and_confusion_matrix():
    result = evaluate_finance_controller()
    labels = result["confusion_matrix"]["labels"]
    matrix = result["confusion_matrix"]["matrix"]
    assert set(labels) >= {
        "NO_ACTION",
        "FLAG_FOR_REVIEW",
        "VERIFY_REFUND",
        "ESCALATE_MISSING_BANK",
        "ESCALATE_MISSING_SETTLEMENT",
    }
    for exp in labels:
        assert exp in matrix
        row_sum = sum(matrix[exp].values())
        support = result["per_decision"][exp]["support"]
        assert row_sum == support

    for _label, metrics in result["per_decision"].items():
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "false_positives" in metrics
        assert "false_negatives" in metrics
        if metrics["support"] > 0 and result["accuracy"] == 1.0:
            assert metrics["precision"] == 1.0
            assert metrics["recall"] == 1.0
            assert metrics["f1"] == 1.0


def test_false_positives_and_false_negatives_with_mock():
    dataset = {
        "dataset_id": DATASET_ID,
        "held_out": True,
        "label_source": "unit-test",
        "records": [
            {
                "record_id": "FCEVAL_T1",
                "scenario_type": "clean",
                "expected_decision": DECISION_NO_ACTION,
                "label_rationale": "test",
                "order_result": {
                    "order_id": "FCEVAL_T1",
                    "status": "reconciled",
                    "reconciled": True,
                    "confidence_score": 90,
                    "exceptions": [],
                    "amount_comparison": {},
                    "timestamp_comparison": {},
                    "rules_triggered": [],
                    "audit_trail": [],
                },
            },
            {
                "record_id": "FCEVAL_T2",
                "scenario_type": "refund",
                "expected_decision": DECISION_VERIFY_REFUND,
                "label_rationale": "test",
                "order_result": {
                    "order_id": "FCEVAL_T2",
                    "status": "reconciled_with_refund_adjustment",
                    "reconciled": True,
                    "confidence_score": 80,
                    "exceptions": [{"type": "REFUND_ADJUSTED", "message": "adj"}],
                    "amount_comparison": {},
                    "timestamp_comparison": {},
                    "rules_triggered": [],
                    "audit_trail": [],
                },
            },
        ],
    }

    def wrong_predict(_order: dict) -> str:
        return DECISION_VERIFY_REFUND

    result = evaluate_finance_controller(dataset, predict_fn=wrong_predict)
    no_action = result["per_decision"][DECISION_NO_ACTION]
    verify = result["per_decision"][DECISION_VERIFY_REFUND]
    assert no_action["false_negatives"] == 1
    assert no_action["false_positives"] == 0
    assert verify["false_positives"] == 1
    assert verify["true_positives"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["expected_decision"] == DECISION_NO_ACTION
    assert result["errors"][0]["predicted_decision"] == DECISION_VERIFY_REFUND


def test_undefined_metric_when_no_predictions():
    dataset = {
        "dataset_id": DATASET_ID,
        "held_out": True,
        "label_source": "unit-test",
        "records": [
            {
                "record_id": "FCEVAL_U1",
                "scenario_type": "clean",
                "expected_decision": DECISION_NO_ACTION,
                "label_rationale": "test",
                "order_result": {
                    "order_id": "FCEVAL_U1",
                    "status": "reconciled",
                    "reconciled": True,
                    "confidence_score": 99,
                    "exceptions": [],
                    "amount_comparison": {},
                    "timestamp_comparison": {},
                    "rules_triggered": [],
                    "audit_trail": [],
                },
            }
        ],
    }
    result = evaluate_finance_controller(
        dataset, predict_fn=lambda _o: DECISION_NO_ACTION
    )
    bank = result["per_decision"][DECISION_ESCALATE_MISSING_BANK]
    assert bank["support"] == 0
    assert bank["precision"] is None
    assert bank["recall"] is None
    assert bank["f1"] is None


def test_unknown_unsupported_prediction_counted():
    dataset = {
        "dataset_id": DATASET_ID,
        "held_out": True,
        "label_source": "unit-test",
        "records": [
            {
                "record_id": "FCEVAL_X1",
                "scenario_type": "clean",
                "expected_decision": DECISION_NO_ACTION,
                "label_rationale": "test",
                "order_result": {
                    "order_id": "FCEVAL_X1",
                    "status": "reconciled",
                    "reconciled": True,
                    "confidence_score": 90,
                    "exceptions": [],
                    "amount_comparison": {},
                    "timestamp_comparison": {},
                    "rules_triggered": [],
                    "audit_trail": [],
                },
            }
        ],
    }
    result = evaluate_finance_controller(
        dataset, predict_fn=lambda _o: "NOT_AN_ALLOWED_DECISION"
    )
    assert result["error_analysis"]["unknown_unsupported_predictions"] == 1
    assert result["incorrect_decisions"] == 1


def test_exception_list_fields():
    dataset = load_held_out_dataset()

    def flip(order: dict) -> str:
        real = decide_for_order(order).decision
        return (
            DECISION_FLAG_FOR_REVIEW
            if real == DECISION_NO_ACTION
            else DECISION_NO_ACTION
        )

    result = evaluate_finance_controller(dataset, predict_fn=flip)
    assert result["errors"]
    err = result["errors"][0]
    for key in (
        "record_id",
        "order_id",
        "expected_decision",
        "predicted_decision",
        "reconciliation_status",
        "confidence_score",
        "exception_types",
        "mismatch_reason",
    ):
        assert key in err


def test_throughput_fields_present():
    result = evaluate_finance_controller()
    thr = result["throughput"]
    assert thr["records_processed"] == result["records_evaluated"]
    assert isinstance(thr["elapsed_seconds"], float)
    assert thr["elapsed_seconds"] >= 0
    assert thr["records_per_second"] is None or thr["records_per_second"] > 0


def test_no_secret_leakage_in_evaluation_output():
    result = evaluate_finance_controller()
    blob = json.dumps(result)
    for needle in (
        "GEMINI_API_KEY",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_KEY_ID",
        "api_key",
        "Bearer ",
    ):
        assert needle not in blob
    summary = format_evaluation_summary(result)
    assert "GEMINI_API_KEY" not in summary


def test_existing_finance_controller_behavior_unchanged_on_demo_batch():
    """Evaluation must not alter agent policy; demo/production batch stays stable."""
    with (PROJECT_ROOT / "data" / "demo_bank.csv").open("rb") as handle:
        response = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    orders = response.json()["order_results"]
    by_id = {o["order_id"]: o for o in orders}
    assert decide_for_order(by_id["ORD_0001"]).decision == DECISION_NO_ACTION
    assert decide_for_order(by_id["ORD_0002"]).decision == DECISION_FLAG_FOR_REVIEW
    assert decide_for_order(by_id["ORD_0003"]).decision == DECISION_ESCALATE_MISSING_BANK
    assert decide_for_order(by_id["ORD_0033"]).decision == DECISION_VERIFY_REFUND
    assert decide_for_order(by_id["ORD_0024"]).decision == "ESCALATE_MISSING_SETTLEMENT"


def test_production_hundred_record_batch_still_matches():
    report = client.get("/api/v1/reconciliation/report").json()
    batch = run_finance_controller(report)
    assert batch.records_processed == 100
    assert batch.decisions_by_type["NO_ACTION"] == 40
    assert batch.decisions_by_type["FLAG_FOR_REVIEW"] == 32
    assert batch.decisions_by_type["ESCALATE_MISSING_BANK"] == 10
    assert batch.decisions_by_type["VERIFY_REFUND"] == 10
    assert batch.decisions_by_type["ESCALATE_MISSING_SETTLEMENT"] == 8


def test_evaluation_api_endpoint():
    response = client.get("/api/v1/finance-controller/evaluation")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset"] == DATASET_ID
    assert body["records_evaluated"] >= 50
    assert "accuracy" in body
    assert "per_decision" in body
    assert "confusion_matrix" in body
    assert "errors" in body
    assert "throughput" in body
    assert "GEMINI_API_KEY" not in response.text
    assert "RAZORPAY_KEY_SECRET" not in response.text


def test_write_and_reload_dataset_roundtrip(tmp_path: Path):
    path = tmp_path / "finance_controller_eval_v1.json"
    write_held_out_dataset(path)
    loaded = load_held_out_dataset(path)
    assert loaded["record_count"] == len(loaded["records"])
    assert loaded["record_count"] >= 50

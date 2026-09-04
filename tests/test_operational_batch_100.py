"""Operational batch expansion contract: 100+ records through existing pipeline."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from data_gen import NUM_ORDERS
from finance_agent import decide_for_order, run_finance_controller
from finance_agent_eval import evaluate_finance_controller, load_held_out_dataset
from finance_agent_run import configure_run_store, reset_run_store, run_finance_controller_agent

client = TestClient(app)
DEMO_BANK = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"
SECRET_MARKERS = ("GEMINI_API_KEY", "RAZORPAY_KEY", "password", "Authorization")


def setup_function() -> None:
    configure_run_store(persist=False)
    reset_run_store()


def teardown_function() -> None:
    reset_run_store()
    configure_run_store(persist=True)


def test_operational_batch_has_at_least_100_orders():
    report = client.get("/api/v1/reconciliation/report").json()
    assert len(report["order_results"]) >= 100
    assert len(report["order_results"]) == NUM_ORDERS == 100


def test_agent_classifies_every_operational_record_exactly_once():
    report = client.get("/api/v1/reconciliation/report").json()
    batch = run_finance_controller(report)
    assert batch.records_processed == len(report["order_results"])
    assert len(batch.decisions) == batch.records_processed
    assert sum(batch.decisions_by_type.values()) == batch.records_processed
    order_ids = [d.order_id for d in batch.decisions]
    assert len(order_ids) == len(set(order_ids))


def test_run_agent_processes_100_plus_default_batch():
    response = client.post("/api/v1/finance-controller/run-agent")
    assert response.status_code == 200
    body = response.json()
    assert body["records_processed"] >= 100
    assert body["records_processed"] == len(body["decisions"])
    assert sum(body["decisions_by_type"].values()) == body["records_processed"]
    assert body["no_action_count"] + body["review_required_count"] == body["records_processed"]
    assert body["pending_approval_count"] == body["review_required_count"]
    assert body["unresolved_count"] == body["review_required_count"]
    # Coverage of all five decision classes
    for key in (
        "NO_ACTION",
        "FLAG_FOR_REVIEW",
        "ESCALATE_MISSING_BANK",
        "VERIFY_REFUND",
        "ESCALATE_MISSING_SETTLEMENT",
    ):
        assert body["decisions_by_type"].get(key, 0) >= 1


def test_demo_scenarios_retain_import_decisions():
    with DEMO_BANK.open("rb") as handle:
        demo = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        ).json()
    by_id = {o["order_id"]: o for o in demo["order_results"]}
    expected = {
        "ORD_0001": "NO_ACTION",
        "ORD_0002": "FLAG_FOR_REVIEW",
        "ORD_0003": "ESCALATE_MISSING_BANK",
        "ORD_0033": "VERIFY_REFUND",
        "ORD_0024": "ESCALATE_MISSING_SETTLEMENT",
    }
    for order_id, decision in expected.items():
        assert decide_for_order(by_id[order_id]).decision == decision


def test_held_out_evaluation_still_69_and_independent():
    dataset = load_held_out_dataset()
    assert dataset["record_count"] == 69
    assert len(dataset["records"]) == 69
    result = evaluate_finance_controller()
    assert result["records_evaluated"] == 69
    assert result["accuracy"] == 1.0
    api_result = client.get("/api/v1/finance-controller/evaluation").json()
    assert api_result["records_evaluated"] == 69
    assert api_result["accuracy"] == 1.0


def test_original_results_immutable_across_100_batch():
    report = client.get("/api/v1/reconciliation/report").json()
    before = copy.deepcopy(report["order_results"])
    run_finance_controller_agent(report)
    assert report["order_results"] == before


def test_no_secret_leakage_in_expanded_batch_responses():
    payloads = [
        client.post("/api/v1/finance-controller/run-agent").json(),
        client.get("/api/v1/finance-controller/lifecycle").json(),
        client.get("/api/v1/finance-controller/approval-queue").json(),
        client.get("/api/v1/finance-controller/evaluation").json(),
    ]
    blob = json.dumps(payloads)
    for marker in SECRET_MARKERS:
        assert marker not in blob

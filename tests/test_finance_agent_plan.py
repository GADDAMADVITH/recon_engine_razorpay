"""Batch-level Finance Controller agent orchestration tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_agent import decide_for_order, run_finance_controller
from finance_agent_plan import (
    build_finance_controller_agent_plan,
    build_prioritized_work_queue,
    compute_priority,
)
from finance_agent_run import configure_run_store, reset_run_store

client = TestClient(app)
DEMO_BANK = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"
ENDPOINT = "/api/v1/finance-controller/agent-plan"
SECRET_MARKERS = ("GEMINI_API_KEY", "RAZORPAY_KEY", "password", "Authorization", "api_secret")


def setup_function() -> None:
    configure_run_store(persist=False)
    reset_run_store()


def teardown_function() -> None:
    reset_run_store()
    configure_run_store(persist=True)


def _demo_orders() -> list[dict]:
    with DEMO_BANK.open("rb") as handle:
        response = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    return response.json()["order_results"]


def test_agent_plan_100_record_batch():
    response = client.post(ENDPOINT)
    assert response.status_code == 200
    body = response.json()
    assert body["records_processed"] == 100
    assert body["batch_analysis"]["records_processed"] == 100
    assert body["decisions_by_type"] == {
        "ESCALATE_MISSING_BANK": 10,
        "ESCALATE_MISSING_SETTLEMENT": 8,
        "FLAG_FOR_REVIEW": 32,
        "NO_ACTION": 40,
        "VERIFY_REFUND": 10,
    }
    assert body["unresolved_count"] == 60
    assert body["pending_approval_count"] == 60
    assert body["money_moved"] is False
    assert len(body["prioritized_work_queue"]) == 60
    assert "agent_plan" in body
    assert body["agent_plan"]["human_approval_requirements"]["money_moved"] is False


def test_grouping_and_priority_ordering():
    plan = build_finance_controller_agent_plan(client.get("/api/v1/reconciliation/report").json())
    groups = plan["unresolved_groups"]
    assert groups["decision_group_counts"]["ESCALATE_MISSING_SETTLEMENT"] == 8
    assert groups["decision_group_counts"]["ESCALATE_MISSING_BANK"] == 10
    queue = plan["prioritized_work_queue"]
    priorities = [item["priority"] for item in queue]
    assert priorities == sorted(priorities, reverse=True)
    # Missing settlement escalations should rank above FLAG_FOR_REVIEW.
    first_settlement = next(i for i in queue if i["decision"] == "ESCALATE_MISSING_SETTLEMENT")
    first_flag = next(i for i in queue if i["decision"] == "FLAG_FOR_REVIEW")
    assert first_settlement["priority"] >= first_flag["priority"]


def test_deterministic_repeated_output():
    report = client.get("/api/v1/reconciliation/report").json()
    first = build_finance_controller_agent_plan(report)
    second = build_finance_controller_agent_plan(report)
    # run_id / timestamps differ; compare planning payload.
    for key in (
        "records_processed",
        "batch_analysis",
        "decisions_by_type",
        "unresolved_count",
        "pending_approval_count",
        "unresolved_groups",
    ):
        assert first[key] == second[key]
    assert [i["order_id"] for i in first["prioritized_work_queue"]] == [
        i["order_id"] for i in second["prioritized_work_queue"]
    ]
    assert [i["priority"] for i in first["prioritized_work_queue"]] == [
        i["priority"] for i in second["prioritized_work_queue"]
    ]


def test_approval_requirements_on_queue():
    plan = build_finance_controller_agent_plan(client.get("/api/v1/reconciliation/report").json())
    for item in plan["prioritized_work_queue"]:
        assert item["requires_approval"] is True
        assert item["decision"] != "NO_ACTION"
        assert item["proposed_action"] is not None


def test_unknown_exception_fallback_priority():
    synthetic = {
        "order_id": "SYN_UNKNOWN",
        "status": "unreconciled_unknown",
        "reconciled": False,
        "confidence_score": 10,
        "exceptions": [{"type": "TOTALLY_UNKNOWN_EXCEPTION", "severity": "error"}],
        "failed_checks": [],
        "amount_comparison": {},
    }
    decision = decide_for_order(synthetic)
    assert decision.decision == "FLAG_FOR_REVIEW"
    plan = build_finance_controller_agent_plan([synthetic])
    assert plan["records_processed"] == 1
    item = plan["prioritized_work_queue"][0]
    assert item["decision"] == "FLAG_FOR_REVIEW"
    assert item["requires_approval"] is True
    score, reason = compute_priority(item)
    assert score >= 60
    assert "decision_base" in reason


def test_immutability_of_order_results():
    report = client.get("/api/v1/reconciliation/report").json()
    before = copy.deepcopy(report["order_results"])
    build_finance_controller_agent_plan(report)
    assert report["order_results"] == before


def test_demo_five_scenario_matrix():
    orders = _demo_orders()
    plan = build_finance_controller_agent_plan(orders, data_source="provided_order_results")
    by_id = {i["order_id"]: i for i in plan["prioritized_work_queue"]}
    # NO_ACTION ORD_0001 should not appear in work queue.
    assert "ORD_0001" not in by_id
    assert by_id["ORD_0002"]["decision"] == "FLAG_FOR_REVIEW"
    assert by_id["ORD_0003"]["decision"] == "ESCALATE_MISSING_BANK"
    assert by_id["ORD_0033"]["decision"] == "VERIFY_REFUND"
    assert by_id["ORD_0024"]["decision"] == "ESCALATE_MISSING_SETTLEMENT"
    # Escalations rank above flag.
    assert by_id["ORD_0024"]["priority"] >= by_id["ORD_0002"]["priority"]
    assert by_id["ORD_0003"]["priority"] >= by_id["ORD_0002"]["priority"]


def test_empty_input_behavior():
    plan = build_finance_controller_agent_plan([])
    assert plan["records_processed"] == 0
    assert plan["prioritized_work_queue"] == []
    assert plan["unresolved_count"] == 0
    none_plan = build_finance_controller_agent_plan(None)
    assert none_plan["records_processed"] == 0


def test_api_response_contract():
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 200
    body = response.json()
    for key in (
        "run_id",
        "records_processed",
        "batch_analysis",
        "prioritized_work_queue",
        "agent_plan",
        "decisions_by_type",
        "unresolved_count",
        "pending_approval_count",
    ):
        assert key in body
    analysis = body["batch_analysis"]
    for key in (
        "records_processed",
        "reconciled_count",
        "exception_count",
        "unresolved_count",
        "decisions_by_type",
        "approval_required_count",
    ):
        assert key in analysis
    plan = body["agent_plan"]
    for key in (
        "objective",
        "observations",
        "prioritized_work",
        "proposed_actions",
        "unresolved_cases",
        "human_approval_requirements",
    ):
        assert key in plan


def test_decision_distribution_matches_existing_agent():
    report = client.get("/api/v1/reconciliation/report").json()
    batch = run_finance_controller(report)
    plan = build_finance_controller_agent_plan(report)
    assert plan["decisions_by_type"] == dict(batch.decisions_by_type)
    assert plan["records_processed"] == batch.records_processed


def test_no_secret_leakage():
    body = client.post(ENDPOINT).json()
    blob = json.dumps(body)
    for marker in SECRET_MARKERS:
        assert marker not in blob


def test_work_queue_helper_excludes_no_action():
    run = {
        "decisions": [
            {
                "order_id": "A",
                "decision": "NO_ACTION",
                "requires_approval": False,
                "triggered_exceptions": [],
                "original_result": {
                    "order_id": "A",
                    "status": "reconciled",
                    "reconciled": True,
                    "confidence_score": 100,
                    "exception_types": [],
                },
                "proposed_action": None,
                "rationale": "ok",
            },
            {
                "order_id": "B",
                "decision": "FLAG_FOR_REVIEW",
                "requires_approval": True,
                "triggered_exceptions": ["BANK_AMOUNT_MISMATCH"],
                "original_result": {
                    "order_id": "B",
                    "status": "unreconciled_settlement_amount",
                    "reconciled": False,
                    "confidence_score": 40,
                    "exception_types": ["BANK_AMOUNT_MISMATCH"],
                },
                "proposed_action": "RECORD_REVIEW",
                "rationale": "mismatch",
            },
        ]
    }
    queue = build_prioritized_work_queue(run)
    assert len(queue) == 1
    assert queue[0]["order_id"] == "B"

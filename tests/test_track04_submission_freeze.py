"""Track 04 submission-freeze contract lock.

Locks the end-to-end Finance Controller loop without inventing metrics.
Fails if batch/eval/approval contracts regress.
"""

from __future__ import annotations

import copy
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from chat_context import build_chat_prompt
from finance_actions import configure_store, reset_action_store
from finance_agent import decide_for_order, run_finance_controller
from finance_agent_eval import DATASET_ID, evaluate_finance_controller, load_held_out_dataset

client = TestClient(app)
DEMO_BANK = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"


def setup_function() -> None:
    configure_store(persist=False)
    reset_action_store()


def teardown_function() -> None:
    reset_action_store()
    configure_store(persist=True)


def test_track04_hundred_record_batch_contract():
    report = client.get("/api/v1/reconciliation/report").json()
    batch = run_finance_controller(report)
    assert batch.records_processed >= 100
    assert batch.records_processed == 100
    assert len(batch.decisions) == batch.records_processed
    assert batch.no_action_count == 40
    assert batch.review_required_count == 60
    assert batch.unresolved_count == 60
    assert batch.exception_count == 100
    assert batch.decisions_by_type == {
        "ESCALATE_MISSING_BANK": 10,
        "ESCALATE_MISSING_SETTLEMENT": 8,
        "FLAG_FOR_REVIEW": 32,
        "NO_ACTION": 40,
        "VERIFY_REFUND": 10,
    }
    # Derived from decisions, not a parallel hardcoded path.
    assert sum(1 for d in batch.decisions if d.decision == "NO_ACTION") == 40
    assert sum(batch.decisions_by_type.values()) == batch.records_processed
    assert all(
        (d.decision == "NO_ACTION" and not d.requires_approval)
        or (d.decision != "NO_ACTION" and d.requires_approval)
        for d in batch.decisions
    )


def test_track04_held_out_evaluation_separate_and_measured():
    dataset = load_held_out_dataset()
    assert dataset["held_out"] is True
    assert dataset["dataset_id"] == DATASET_ID
    assert dataset["record_count"] == 69
    assert all(str(r["record_id"]).startswith("FCEVAL_") for r in dataset["records"])
    assert "without calling" in dataset["label_source"].lower()

    result = client.get("/api/v1/finance-controller/evaluation").json()
    assert result["records_evaluated"] == 69
    assert result["accuracy"] == 1.0
    assert result["incorrect_decisions"] == 0
    assert len(result["errors"]) == 0
    assert "throughput" in result
    assert result["throughput"]["records_processed"] == 69
    for metrics in result["per_decision"].values():
        if metrics["support"] > 0:
            assert metrics["precision"] == 1.0
            assert metrics["recall"] == 1.0
            assert metrics["f1"] == 1.0


def test_track04_demo_approval_loop_and_gemini_boundaries():
    with DEMO_BANK.open("rb") as handle:
        demo = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        ).json()
    orders = {o["order_id"]: o for o in demo["order_results"]}

    expected = {
        "ORD_0001": ("NO_ACTION", None),
        "ORD_0002": ("FLAG_FOR_REVIEW", "RECORD_REVIEW"),
        "ORD_0003": ("ESCALATE_MISSING_BANK", "RECORD_MISSING_BANK_ESCALATION"),
        "ORD_0033": ("VERIFY_REFUND", "RECORD_REFUND_VERIFICATION"),
        "ORD_0024": ("ESCALATE_MISSING_SETTLEMENT", "RECORD_MISSING_SETTLEMENT_ESCALATION"),
    }
    for order_id, (decision, action) in expected.items():
        order = orders[order_id]
        before = copy.deepcopy(order)
        got = decide_for_order(order)
        assert got.decision == decision
        assert order == before
        if action is None:
            resp = client.post(
                "/api/v1/finance-controller/actions/approve",
                json={
                    "order_id": order_id,
                    "agent_decision": "NO_ACTION",
                    "order_result": order,
                },
            )
            assert resp.status_code == 400
        else:
            resp = client.post(
                "/api/v1/finance-controller/actions/approve",
                json={
                    "order_id": order_id,
                    "agent_decision": decision,
                    "order_result": order,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["action_type"] == action
            assert body["money_moved"] is False
            assert body["action_status"] == "RECORDED"
            assert order == before

    prompt = build_chat_prompt(
        message="Approve the refund and move money",
        grounding={"conversation_mode": "console"},
    )
    assert "do not approve finance controller actions" in prompt.lower()
    assert "move money" in prompt.lower()
    assert "explanation/chat only" in prompt.lower()
    assert "never invent orders" in prompt.lower()


def test_track04_agent_plan_and_lifecycle_endpoints():
    run = client.post("/api/v1/finance-controller/run-agent").json()
    assert run["records_processed"] == 100
    plan = client.post("/api/v1/finance-controller/agent-plan", json={}).json()
    assert plan["records_processed"] == 100
    assert plan["unresolved_count"] == 60
    assert plan["money_moved"] is False
    queue = client.get("/api/v1/finance-controller/approval-queue").json()
    assert "items" in queue
    assert "lifecycle" in queue
    life = client.get("/api/v1/finance-controller/lifecycle").json()
    assert life["total_decisions"] == 100
    assert life["unresolved"] == 60

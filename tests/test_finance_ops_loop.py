"""Human-in-the-loop ops: approval queue, reject, lifecycle, run history."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_actions import (
    ACTION_RECORDED,
    ACTION_REJECTED,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    configure_store,
    list_audit_events,
    reset_action_store,
)
from finance_agent import decide_for_order
from finance_agent_run import (
    configure_run_store,
    get_approval_queue,
    get_lifecycle_metrics,
    list_agent_run_history,
    reset_run_store,
    run_finance_controller_agent,
)

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_BANK_CSV = PROJECT_ROOT / "data" / "demo_bank.csv"

SECRET_MARKERS = ("GEMINI_API_KEY", "RAZORPAY_KEY", "password", "Authorization", "api_secret")


def setup_function() -> None:
    configure_store(persist=False)
    reset_action_store()
    configure_run_store(persist=False)
    reset_run_store()


def teardown_function() -> None:
    reset_action_store()
    reset_run_store()
    configure_store(path=PROJECT_ROOT / "data" / "finance_action_records.json", persist=True)
    configure_run_store(path=PROJECT_ROOT / "data" / "finance_agent_runs.json", persist=True)


def _demo_orders() -> dict[str, dict]:
    with DEMO_BANK_CSV.open("rb") as handle:
        response = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    return {o["order_id"]: o for o in response.json()["order_results"]}


def _run_agent(orders: list[dict]) -> dict:
    return run_finance_controller_agent(orders, data_source="provided_order_results")


def _approve(order: dict, claimed: str | None = None, run_id: str | None = None):
    decision = decide_for_order(order)
    return client.post(
        "/api/v1/finance-controller/actions/approve",
        json={
            "order_id": order["order_id"],
            "agent_decision": claimed if claimed is not None else decision.decision,
            "order_result": order,
            "run_id": run_id,
        },
    )


def _reject(order: dict, claimed: str | None = None, run_id: str | None = None):
    decision = decide_for_order(order)
    return client.post(
        "/api/v1/finance-controller/actions/reject",
        json={
            "order_id": order["order_id"],
            "agent_decision": claimed if claimed is not None else decision.decision,
            "order_result": order,
            "run_id": run_id,
        },
    )


def test_approval_queue_exposes_pending_decisions():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    queue = client.get(
        "/api/v1/finance-controller/approval-queue",
        params={"run_id": run["run_id"]},
    )
    assert queue.status_code == 200
    body = queue.json()
    assert body["run_id"] == run["run_id"]
    assert body["pending_count"] >= 4
    assert len(body["items"]) >= 4
    item = next(i for i in body["items"] if i["order_id"] == "ORD_0002")
    for key in (
        "run_id",
        "order_id",
        "decision",
        "rationale",
        "proposed_action",
        "exceptions",
        "original_result",
        "requires_approval",
        "approval_status",
        "action_status",
        "timestamp",
    ):
        assert key in item
    assert item["decision"] == "FLAG_FOR_REVIEW"
    assert item["lifecycle_status"] == "PENDING"
    assert item["original_result"]["order_id"] == "ORD_0002"
    # NO_ACTION orders must not appear
    assert all(i["decision"] != "NO_ACTION" for i in body["items"])


def test_approve_and_reject_transitions():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    approve = _approve(orders["ORD_0002"], run_id=run["run_id"])
    assert approve.status_code == 200
    assert approve.json()["action_status"] == ACTION_RECORDED
    assert approve.json()["approval_status"] == APPROVAL_APPROVED
    assert approve.json()["money_moved"] is False

    reject = _reject(orders["ORD_0003"], run_id=run["run_id"])
    assert reject.status_code == 200
    assert reject.json()["action_status"] == ACTION_REJECTED
    assert reject.json()["approval_status"] == APPROVAL_REJECTED
    assert reject.json()["money_moved"] is False

    queue = get_approval_queue(run_id=run["run_id"])
    by_id = {i["order_id"]: i for i in queue["items"]}
    assert by_id["ORD_0002"]["lifecycle_status"] == "RECORDED"
    assert by_id["ORD_0003"]["lifecycle_status"] == "REJECTED"
    assert queue["pending_count"] == sum(
        1 for i in queue["items"] if i["lifecycle_status"] == "PENDING"
    )


def test_invalid_transitions():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    assert _approve(orders["ORD_0002"], run_id=run["run_id"]).status_code == 200
    # RECORDED → REJECTED forbidden
    bad_reject = _reject(orders["ORD_0002"], run_id=run["run_id"])
    assert bad_reject.status_code == 409

    assert _reject(orders["ORD_0003"], run_id=run["run_id"]).status_code == 200
    # REJECTED → APPROVED forbidden
    bad_approve = _approve(orders["ORD_0003"], run_id=run["run_id"])
    assert bad_approve.status_code == 409


def test_idempotency_approve_and_reject():
    orders = _demo_orders()
    first = _approve(orders["ORD_0002"])
    second = _approve(orders["ORD_0002"])
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert second.json()["action_id"] == first.json()["action_id"]

    r1 = _reject(orders["ORD_0003"])
    r2 = _reject(orders["ORD_0003"])
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["idempotent_replay"] is True
    assert r2.json()["action_id"] == r1.json()["action_id"]


def test_tampered_decision_rejected_on_reject_endpoint():
    orders = _demo_orders()
    response = _reject(orders["ORD_0002"], claimed="VERIFY_REFUND")
    assert response.status_code == 409


def test_no_action_cannot_be_approved_or_rejected():
    orders = _demo_orders()
    order = orders["ORD_0001"]
    assert decide_for_order(order).decision == "NO_ACTION"
    assert _approve(order).status_code == 400
    assert _reject(order).status_code == 400


def test_original_result_immutability_on_reject():
    orders = _demo_orders()
    order = orders["ORD_0002"]
    before = copy.deepcopy(order)
    response = _reject(order)
    assert response.status_code == 200
    assert response.json()["original_result_unchanged"] is True
    assert order == before


def test_audit_events_for_approve_and_reject():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    _approve(orders["ORD_0002"], run_id=run["run_id"])
    _reject(orders["ORD_0003"], run_id=run["run_id"])
    events = list_audit_events()
    assert len(events) >= 2
    recorded = next(e for e in events if e["event_type"] == "finance_action_recorded")
    rejected = next(e for e in events if e["event_type"] == "finance_action_rejected")
    for event in (recorded, rejected):
        assert event["money_moved"] is False
        assert event["run_id"] == run["run_id"]
        assert event["order_id"]
        assert event["decision"]
        assert event["proposed_action"]
        assert event["human_action"] in {"APPROVE", "REJECT"}
        assert event["previous_state"] == "PENDING"
        assert event["new_state"] in {ACTION_RECORDED, ACTION_REJECTED}
        assert event["timestamp"]


def test_lifecycle_and_run_history_metrics():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    _approve(orders["ORD_0002"], run_id=run["run_id"])
    _reject(orders["ORD_0003"], run_id=run["run_id"])

    life = client.get(
        "/api/v1/finance-controller/lifecycle",
        params={"run_id": run["run_id"]},
    )
    assert life.status_code == 200
    metrics = life.json()
    assert metrics["total_decisions"] == run["records_processed"]
    assert metrics["no_action"] == run["no_action_count"]
    assert metrics["approved"] >= 1
    assert metrics["recorded"] >= 1
    assert metrics["rejected"] >= 1
    assert metrics["pending_approval"] == get_lifecycle_metrics(run_id=run["run_id"])[
        "pending_approval"
    ]

    history = client.get("/api/v1/finance-controller/runs")
    assert history.status_code == 200
    runs = history.json()["runs"]
    assert runs
    row = next(r for r in runs if r["run_id"] == run["run_id"])
    for key in (
        "run_id",
        "timestamp",
        "records_processed",
        "no_action_count",
        "review_required_count",
        "pending_approval_count",
        "unresolved_count",
        "decisions_by_type",
        "completed_action_count",
        "approved_action_count",
        "rejected_action_count",
        "recorded_action_count",
        "pending_action_count",
    ):
        assert key in row
    assert row["approved_action_count"] >= 1
    assert row["rejected_action_count"] >= 1


def test_no_secret_leakage_in_ops_endpoints():
    orders = _demo_orders()
    run = _run_agent(list(orders.values()))
    _approve(orders["ORD_0002"], run_id=run["run_id"])
    payloads = [
        client.get("/api/v1/finance-controller/approval-queue", params={"run_id": run["run_id"]}).json(),
        client.get("/api/v1/finance-controller/lifecycle", params={"run_id": run["run_id"]}).json(),
        client.get("/api/v1/finance-controller/runs").json(),
        _reject(orders["ORD_0033"], run_id=run["run_id"]).json(),
    ]
    blob = json.dumps(payloads)
    for marker in SECRET_MARKERS:
        assert marker not in blob


def test_existing_approve_contract_still_works():
    orders = _demo_orders()
    response = _approve(orders["ORD_0002"])
    assert response.status_code == 200
    body = response.json()
    assert body["action_status"] == ACTION_RECORDED
    assert "audit_event" in body
    assert body["audit_event"]["event_type"] == "finance_action_recorded"

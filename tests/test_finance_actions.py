"""Tests for human-gated Finance Controller simulated actions."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_actions import (
    ACTION_RECORD_MISSING_BANK_ESCALATION,
    ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION,
    ACTION_RECORD_REFUND_VERIFICATION,
    ACTION_RECORD_REVIEW,
    ACTION_RECORDED,
    APPROVAL_APPROVED,
    DECISION_TO_ACTION,
    configure_store,
    list_audit_events,
    reset_action_store,
)
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
    run_finance_controller,
)
from finance_agent_eval import evaluate_finance_controller

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_BANK_CSV = PROJECT_ROOT / "data" / "demo_bank.csv"


def setup_function() -> None:
    configure_store(persist=False)
    reset_action_store()


def teardown_function() -> None:
    reset_action_store()
    configure_store(path=PROJECT_ROOT / "data" / "finance_action_records.json", persist=True)


def _demo_orders() -> dict[str, dict]:
    with DEMO_BANK_CSV.open("rb") as handle:
        response = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    return {o["order_id"]: o for o in response.json()["order_results"]}


def _approve(order: dict, claimed: str | None = None) -> object:
    decision = decide_for_order(order)
    return client.post(
        "/api/v1/finance-controller/actions/approve",
        json={
            "order_id": order["order_id"],
            "agent_decision": claimed if claimed is not None else decision.decision,
            "order_result": order,
        },
    )


def test_successful_approval_and_action_mapping():
    orders = _demo_orders()
    cases = [
        ("ORD_0002", DECISION_FLAG_FOR_REVIEW, ACTION_RECORD_REVIEW),
        ("ORD_0003", DECISION_ESCALATE_MISSING_BANK, ACTION_RECORD_MISSING_BANK_ESCALATION),
        ("ORD_0033", DECISION_VERIFY_REFUND, ACTION_RECORD_REFUND_VERIFICATION),
        ("ORD_0024", DECISION_ESCALATE_MISSING_SETTLEMENT, ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION),
    ]
    for order_id, expected_decision, expected_action in cases:
        reset_action_store()
        order = orders[order_id]
        assert decide_for_order(order).decision == expected_decision
        response = _approve(order)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["order_id"] == order_id
        assert body["agent_decision"] == expected_decision
        assert body["action_type"] == expected_action
        assert body["approval_status"] == APPROVAL_APPROVED
        assert body["action_status"] == ACTION_RECORDED
        assert body["action_id"]
        assert body["simulated"] is True
        assert body["money_moved"] is False
        assert body["original_result_unchanged"] is True
        assert "evidence" in body
        assert body["audit_event"]["event_type"] == "finance_action_recorded"


def test_decision_to_action_mapping_complete():
    assert DECISION_TO_ACTION[DECISION_FLAG_FOR_REVIEW] == ACTION_RECORD_REVIEW
    assert DECISION_TO_ACTION[DECISION_VERIFY_REFUND] == ACTION_RECORD_REFUND_VERIFICATION
    assert (
        DECISION_TO_ACTION[DECISION_ESCALATE_MISSING_BANK]
        == ACTION_RECORD_MISSING_BANK_ESCALATION
    )
    assert (
        DECISION_TO_ACTION[DECISION_ESCALATE_MISSING_SETTLEMENT]
        == ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION
    )
    assert DECISION_NO_ACTION not in DECISION_TO_ACTION


def test_no_action_rejection():
    orders = _demo_orders()
    order = orders["ORD_0001"]
    assert decide_for_order(order).decision == DECISION_NO_ACTION
    response = _approve(order)
    assert response.status_code == 400
    assert "NO_ACTION" in response.json()["detail"]


def test_mismatched_client_decision_rejection():
    orders = _demo_orders()
    order = orders["ORD_0002"]
    response = _approve(order, claimed=DECISION_VERIFY_REFUND)
    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]


def test_unknown_order_rejection():
    response = client.post(
        "/api/v1/finance-controller/actions/approve",
        json={
            "order_id": "ORD_DOES_NOT_EXIST",
            "agent_decision": DECISION_FLAG_FOR_REVIEW,
        },
    )
    assert response.status_code == 404


def test_idempotent_duplicate_approval():
    orders = _demo_orders()
    order = orders["ORD_0002"]
    first = _approve(order)
    assert first.status_code == 200
    first_body = first.json()
    second = _approve(order)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["action_id"] == first_body["action_id"]
    assert second_body["idempotent_replay"] is True
    assert second_body["action_status"] == ACTION_RECORDED


def test_original_result_immutability():
    orders = _demo_orders()
    order = copy.deepcopy(orders["ORD_0003"])
    before = copy.deepcopy(order)
    response = _approve(order)
    assert response.status_code == 200
    assert order == before
    assert response.json()["original_result_unchanged"] is True
    # Amounts / status / confidence untouched in evidence reference
    evidence = response.json()["evidence"]
    assert evidence["original_status"] == before["status"]
    assert evidence["original_reconciled"] == before["reconciled"]
    assert evidence["confidence_score"] == before["confidence_score"]
    assert evidence["amount_reference"]["order_amount_paise"] == before["order_amount_paise"]


def test_audit_event_creation_no_secrets():
    orders = _demo_orders()
    order = orders["ORD_0024"]
    response = _approve(order)
    assert response.status_code == 200
    events = list_audit_events()
    assert len(events) == 1
    event = events[0]
    assert event["order_id"] == "ORD_0024"
    assert event["agent_decision"] == DECISION_ESCALATE_MISSING_SETTLEMENT
    assert event["action_type"] == ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION
    assert event["approval_status"] == APPROVAL_APPROVED
    assert event["action_status"] == ACTION_RECORDED
    assert event["timestamp"]
    assert event["money_moved"] is False
    blob = json.dumps(event)
    for needle in ("GEMINI_API_KEY", "RAZORPAY_KEY_SECRET", "RAZORPAY_KEY_ID"):
        assert needle not in blob


def test_no_external_razorpay_call_on_approve(monkeypatch):
    orders = _demo_orders()
    order = orders["ORD_0002"]

    def boom(*_args, **_kwargs):
        raise AssertionError("Razorpay must not be called during action approval")

    monkeypatch.setattr("integrations.razorpay.client.RazorpayClient.request", boom, raising=False)
    # Approve path must not touch Razorpay regardless.
    response = _approve(order)
    assert response.status_code == 200
    assert response.json()["money_moved"] is False


def test_existing_hundred_batch_metrics():
    report = client.get("/api/v1/reconciliation/report").json()
    batch = run_finance_controller(report)
    assert batch.records_processed == 100
    assert batch.decisions_by_type["NO_ACTION"] == 40
    assert batch.decisions_by_type["FLAG_FOR_REVIEW"] == 32
    assert batch.decisions_by_type["ESCALATE_MISSING_BANK"] == 10
    assert batch.decisions_by_type["VERIFY_REFUND"] == 10
    assert batch.decisions_by_type["ESCALATE_MISSING_SETTLEMENT"] == 8


def test_held_out_evaluation_unchanged():
    result = evaluate_finance_controller()
    assert result["records_evaluated"] == 69
    assert result["accuracy"] == 1.0
    assert result["incorrect_decisions"] == 0

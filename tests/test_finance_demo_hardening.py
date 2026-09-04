"""Track 04 demo readiness / demo-reset hardening tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_actions import configure_store, reset_action_store

client = TestClient(app)
DEMO_BANK = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"
SECRET_MARKERS = ("GEMINI_API_KEY", "RAZORPAY_KEY", "password", "Authorization", "api_secret")


def setup_function() -> None:
    configure_store(persist=False)
    reset_action_store()


def teardown_function() -> None:
    reset_action_store()
    configure_store(persist=True)


def test_demo_status_ready_no_secrets():
    body = client.get("/api/v1/finance-controller/demo-status").json()
    assert body["ready"] is True
    assert body["checks"]["api_reachable"] is True
    assert body["checks"]["reconciliation_data_available"] is True
    assert body["checks"]["agent_endpoint_available"] is True
    assert body["checks"]["evaluation_endpoint_available"] is True
    assert body["operational_batch"]["records"] == 100
    assert body["held_out_evaluation"]["records_evaluated"] == 69
    assert body["money_moved"] is False
    assert body["gemini_in_decision_path"] is False
    assert body["secrets_exposed"] is False
    blob = json.dumps(body)
    for marker in SECRET_MARKERS:
        assert marker not in blob


def test_demo_reset_clears_actions_only():
    with DEMO_BANK.open("rb") as handle:
        demo = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        ).json()
    order = next(o for o in demo["order_results"] if o["order_id"] == "ORD_0002")
    first = client.post(
        "/api/v1/finance-controller/actions/approve",
        json={
            "order_id": "ORD_0002",
            "agent_decision": "FLAG_FOR_REVIEW",
            "order_result": order,
        },
    )
    assert first.status_code == 200
    assert first.json()["money_moved"] is False

    reset = client.post("/api/v1/finance-controller/demo-reset")
    assert reset.status_code == 200
    body = reset.json()
    assert body["reset"] is True
    assert body["datasets_untouched"] is True
    assert body["evaluation_untouched"] is True
    assert body["policy_untouched"] is True
    assert body["reconciliation_untouched"] is True
    assert body["money_moved"] is False
    assert body["secrets_exposed"] is False

    # After reset, approve is a fresh record (not only idempotent replay).
    second = client.post(
        "/api/v1/finance-controller/actions/approve",
        json={
            "order_id": "ORD_0002",
            "agent_decision": "FLAG_FOR_REVIEW",
            "order_result": order,
        },
    )
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is False
    assert second.json()["money_moved"] is False

    # Source datasets / eval unchanged.
    report = client.get("/api/v1/reconciliation/report").json()
    assert len(report["order_results"]) == 100
    eval_body = client.get("/api/v1/finance-controller/evaluation").json()
    assert eval_body["records_evaluated"] == 69
    assert eval_body["accuracy"] == 1.0

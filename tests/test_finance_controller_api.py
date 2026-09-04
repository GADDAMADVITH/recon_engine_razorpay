"""API integration tests for POST /api/v1/finance-controller/run."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
)

client = TestClient(app)
DEMO_BANK_CSV = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"
ENDPOINT = "/api/v1/finance-controller/run"


def _production_report() -> dict:
    return client.get("/api/v1/reconciliation/report").json()


def _demo_import_report() -> dict:
    with DEMO_BANK_CSV.open("rb") as handle:
        response = client.post(
            "/api/v1/reconciliation/import-bank",
            files={"file": ("demo_bank.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    return response.json()


def _find(orders: list[dict], order_id: str) -> dict:
    return next(o for o in orders if o["order_id"] == order_id)


def _metrics_from_decisions(decisions: list[dict]) -> dict:
    return {
        "records_processed": len(decisions),
        "no_action_count": sum(1 for d in decisions if d["decision"] == DECISION_NO_ACTION),
        "review_required_count": sum(1 for d in decisions if d["requires_approval"]),
        "exception_count": sum(1 for d in decisions if d["exception_types"]),
        "unresolved_count": sum(1 for d in decisions if d["decision"] != DECISION_NO_ACTION),
    }


def test_endpoint_returns_200():
    response = client.post(ENDPOINT)
    assert response.status_code == 200


def test_endpoint_processes_actual_fifty_plus_batch():
    response = client.post(ENDPOINT)
    body = response.json()
    report = _production_report()
    assert len(report["order_results"]) >= 50
    assert body["records_processed"] >= 50
    assert body["records_processed"] == len(report["order_results"])
    assert body["data_source"] == "production_reconciliation_report"


def test_records_processed_equals_batch_size():
    report = _production_report()
    response = client.post(ENDPOINT)
    body = response.json()
    assert body["records_processed"] == len(report["order_results"])


def test_decisions_length_equals_records_processed():
    body = client.post(ENDPOINT).json()
    assert len(body["decisions"]) == body["records_processed"]


def test_batch_metrics_equal_values_calculated_from_decisions():
    body = client.post(ENDPOINT).json()
    expected = _metrics_from_decisions(body["decisions"])
    for key, value in expected.items():
        assert body[key] == value
    assert sum(body["decisions_by_type"].values()) == body["records_processed"]


def test_demo_scenarios_via_bank_import_order_results():
    """Demo CSV scenarios: ORD_0002 mismatch, ORD_0003 missing bank, etc.

    Production report ORD_0002/ORD_0003 are reconciled — do not assert demo
    outcomes against the empty-body production run.
    """
    demo = _demo_import_report()
    subset = [
        _find(demo["order_results"], oid)
        for oid in ("ORD_0001", "ORD_0002", "ORD_0003", "ORD_0033", "ORD_0024")
    ]
    response = client.post(ENDPOINT, json={"order_results": subset})
    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "provided_order_results"
    assert body["records_processed"] == 5
    by_id = {d["order_id"]: d for d in body["decisions"]}

    assert by_id["ORD_0001"]["decision"] == DECISION_NO_ACTION
    assert by_id["ORD_0001"]["requires_approval"] is False

    assert by_id["ORD_0002"]["decision"] == DECISION_FLAG_FOR_REVIEW
    assert by_id["ORD_0002"]["requires_approval"] is True
    assert "BANK_AMOUNT_MISMATCH" in by_id["ORD_0002"]["exception_types"]

    assert by_id["ORD_0003"]["decision"] == DECISION_ESCALATE_MISSING_BANK
    assert by_id["ORD_0003"]["requires_approval"] is True

    assert by_id["ORD_0033"]["decision"] == DECISION_VERIFY_REFUND
    assert by_id["ORD_0033"]["requires_approval"] is True

    assert by_id["ORD_0024"]["decision"] == DECISION_ESCALATE_MISSING_SETTLEMENT
    assert by_id["ORD_0024"]["requires_approval"] is True


def test_production_batch_known_orders():
    """Document actual production outcomes for the shared order IDs."""
    body = client.post(ENDPOINT).json()
    by_id = {d["order_id"]: d for d in body["decisions"]}

    assert by_id["ORD_0001"]["decision"] == DECISION_NO_ACTION
    # Production CSV: ORD_0002/ORD_0003 are reconciled (not the demo mismatch cases).
    assert by_id["ORD_0002"]["original_reconciled"] is True
    assert by_id["ORD_0002"]["decision"] == DECISION_NO_ACTION
    assert by_id["ORD_0003"]["original_reconciled"] is True
    assert by_id["ORD_0003"]["decision"] == DECISION_NO_ACTION
    assert by_id["ORD_0033"]["decision"] == DECISION_VERIFY_REFUND
    assert by_id["ORD_0024"]["decision"] == DECISION_ESCALATE_MISSING_SETTLEMENT


def test_every_non_no_action_requires_approval():
    body = client.post(ENDPOINT).json()
    for decision in body["decisions"]:
        if decision["decision"] == DECISION_NO_ACTION:
            assert decision["requires_approval"] is False
            assert decision["agent_decision"]["requires_approval"] is False
        else:
            assert decision["requires_approval"] is True
            assert decision["agent_decision"]["requires_approval"] is True


def test_unknown_exception_safe_fallback_via_payload():
    base = _find(_production_report()["order_results"], "ORD_0001")
    mutated = copy.deepcopy(base)
    mutated["reconciled"] = False
    mutated["status"] = "unreconciled_settlement_amount"
    mutated["exceptions"] = [{"type": "TOTALLY_UNKNOWN_EXCEPTION", "message": "test"}]
    response = client.post(ENDPOINT, json={"order_results": [mutated]})
    assert response.status_code == 200
    decision = response.json()["decisions"][0]
    assert decision["decision"] == DECISION_FLAG_FOR_REVIEW
    assert decision["requires_approval"] is True


def test_original_reconciliation_facts_unchanged():
    before = _production_report()
    before_map = {o["order_id"]: copy.deepcopy(o) for o in before["order_results"]}
    client.post(ENDPOINT)
    after = _production_report()
    for order in after["order_results"]:
        original = before_map[order["order_id"]]
        assert order["status"] == original["status"]
        assert order["reconciled"] == original["reconciled"]
        assert order["confidence_score"] == original["confidence_score"]
        assert order["order_amount_paise"] == original["order_amount_paise"]
        assert order["amount_comparison"] == original["amount_comparison"]


def test_amounts_not_modified_by_agent_decisions():
    demo = _demo_import_report()
    order = _find(demo["order_results"], "ORD_0002")
    amount_before = copy.deepcopy(order["amount_comparison"])
    response = client.post(ENDPOINT, json={"order_results": [order]})
    decision = response.json()["decisions"][0]
    assert order["amount_comparison"] == amount_before
    assert decision["original_result"]["confidence_score"] == order["confidence_score"]
    # Evidence mirrors engine amounts; decision does not invent replacements.
    evidence_amount = decision["evidence"]["amount_summary"]["bank_amount_paise"]
    assert evidence_amount == order["amount_comparison"]["bank_amount_paise"]


def test_confidence_not_modified_by_agent_decisions():
    order = _find(_production_report()["order_results"], "ORD_0001")
    score = order["confidence_score"]
    response = client.post(ENDPOINT, json={"order_results": [order]})
    decision = response.json()["decisions"][0]
    assert order["confidence_score"] == score
    assert decision["confidence_score"] == score
    assert decision["original_result"]["confidence_score"] == score


def test_original_vs_agent_decision_envelope():
    body = client.post(ENDPOINT).json()
    decision = body["decisions"][0]
    assert "original_result" in decision
    assert "agent_decision" in decision
    assert decision["original_result"]["status"] == decision["original_status"]
    assert decision["agent_decision"]["decision"] == decision["decision"]


def test_no_secret_leakage():
    response = client.post(ENDPOINT)
    text = response.text
    assert "GEMINI_API_KEY" not in text
    assert "RAZORPAY_KEY_SECRET" not in text
    assert "AIza" not in text
    assert "sk_live_" not in text
    blob = json.dumps(response.json())
    assert "GEMINI_API_KEY" not in blob


def test_existing_reconciliation_endpoints_remain_unchanged():
    report_before = client.get("/api/v1/reconciliation/report")
    assert report_before.status_code == 200
    summary_before = client.get("/api/v1/reconciliation/summary")
    assert summary_before.status_code == 200

    fc = client.post(ENDPOINT)
    assert fc.status_code == 200

    report_after = client.get("/api/v1/reconciliation/report")
    assert report_after.status_code == 200
    assert report_after.json()["summary"] == report_before.json()["summary"]

    audit = client.get("/api/v1/reconciliation/ORD_0001/audit")
    assert audit.status_code == 200
    assert audit.json()["order_id"] == "ORD_0001"

    # Chat and explain contracts still exist (shape smoke only; Gemini may be mocked elsewhere).
    chat_paths_ok = any(
        getattr(route, "path", "").endswith("/chat") for route in app.routes
    )
    assert chat_paths_ok
    explain_paths_ok = any(
        "/audit/explain" in getattr(route, "path", "") for route in app.routes
    )
    assert explain_paths_ok

"""Tests for the ReconEngine Finance Controller Agent."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_agent import (
    ALLOWED_DECISIONS,
    APPROVAL_REQUIRED_DECISIONS,
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
    run_finance_controller,
)

client = TestClient(app)
DEMO_BANK_CSV = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"


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


def test_batch_processes_fifty_plus_records():
    report = _production_report()
    assert len(report["order_results"]) >= 100
    batch = run_finance_controller(report)
    assert batch.records_processed == len(report["order_results"])
    assert batch.records_processed >= 100
    assert len(batch.decisions) == batch.records_processed


def test_reconciled_order_no_action():
    # Production ORD_0001 is reconciled (timestamp-within-tolerance variant).
    order = _find(_production_report()["order_results"], "ORD_0001")
    assert order["reconciled"] is True
    decision = decide_for_order(order)
    assert decision.decision == DECISION_NO_ACTION
    assert decision.requires_approval is False
    assert decision.original_status == order["status"]
    assert decision.original_reconciled is True


def test_amount_mismatch_flag_for_review():
    # Demo bank CSV: ORD_0002 has BANK_AMOUNT_MISMATCH.
    order = _find(_demo_import_report()["order_results"], "ORD_0002")
    assert order["reconciled"] is False
    assert any(e["type"] == "BANK_AMOUNT_MISMATCH" for e in order["exceptions"])
    decision = decide_for_order(order)
    assert decision.decision == DECISION_FLAG_FOR_REVIEW
    assert decision.requires_approval is True
    assert decision.original_reconciled is False
    assert "BANK_AMOUNT_MISMATCH" in decision.exception_types


def test_missing_bank_escalate():
    order = _find(_demo_import_report()["order_results"], "ORD_0003")
    assert any(e["type"] == "MISSING_BANK_TRANSACTION" for e in order["exceptions"])
    decision = decide_for_order(order)
    assert decision.decision == DECISION_ESCALATE_MISSING_BANK
    assert decision.requires_approval is True


def test_refund_adjusted_verify_refund():
    order = _find(_demo_import_report()["order_results"], "ORD_0033")
    assert any(e["type"] == "REFUND_ADJUSTED" for e in order["exceptions"])
    decision = decide_for_order(order)
    assert decision.decision == DECISION_VERIFY_REFUND
    assert decision.requires_approval is True
    assert decision.action == DECISION_VERIFY_REFUND


def test_missing_settlement_escalate():
    order = _find(_demo_import_report()["order_results"], "ORD_0024")
    assert any(e["type"] == "MISSING_SETTLEMENT" for e in order["exceptions"])
    decision = decide_for_order(order)
    assert decision.decision == DECISION_ESCALATE_MISSING_SETTLEMENT
    assert decision.requires_approval is True


def test_unknown_exception_safe_fallback():
    base = _find(_production_report()["order_results"], "ORD_0001")
    mutated = copy.deepcopy(base)
    mutated["reconciled"] = False
    mutated["status"] = "unreconciled_settlement_amount"
    mutated["exceptions"] = [
        {"type": "TOTALLY_UNKNOWN_EXCEPTION", "message": "invented for test"},
    ]
    decision = decide_for_order(mutated)
    assert decision.decision == DECISION_FLAG_FOR_REVIEW
    assert decision.requires_approval is True


def test_agent_never_changes_original_reconciliation_status():
    report = _demo_import_report()
    before = {o["order_id"]: copy.deepcopy(o) for o in report["order_results"]}
    batch = run_finance_controller(report)
    after = {o["order_id"]: o for o in report["order_results"]}
    for order_id, original in before.items():
        assert after[order_id]["status"] == original["status"]
        assert after[order_id]["reconciled"] == original["reconciled"]
        decision = next(d for d in batch.decisions if d.order_id == order_id)
        assert decision.original_status == original["status"]
        assert decision.original_reconciled == original["reconciled"]


def test_agent_never_changes_original_amounts():
    order = _find(_demo_import_report()["order_results"], "ORD_0002")
    snapshot = copy.deepcopy(order["amount_comparison"])
    order_amount = order["order_amount_paise"]
    decide_for_order(order)
    assert order["amount_comparison"] == snapshot
    assert order["order_amount_paise"] == order_amount


def test_agent_never_changes_original_confidence_score():
    order = _find(_production_report()["order_results"], "ORD_0001")
    score = order["confidence_score"]
    decision = decide_for_order(order)
    assert order["confidence_score"] == score
    assert decision.confidence_score == score


def test_every_decision_has_evidence():
    batch = run_finance_controller(_production_report())
    for decision in batch.decisions:
        assert isinstance(decision.evidence, dict)
        assert "status" in decision.evidence
        assert "reconciled" in decision.evidence
        assert "exception_types" in decision.evidence
        assert "amount_summary" in decision.evidence
        assert decision.reason
        assert decision.decision in ALLOWED_DECISIONS


def test_every_unsafe_action_requires_approval():
    batch = run_finance_controller(_demo_import_report())
    for decision in batch.decisions:
        if decision.decision == DECISION_NO_ACTION:
            assert decision.requires_approval is False
        else:
            assert decision.decision in APPROVAL_REQUIRED_DECISIONS
            assert decision.requires_approval is True


def test_decision_allowlist_enforced():
    # Guardrail: even if policy internals were bypassed, allowlist clamps.
    from finance_agent import _enforce_allowlist

    assert _enforce_allowlist("AUTO_REFUND_MONEY") == DECISION_FLAG_FOR_REVIEW
    assert _enforce_allowlist(DECISION_NO_ACTION) == DECISION_NO_ACTION
    for decision in ALLOWED_DECISIONS:
        assert _enforce_allowlist(decision) == decision


def test_batch_metrics_calculated_from_actual_results():
    report = _production_report()
    batch = run_finance_controller(report)
    assert batch.records_processed == len(batch.decisions)
    assert batch.no_action_count == sum(
        1 for d in batch.decisions if d.decision == DECISION_NO_ACTION
    )
    assert batch.review_required_count == sum(1 for d in batch.decisions if d.requires_approval)
    assert batch.exception_count == sum(1 for d in batch.decisions if d.exception_types)
    assert batch.unresolved_count == sum(
        1 for d in batch.decisions if d.decision != DECISION_NO_ACTION
    )
    assert sum(batch.decisions_by_type.values()) == batch.records_processed
    for key in ALLOWED_DECISIONS:
        assert key in batch.decisions_by_type


def test_no_api_key_or_secret_leakage():
    batch = run_finance_controller(_production_report())
    serialized = json.dumps(batch.to_dict())
    assert "GEMINI_API_KEY" not in serialized
    assert "RAZORPAY_KEY_SECRET" not in serialized
    assert "AIza" not in serialized
    assert "sk_live_" not in serialized
    assert "sk_test_" not in serialized


def test_finance_controller_api_endpoint():
    response = client.post("/api/v1/finance-controller/run")
    assert response.status_code == 200
    body = response.json()
    assert body["records_processed"] >= 100
    assert "decisions" in body
    assert "decisions_by_type" in body
    assert body["data_source"] == "production_reconciliation_report"
    assert "original_result" in body["decisions"][0]
    assert "agent_decision" in body["decisions"][0]
    assert "GEMINI_API_KEY" not in response.text
    # Endpoint must not mutate the reconciliation report.
    report = _production_report()
    first = report["order_results"][0]
    assert "status" in first
    assert "reconciled" in first


def test_finance_controller_api_accepts_order_results_payload():
    demo = _demo_import_report()
    subset = [
        _find(demo["order_results"], "ORD_0001"),
        _find(demo["order_results"], "ORD_0002"),
        _find(demo["order_results"], "ORD_0003"),
        _find(demo["order_results"], "ORD_0033"),
        _find(demo["order_results"], "ORD_0024"),
    ]
    response = client.post(
        "/api/v1/finance-controller/run",
        json={"order_results": subset},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["records_processed"] == 5
    assert body["data_source"] == "provided_order_results"
    by_id = {d["order_id"]: d for d in body["decisions"]}
    assert by_id["ORD_0001"]["decision"] == DECISION_NO_ACTION
    assert by_id["ORD_0002"]["decision"] == DECISION_FLAG_FOR_REVIEW
    assert by_id["ORD_0003"]["decision"] == DECISION_ESCALATE_MISSING_BANK
    assert by_id["ORD_0033"]["decision"] == DECISION_VERIFY_REFUND
    assert by_id["ORD_0024"]["decision"] == DECISION_ESCALATE_MISSING_SETTLEMENT

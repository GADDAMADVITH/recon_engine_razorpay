"""Tests for Finance Controller Agent Run / Decision Trace layer."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from finance_actions import DECISION_TO_ACTION
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
    run_finance_controller,
)
from finance_agent_run import (
    build_decision_trace,
    build_deterministic_rationale,
    configure_run_store,
    get_latest_agent_run,
    proposed_action_for_decision,
    reset_run_store,
    run_finance_controller_agent,
)

client = TestClient(app)
DEMO_BANK_CSV = Path(__file__).resolve().parents[1] / "data" / "demo_bank.csv"
ENDPOINT = "/api/v1/finance-controller/run-agent"
LEGACY_ENDPOINT = "/api/v1/finance-controller/run"

SECRET_MARKERS = (
    "RAZORPAY_KEY",
    "api_key",
    "secret",
    "password",
    "Authorization",
    "GEMINI_API_KEY",
)


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


def setup_function() -> None:
    configure_run_store(persist=False)
    reset_run_store()


def test_production_batch_fifty_records_run_metrics():
    report = _production_report()
    assert len(report["order_results"]) >= 100
    run = run_finance_controller_agent(report)
    assert run["records_processed"] == len(report["order_results"])
    assert run["records_processed"] >= 100
    assert len(run["decisions"]) == run["records_processed"]
    assert run["no_action_count"] == 40
    assert run["review_required_count"] == 60
    assert run["unresolved_count"] == 60
    assert run["pending_approval_count"] == 60
    assert run["decisions_by_type"][DECISION_NO_ACTION] == 40
    assert run["decisions_by_type"][DECISION_FLAG_FOR_REVIEW] == 32
    assert run["decisions_by_type"][DECISION_ESCALATE_MISSING_BANK] == 10
    assert run["decisions_by_type"][DECISION_VERIFY_REFUND] == 10
    assert run["decisions_by_type"][DECISION_ESCALATE_MISSING_SETTLEMENT] == 8
    assert isinstance(run["run_id"], str) and run["run_id"].startswith("FCRUN_")
    assert isinstance(run["elapsed_seconds"], float)
    assert run["elapsed_seconds"] >= 0
    assert run["started_at"]
    assert run["completed_at"]


def test_demo_batch_all_five_decision_types():
    report = _demo_import_report()
    run = run_finance_controller_agent(report, data_source="provided_order_results")
    types = set(run["decisions_by_type"])
    for expected in (
        DECISION_NO_ACTION,
        DECISION_FLAG_FOR_REVIEW,
        DECISION_VERIFY_REFUND,
        DECISION_ESCALATE_MISSING_BANK,
        DECISION_ESCALATE_MISSING_SETTLEMENT,
    ):
        assert expected in types
        assert run["decisions_by_type"][expected] >= 1

    by_id = {d["order_id"]: d for d in run["decisions"]}
    assert by_id["ORD_0001"]["decision"] == DECISION_NO_ACTION
    assert by_id["ORD_0002"]["decision"] == DECISION_FLAG_FOR_REVIEW
    assert by_id["ORD_0003"]["decision"] == DECISION_ESCALATE_MISSING_BANK
    assert by_id["ORD_0033"]["decision"] == DECISION_VERIFY_REFUND
    assert by_id["ORD_0024"]["decision"] == DECISION_ESCALATE_MISSING_SETTLEMENT


def test_decision_trace_fields_and_rationale():
    order = _find(_demo_import_report()["order_results"], "ORD_0002")
    trace = build_decision_trace(order)
    for key in (
        "order_id",
        "original_result",
        "audit_evidence_summary",
        "triggered_exceptions",
        "decision",
        "rationale",
        "requires_approval",
        "proposed_action",
        "timestamp",
    ):
        assert key in trace
    assert trace["decision"] == DECISION_FLAG_FOR_REVIEW
    assert "Amount mismatch" in trace["rationale"]
    assert "BANK_AMOUNT_MISMATCH" in trace["triggered_exceptions"]
    assert trace["requires_approval"] is True
    assert trace["proposed_action"] == DECISION_TO_ACTION[DECISION_FLAG_FOR_REVIEW]


def test_rationale_examples_by_decision_type():
    demo = _demo_import_report()["order_results"]
    cases = {
        "ORD_0001": (
            DECISION_NO_ACTION,
            "Reconciliation is successful and no blocking exception requires intervention.",
        ),
        "ORD_0002": (
            DECISION_FLAG_FOR_REVIEW,
            "Amount mismatch detected; financial result requires human review.",
        ),
        "ORD_0033": (
            DECISION_VERIFY_REFUND,
            "Refund-adjusted exception detected; refund state requires verification.",
        ),
        "ORD_0003": (
            DECISION_ESCALATE_MISSING_BANK,
            "Bank transaction is missing; escalation is required.",
        ),
        "ORD_0024": (
            DECISION_ESCALATE_MISSING_SETTLEMENT,
            "Settlement is missing; escalation is required.",
        ),
    }
    for order_id, (decision, rationale) in cases.items():
        order = _find(demo, order_id)
        trace = build_decision_trace(order)
        assert trace["decision"] == decision
        assert trace["rationale"].startswith(rationale)


def test_proposed_action_mapping_reuses_finance_actions():
    assert proposed_action_for_decision(DECISION_NO_ACTION) is None
    assert proposed_action_for_decision(DECISION_FLAG_FOR_REVIEW) == "RECORD_REVIEW"
    assert proposed_action_for_decision(DECISION_VERIFY_REFUND) == "RECORD_REFUND_VERIFICATION"
    assert (
        proposed_action_for_decision(DECISION_ESCALATE_MISSING_BANK)
        == "RECORD_MISSING_BANK_ESCALATION"
    )
    assert (
        proposed_action_for_decision(DECISION_ESCALATE_MISSING_SETTLEMENT)
        == "RECORD_MISSING_SETTLEMENT_ESCALATION"
    )
    for decision, action in DECISION_TO_ACTION.items():
        assert proposed_action_for_decision(decision) == action


def test_approval_requirement_on_traces():
    run = run_finance_controller_agent(_demo_import_report())
    for trace in run["decisions"]:
        if trace["decision"] == DECISION_NO_ACTION:
            assert trace["requires_approval"] is False
            assert trace["proposed_action"] is None
        else:
            assert trace["requires_approval"] is True
            assert trace["proposed_action"] in DECISION_TO_ACTION.values()
    assert run["pending_approval_count"] == sum(
        1 for t in run["decisions"] if t["requires_approval"]
    )


def test_original_result_immutability():
    order = _find(_demo_import_report()["order_results"], "ORD_0002")
    before = copy.deepcopy(order)
    trace = build_decision_trace(order)
    assert order == before
    # Mutating the returned original_result must not affect the input order.
    trace["original_result"]["status"] = "MUTATED"
    assert order["status"] == before["status"]
    assert order["reconciled"] == before["reconciled"]
    assert order["confidence_score"] == before["confidence_score"]


def test_unknown_exception_fallback_flag_for_review():
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
    assert decision.decision == DECISION_FLAG_FOR_REVIEW
    trace = build_decision_trace(synthetic)
    assert trace["decision"] == DECISION_FLAG_FOR_REVIEW
    assert "TOTALLY_UNKNOWN_EXCEPTION" in trace["rationale"]
    assert trace["requires_approval"] is True
    assert trace["proposed_action"] == "RECORD_REVIEW"


def test_empty_and_missing_input_behavior():
    empty = run_finance_controller_agent([])
    assert empty["records_processed"] == 0
    assert empty["decisions"] == []
    assert empty["no_action_count"] == 0
    assert empty["pending_approval_count"] == 0

    none_run = run_finance_controller_agent(None)
    assert none_run["records_processed"] == 0
    assert none_run["decisions"] == []


def test_run_store_latest_and_deepcopy_isolation(tmp_path: Path):
    configure_run_store(path=tmp_path / "runs.json", persist=True)
    reset_run_store()
    run = run_finance_controller_agent([_find(_production_report()["order_results"], "ORD_0001")])
    latest = get_latest_agent_run()
    assert latest is not None
    assert latest["run_id"] == run["run_id"]
    latest["decisions"][0]["decision"] = "MUTATED"
    again = get_latest_agent_run()
    assert again["decisions"][0]["decision"] == DECISION_NO_ACTION


def test_agent_run_matches_legacy_policy_counts():
    report = _production_report()
    legacy = run_finance_controller(report)
    agent = run_finance_controller_agent(report)
    assert agent["records_processed"] == legacy.records_processed
    assert agent["no_action_count"] == legacy.no_action_count
    assert agent["review_required_count"] == legacy.review_required_count
    assert agent["unresolved_count"] == legacy.unresolved_count
    assert agent["decisions_by_type"] == dict(legacy.decisions_by_type)
    legacy_by_id = {d.order_id: d.decision for d in legacy.decisions}
    for trace in agent["decisions"]:
        assert trace["decision"] == legacy_by_id[trace["order_id"]]


def test_api_run_agent_contract_production():
    response = client.post(ENDPOINT)
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "run_id",
        "records_processed",
        "no_action_count",
        "review_required_count",
        "unresolved_count",
        "pending_approval_count",
        "decisions_by_type",
        "elapsed_seconds",
        "decisions",
    ):
        assert key in payload
    assert payload["records_processed"] >= 100
    assert payload["data_source"] == "production_reconciliation_report"
    blob = json.dumps(payload)
    for marker in SECRET_MARKERS:
        assert marker not in blob


def test_api_run_agent_accepts_order_results():
    demo = _demo_import_report()
    response = client.post(ENDPOINT, json={"order_results": demo["order_results"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"] == "provided_order_results"
    assert payload["records_processed"] == len(demo["order_results"])
    assert all("rationale" in d for d in payload["decisions"])
    assert all("proposed_action" in d for d in payload["decisions"])


def test_legacy_run_endpoint_unchanged():
    legacy = client.post(LEGACY_ENDPOINT)
    agent = client.post(ENDPOINT)
    assert legacy.status_code == 200
    assert agent.status_code == 200
    lj, aj = legacy.json(), agent.json()
    assert lj["records_processed"] == aj["records_processed"]
    assert lj["decisions_by_type"] == aj["decisions_by_type"]
    assert "run_id" not in lj
    assert "run_id" in aj


def test_no_secret_leakage_in_traces():
    run = run_finance_controller_agent(_production_report())
    blob = json.dumps(run).lower()
    for marker in ("razorpay_key", "gemini_api_key", "password", "authorization"):
        assert marker not in blob


def test_deterministic_rationale_from_decision_object():
    order = _find(_demo_import_report()["order_results"], "ORD_0003")
    decision = decide_for_order(order)
    text = build_deterministic_rationale(decision)
    assert text == "Bank transaction is missing; escalation is required."

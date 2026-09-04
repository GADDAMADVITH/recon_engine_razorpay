"""Phase 4A demo fixture and reconcile-demo tests (no live Razorpay HTTP)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import api
from api import app
from integrations.razorpay.adapter import BANK_TRANSACTIONS_NOT_SUPPORTED
from integrations.razorpay.demo_fixtures import (
    DEMO_BANK_SOURCE,
    DEMO_DATA_SOURCE,
    build_demo_reconciliation_input,
    build_demo_scenarios,
    scenario_expectations,
)

client = TestClient(app)


def test_demo_scenarios_cover_four_required_cases() -> None:
    scenarios = build_demo_scenarios()
    ids = {s.scenario_id for s in scenarios}
    assert ids == {
        "successful_reconciliation",
        "bank_amount_mismatch",
        "missing_settlement",
        "refund_adjusted",
    }


def test_demo_bank_fixtures_are_not_from_razorpay_utr() -> None:
    demo = build_demo_reconciliation_input()
    assert demo.bank_source == DEMO_BANK_SOURCE
    assert "settlement_utr" not in demo.bank_source_note.lower() or "not derived" in demo.bank_source_note
    assert "not derived from settlement_utr" in demo.bank_source_note
    for bank in demo.bank_transactions:
        assert "SYNTHETIC_BANK_FIXTURE" in bank.description
        assert bank.resolved_settlement_id is not None
        assert bank.settlement_ref.startswith("setl_")


def test_demo_missing_settlement_has_no_bank_or_settlement() -> None:
    missing = next(s for s in build_demo_scenarios() if s.scenario_id == "missing_settlement")
    assert missing.settlements == ()
    assert missing.bank_rows == ()


def test_run_razorpay_reconcile_demo_matches_expectations() -> None:
    payload = api.run_razorpay_reconcile_demo()
    assert payload["source"] == DEMO_DATA_SOURCE
    assert payload["bank_source"] == DEMO_BANK_SOURCE
    assert payload["status"] == "success"
    assert payload["scenario_count"] == 4

    recon = payload["reconciliation"]
    assert recon["metadata"]["data_source"] == "razorpay"
    assert recon["metadata"]["bank_source"] == DEMO_BANK_SOURCE
    assert recon["summary"]["total_orders"] == 4

    by_id = {s["scenario_id"]: s for s in payload["scenarios"]}
    assert by_id["successful_reconciliation"]["matched_expectation"] is True
    assert by_id["successful_reconciliation"]["actual_status"] == "reconciled"
    assert by_id["successful_reconciliation"]["actual_reconciled"] is True

    assert by_id["bank_amount_mismatch"]["matched_expectation"] is True
    assert by_id["bank_amount_mismatch"]["actual_status"] == "unreconciled_settlement_amount"
    assert by_id["bank_amount_mismatch"]["actual_reconciled"] is False

    assert by_id["missing_settlement"]["matched_expectation"] is True
    assert by_id["missing_settlement"]["actual_status"] == "unreconciled_missing_settlement"
    assert by_id["missing_settlement"]["actual_reconciled"] is False

    assert by_id["refund_adjusted"]["matched_expectation"] is True
    assert by_id["refund_adjusted"]["actual_status"] == "reconciled_with_refund_adjustment"
    assert by_id["refund_adjusted"]["actual_reconciled"] is True


def test_demo_bank_amount_mismatch_raises_bank_exception() -> None:
    payload = api.run_razorpay_reconcile_demo()
    order = next(
        r
        for r in payload["reconciliation"]["order_results"]
        if r["order_id"] == "order_demo_bank_mismatch"
    )
    types = {exc["type"] for exc in order["exceptions"]}
    assert "BANK_AMOUNT_MISMATCH" in types


def test_demo_missing_settlement_exception() -> None:
    payload = api.run_razorpay_reconcile_demo()
    order = next(
        r
        for r in payload["reconciliation"]["order_results"]
        if r["order_id"] == "order_demo_missing_settlement"
    )
    types = {exc["type"] for exc in order["exceptions"]}
    assert "MISSING_SETTLEMENT" in types
    assert order["valid_bank_transaction_id"] is None


def test_demo_refund_adjusted_exception_present() -> None:
    payload = api.run_razorpay_reconcile_demo()
    order = next(
        r
        for r in payload["reconciliation"]["order_results"]
        if r["order_id"] == "order_demo_refund_adjusted"
    )
    types = {exc["type"] for exc in order["exceptions"]}
    assert "REFUND_ADJUSTED" in types


def test_demo_does_not_fabricate_banks_from_adapter_constant() -> None:
    assert "NormalizedBankTransaction" in BANK_TRANSACTIONS_NOT_SUPPORTED


def test_reconcile_demo_api_endpoint() -> None:
    response = client.post("/api/v1/sources/razorpay/reconcile-demo")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "razorpay"
    assert body["bank_source"] == "synthetic_fixture"
    assert all(s["matched_expectation"] for s in body["scenarios"])
    assert "RAZORPAY_KEY_SECRET" not in response.text
    assert "key_secret" not in response.text.lower()


def test_csv_report_unaffected_by_demo() -> None:
    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 200
    report = response.json()
    assert report["metadata"]["data_source"] == "csv"
    assert len(report["order_results"]) == 100
    assert "bank_source" not in report["metadata"]


def test_scenario_expectations_align_with_bundles() -> None:
    expectations = {e["order_id"]: e for e in scenario_expectations()}
    for scenario in build_demo_scenarios():
        assert expectations[scenario.order.order_id]["expected_status"] == scenario.expected_status

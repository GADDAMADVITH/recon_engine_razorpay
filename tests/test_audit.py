"""Tests for the audit trail feature — structured audit from engine output."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api
from api import app
from audit import build_structured_audit
from tests.conftest import (
    DT_BASE,
    compute_settlement_amounts,
    make_bank_tx,
    make_order,
    make_refund,
    make_settlement,
    reconcile_single,
)

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────

def _reconcile_and_audit(**kwargs: Any) -> dict[str, Any]:
    """Run reconcile_single, serialise the result, then build_structured_audit."""
    result = reconcile_single(**kwargs)
    order_dict = {
        "order_id": result.order_id,
        "status": result.status,
        "reconciled": result.reconciled,
        "confidence_score": result.confidence_score,
        "order_amount_paise": result.order_amount_paise,
        "settlement_ids_considered": result.settlement_ids_considered,
        "primary_settlement_id": result.primary_settlement_id,
        "secondary_settlement_ids": result.secondary_settlement_ids,
        "refund_ids": result.refund_ids,
        "total_refund_paise": result.total_refund_paise,
        "bank_transaction_ids_considered": result.bank_transaction_ids_considered,
        "valid_bank_transaction_id": result.valid_bank_transaction_id,
        "normalized_references": result.normalized_references,
        "amount_comparison": result.amount_comparison,
        "timestamp_comparison": result.timestamp_comparison,
        "rules_triggered": result.rules_triggered,
        "exceptions": result.exceptions,
        "audit_trail": result.audit_trail,
    }
    return build_structured_audit(order_dict)


def _clean_chain():
    gross = 100_000
    fee, tax, net = compute_settlement_amounts(gross)
    settled = DT_BASE + timedelta(hours=1)
    order = make_order(amount_paise=gross)
    settlement = make_settlement(gross_amount_paise=gross, settled_at=settled)
    bank = make_bank_tx(amount_paise=net, transaction_date=settled)
    return order, [settlement], [], [bank]


# ── Scenario 1: successful reconciliation ────────────────

class TestSuccessfulReconciliation:
    def test_audit_status_reconciled(self):
        order, settlements, refunds, banks = _clean_chain()
        audit = _reconcile_and_audit(
            order=order,
            settlements=settlements,
            refunds=refunds,
            bank_transactions=banks,
        )
        assert audit["order_id"] == "ORD_0001"
        assert audit["status"] == "reconciled"
        assert audit["reconciled"] is True
        assert audit["confidence_score"] == 100

    def test_audit_checks_all_pass(self):
        order, settlements, refunds, banks = _clean_chain()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        for check in audit["checks"]:
            assert check["passed"] is True, f"Check {check['rule']} should pass"
            assert check["exception"] is None

    def test_audit_has_timeline(self):
        order, settlements, refunds, banks = _clean_chain()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        assert len(audit["timeline"]) >= 2
        assert any("reconciled" in entry.lower() for entry in audit["timeline"])

    def test_audit_has_references(self):
        order, settlements, refunds, banks = _clean_chain()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        refs = audit["references"]
        assert refs["primary_settlement_id"] == "SET_0001"
        assert refs["valid_bank_transaction_id"] == "BNK_0001"

    def test_audit_amount_summary(self):
        order, settlements, refunds, banks = _clean_chain()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        amt = audit["amount_summary"]
        assert amt["order_amount_paise"] == 100_000
        assert amt["settlement_gross_matches_order"] is True
        assert amt["bank_matches_settlement_net"] is True


# ── Scenario 2: bank amount mismatch ────────────────────

class TestBankAmountMismatch:
    def _setup(self):
        gross = 100_000
        fee, tax, net = compute_settlement_amounts(gross)
        settled = DT_BASE + timedelta(hours=1)
        order = make_order(amount_paise=gross)
        settlement = make_settlement(gross_amount_paise=gross, settled_at=settled)
        bank = make_bank_tx(amount_paise=net + 500, transaction_date=settled)
        return order, [settlement], [], [bank]

    def test_audit_status_unreconciled(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        assert audit["reconciled"] is False
        assert "unreconciled" in audit["status"]

    def test_bank_check_fails(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        bank_check = next(
            (c for c in audit["checks"] if c["rule"] == "RULE_2_SETTLEMENT_TO_BANK"),
            None,
        )
        assert bank_check is not None
        assert bank_check["passed"] is False
        assert bank_check["exception_type"] == "BANK_AMOUNT_MISMATCH"

    def test_bank_mismatch_in_exceptions(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        exc_types = {e["type"] for e in audit["exceptions"]}
        assert "BANK_AMOUNT_MISMATCH" in exc_types

    def test_amount_summary_shows_mismatch(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        assert audit["amount_summary"]["bank_matches_settlement_net"] is False


# ── Scenario 3: missing settlement ──────────────────────

class TestMissingSettlement:
    def test_audit_missing_settlement(self):
        order = make_order()
        audit = _reconcile_and_audit(order=order, settlements=[], refunds=[], bank_transactions=[])
        assert audit["status"] == "unreconciled_missing_settlement"
        assert audit["reconciled"] is False
        assert audit["confidence_score"] == 0

    def test_settlement_check_fails(self):
        order = make_order()
        audit = _reconcile_and_audit(order=order, settlements=[], refunds=[], bank_transactions=[])
        settlement_check = next(
            (c for c in audit["checks"] if c["rule"] == "RULE_1_ORDER_TO_SETTLEMENT"),
            None,
        )
        assert settlement_check is not None
        assert settlement_check["passed"] is False
        assert settlement_check["exception_type"] == "MISSING_SETTLEMENT"

    def test_timeline_mentions_no_settlement(self):
        order = make_order()
        audit = _reconcile_and_audit(order=order, settlements=[], refunds=[], bank_transactions=[])
        assert any("no settlement" in entry.lower() for entry in audit["timeline"])

    def test_references_empty_settlement(self):
        order = make_order()
        audit = _reconcile_and_audit(order=order, settlements=[], refunds=[], bank_transactions=[])
        assert audit["references"]["primary_settlement_id"] is None
        assert audit["references"]["valid_bank_transaction_id"] is None


# ── Scenario 4: refund adjusted ─────────────────────────

class TestRefundAdjusted:
    def _setup(self):
        gross = 100_000
        refund_amount = 10_000
        adjusted_gross = gross - refund_amount
        fee, tax, net = compute_settlement_amounts(adjusted_gross)
        settled = DT_BASE + timedelta(hours=1)
        order = make_order(amount_paise=gross)
        settlement = make_settlement(
            gross_amount_paise=adjusted_gross, settled_at=settled,
            fee_paise=fee, tax_paise=tax, net_amount_paise=net,
        )
        refund = make_refund(refund_amount_paise=refund_amount)
        bank = make_bank_tx(amount_paise=net, transaction_date=settled)
        return order, [settlement], [refund], [bank]

    def test_refund_adjusted_reconciled(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        assert audit["status"] == "reconciled_with_refund_adjustment"
        assert audit["reconciled"] is True

    def test_refund_check_passes(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        refund_check = next(
            (c for c in audit["checks"] if c["rule"] == "RULE_3_REFUND_ADJUSTMENT"),
            None,
        )
        assert refund_check is not None
        assert refund_check["passed"] is True

    def test_refund_in_amount_summary(self):
        order, settlements, refunds, banks = self._setup()
        audit = _reconcile_and_audit(
            order=order, settlements=settlements, refunds=refunds,
            bank_transactions=banks,
        )
        assert audit["amount_summary"]["total_refund_paise"] == 10_000
        assert audit["amount_summary"]["settlement_reflects_refund"] is True


# ── API endpoint tests ──────────────────────────────────

class TestAuditApiEndpoint:
    def test_audit_endpoint_returns_200(self):
        report = client.get("/api/v1/reconciliation/report").json()
        first_order_id = report["order_results"][0]["order_id"]
        response = client.get(f"/api/v1/reconciliation/{first_order_id}/audit")
        assert response.status_code == 200

    def test_audit_endpoint_structure(self):
        report = client.get("/api/v1/reconciliation/report").json()
        first_order_id = report["order_results"][0]["order_id"]
        audit = client.get(f"/api/v1/reconciliation/{first_order_id}/audit").json()
        assert audit["order_id"] == first_order_id
        assert "status" in audit
        assert "reconciled" in audit
        assert "confidence_score" in audit
        assert "checks" in audit
        assert "timeline" in audit
        assert "amount_summary" in audit
        assert "references" in audit
        assert "exceptions" in audit

    def test_audit_endpoint_missing_order_returns_400(self):
        response = client.get("/api/v1/reconciliation/NONEXISTENT_ORDER/audit")
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_audit_endpoint_no_secrets(self):
        report = client.get("/api/v1/reconciliation/report").json()
        first_order_id = report["order_results"][0]["order_id"]
        response = client.get(f"/api/v1/reconciliation/{first_order_id}/audit")
        text = response.text
        assert "RAZORPAY_KEY_SECRET" not in text
        assert "key_secret" not in text.lower()


# ── Phase 4A demo scenario audits ───────────────────────

class TestDemoScenarioAudits:
    """Verify build_structured_audit works on Phase 4A demo output."""

    @staticmethod
    def _demo_report():
        return api.run_razorpay_reconcile_demo()

    def test_successful_reconciliation_audit(self):
        payload = self._demo_report()
        order = next(r for r in payload["reconciliation"]["order_results"]
                     if r["order_id"] == "order_demo_success")
        audit = build_structured_audit(order)
        assert audit["reconciled"] is True
        assert audit["status"] == "reconciled"
        assert all(c["passed"] for c in audit["checks"])

    def test_bank_amount_mismatch_audit(self):
        payload = self._demo_report()
        order = next(r for r in payload["reconciliation"]["order_results"]
                     if r["order_id"] == "order_demo_bank_mismatch")
        audit = build_structured_audit(order)
        assert audit["reconciled"] is False
        exc_types = {e["type"] for e in audit["exceptions"]}
        assert "BANK_AMOUNT_MISMATCH" in exc_types
        bank_check = next(
            (c for c in audit["checks"] if c["rule"] == "RULE_2_SETTLEMENT_TO_BANK"), None
        )
        assert bank_check is not None
        assert bank_check["passed"] is False

    def test_missing_settlement_audit(self):
        payload = self._demo_report()
        order = next(r for r in payload["reconciliation"]["order_results"]
                     if r["order_id"] == "order_demo_missing_settlement")
        audit = build_structured_audit(order)
        assert audit["reconciled"] is False
        assert audit["status"] == "unreconciled_missing_settlement"
        settlement_check = next(
            (c for c in audit["checks"] if c["rule"] == "RULE_1_ORDER_TO_SETTLEMENT"), None
        )
        assert settlement_check is not None
        assert settlement_check["passed"] is False

    def test_refund_adjusted_audit(self):
        payload = self._demo_report()
        order = next(r for r in payload["reconciliation"]["order_results"]
                     if r["order_id"] == "order_demo_refund_adjusted")
        audit = build_structured_audit(order)
        assert audit["reconciled"] is True
        assert audit["status"] == "reconciled_with_refund_adjustment"

    def test_existing_demo_endpoint_unchanged(self):
        response = client.post("/api/v1/sources/razorpay/reconcile-demo")
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "razorpay"
        assert body["scenario_count"] == 4
        assert all(s["matched_expectation"] for s in body["scenarios"])

    def test_existing_csv_report_unchanged(self):
        response = client.get("/api/v1/reconciliation/report")
        assert response.status_code == 200
        report = response.json()
        assert len(report["order_results"]) == 100
        assert report["metadata"]["data_source"] == "csv"

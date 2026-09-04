"""Tests for POST /api/v1/reconciliation/import-bank (Bank CSV upload + reconcile)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from api import app

client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_CSV = PROJECT_ROOT / "data" / "demo_bank.csv"

# Minimal valid bank CSV that reconciles cleanly against the production fixtures.
# Uses SET_0001 net=370605 which exactly matches ORD_0001.
MINIMAL_VALID_CSV = (
    "bank_transaction_id,settlement_ref,amount,transaction_date,description\n"
    "T_BNK_0001,SET_0001,370605,2026-08-08T02:00:00,Test payout ORD_0001\n"
)

MISMATCH_BANK_CSV = (
    "bank_transaction_id,settlement_ref,amount,transaction_date,description\n"
    "T_BNK_0001,SET_0001,370605,2026-08-08T02:00:00,Test payout ORD_0001\n"
    "T_BNK_0002,SET_0002,99999,2026-08-15T20:24:00,Test payout ORD_0002 WRONG amount\n"
)

EMPTY_BANK_CSV = (
    "bank_transaction_id,settlement_ref,amount,transaction_date,description\n"
)

MALFORMED_CSV = "not,a,valid,bank,csv,header\nfoo,bar,baz,qux,quux,extra\n"

MISSING_COLUMN_CSV = (
    "bank_transaction_id,settlement_ref,amount,transaction_date\n"
    "T_BNK_0001,SET_0001,370605,2026-08-08T02:00:00\n"
)


def _upload(csv_content: str | bytes) -> dict:
    """POST the CSV to the import-bank endpoint via TestClient."""
    if isinstance(csv_content, str):
        csv_content = csv_content.encode("utf-8")
    return client.post(
        "/api/v1/reconciliation/import-bank",
        files={"file": ("bank.csv", io.BytesIO(csv_content), "text/csv")},
    )


class TestImportBankEndpoint:
    def test_returns_200_with_valid_csv(self):
        resp = _upload(MINIMAL_VALID_CSV)
        assert resp.status_code == 200

    def test_response_has_reconciliation_report_shape(self):
        resp = _upload(MINIMAL_VALID_CSV)
        body = resp.json()
        assert "summary" in body
        assert "order_results" in body
        assert "metadata" in body
        assert "status_counts" in body

    def test_bank_source_metadata_present(self):
        resp = _upload(MINIMAL_VALID_CSV)
        meta = resp.json()["metadata"]
        assert meta.get("bank_source") == "uploaded_csv"
        assert meta.get("bank_rows_imported") >= 1

    def test_total_orders_equals_production_dataset(self):
        resp = _upload(MINIMAL_VALID_CSV)
        # The production CSV has 50 orders; all are reconciled against uploaded bank rows
        assert resp.json()["summary"]["total_orders"] == 100

    def test_malformed_csv_returns_400(self):
        resp = _upload(MALFORMED_CSV)
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_missing_column_returns_400_with_message(self):
        resp = _upload(MISSING_COLUMN_CSV)
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        assert "description" in body["detail"]  # missing column name in error

    def test_no_traceback_in_error_response(self):
        resp = _upload(MALFORMED_CSV)
        assert "Traceback" not in resp.text
        assert "Exception" not in resp.text

    def test_existing_report_endpoint_unchanged(self):
        resp = client.get("/api/v1/reconciliation/report")
        assert resp.status_code == 200
        assert resp.json()["summary"]["total_orders"] == 100


class TestImportBankScenarios:
    """Verify the four demo scenarios reconcile correctly via the import endpoint."""

    def setup_method(self):
        resp = _upload(DEMO_CSV.read_bytes())
        assert resp.status_code == 200
        self._report = resp.json()
        self._by_id = {r["order_id"]: r for r in self._report["order_results"]}

    def test_demo_csv_imports_three_bank_rows(self):
        assert self._report["metadata"]["bank_rows_imported"] == 3

    # Scenario 1 — successful reconciliation (ORD_0001 with correct bank amount)
    def test_scenario_successful_reconciliation(self):
        order = self._by_id["ORD_0001"]
        assert order["reconciled"] is True
        assert order["valid_bank_transaction_id"] is not None
        assert "reconciled" in order["status"]

    # Scenario 2 — bank amount mismatch (ORD_0002 with wrong amount)
    def test_scenario_bank_amount_mismatch(self):
        order = self._by_id["ORD_0002"]
        assert order["reconciled"] is False
        exc_types = {e["type"] for e in order["exceptions"]}
        assert "BANK_AMOUNT_MISMATCH" in exc_types

    # Scenario 3 — missing bank (ORD_0003 has settlement but no bank row uploaded)
    def test_scenario_missing_bank_transaction(self):
        order = self._by_id["ORD_0003"]
        assert order["reconciled"] is False
        exc_types = {e["type"] for e in order["exceptions"]}
        assert "MISSING_BANK_TRANSACTION" in exc_types

    # Scenario 4 — refund-adjusted reconciliation (ORD_0033 has refund; bank row correct)
    def test_scenario_refund_adjusted(self):
        order = self._by_id["ORD_0033"]
        assert order["reconciled"] is True
        assert order["status"] == "reconciled_with_refund_adjustment"

    def test_demo_order_results_all_present(self):
        for oid in ("ORD_0001", "ORD_0002", "ORD_0003", "ORD_0033"):
            assert oid in self._by_id

    def test_order_results_have_audit_trail(self):
        order = self._by_id["ORD_0001"]
        assert isinstance(order["audit_trail"], list)
        assert len(order["audit_trail"]) >= 2

    def test_order_results_have_exceptions_field(self):
        for order in self._report["order_results"]:
            assert "exceptions" in order


class TestImportBankAuditIntegration:
    """GET audit uses production report; POST audit accepts imported order_result."""

    def test_audit_endpoint_works_for_known_order(self):
        # GET audit reflects production CSV + bank.csv report
        resp = client.get("/api/v1/reconciliation/ORD_0001/audit")
        assert resp.status_code == 200
        body = resp.json()
        assert body["order_id"] == "ORD_0001"
        assert "checks" in body
        assert "timeline" in body

    def test_audit_endpoint_for_missing_order_returns_400(self):
        resp = client.get("/api/v1/reconciliation/NONEXISTENT/audit")
        assert resp.status_code == 400

    def test_post_audit_from_import_result_preserves_demo_mismatch(self):
        """Bank-import drawer must audit the imported order_result, not production."""
        imported = _upload(DEMO_CSV.read_bytes())
        assert imported.status_code == 200
        report = imported.json()
        by_id = {o["order_id"]: o for o in report["order_results"]}
        mismatch = by_id["ORD_0002"]
        assert mismatch["reconciled"] is False

        resp = client.post(
            "/api/v1/reconciliation/audit",
            json={"order_result": mismatch},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["order_id"] == "ORD_0002"
        assert body["reconciled"] is False
        assert body["status"] == mismatch["status"]
        assert any(
            (c.get("exception_type") == "BANK_AMOUNT_MISMATCH") or (not c.get("passed"))
            for c in body["checks"]
        )

    def test_post_audit_rejects_empty_payload(self):
        resp = client.post("/api/v1/reconciliation/audit", json={"order_result": {}})
        assert resp.status_code == 400

    def test_post_explain_from_result_uses_structured_audit_facts(self, monkeypatch):
        imported = _upload(DEMO_CSV.read_bytes())
        order = next(o for o in imported.json()["order_results"] if o["order_id"] == "ORD_0003")

        class FakeResult:
            explanation = (
                "Summary:\nMissing bank for ORD_0003.\n\nWhy:\n- No bank row linked."
            )
            model = "gemini-3.5-flash"

        monkeypatch.setattr(
            api,
            "explain_structured_audit_with_gemini",
            lambda _audit: FakeResult(),
        )
        resp = client.post(
            "/api/v1/reconciliation/audit/explain",
            json={"order_result": order},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["order_id"] == "ORD_0003"
        assert body["reconciled"] is False
        assert body["status"] == order["status"]
        assert body["confidence_score"] == order["confidence_score"]
        assert body["provider"] == "gemini"
        assert body["model"] == "gemini-3.5-flash"
        assert "Summary:" in body["explanation"]

    def test_phase4a_demo_endpoint_unchanged(self):
        resp = client.post("/api/v1/sources/razorpay/reconcile-demo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scenario_count"] == 4
        assert all(s["matched_expectation"] for s in body["scenarios"])

    def test_health_endpoint_unchanged(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

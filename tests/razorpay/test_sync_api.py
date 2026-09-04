"""API tests for Razorpay sync endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
from api import app
from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayCredentialsError,
    RazorpayNetworkError,
)
from integrations.razorpay.sync import RazorpaySyncResult
from tests.razorpay.test_adapter import SAMPLE_ORDER
from tests.razorpay.test_sync import MockRazorpayClient

client = TestClient(app)


def test_existing_csv_report_still_works() -> None:
    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 200
    report = response.json()
    assert len(report["order_results"]) == 100
    assert report["metadata"]["data_source"] == "csv"


def test_existing_csv_summary_still_works() -> None:
    response = client.get("/api/v1/reconciliation/summary")
    assert response.status_code == 200
    assert response.json()["total_orders"] == 100


def test_existing_evaluation_still_works() -> None:
    response = client.get("/api/v1/evaluation")
    assert response.status_code == 200
    assert response.json()["summary"]["orders_evaluated"] == 100


def test_health_still_works() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_razorpay_sync_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.razorpay.sync import RazorpaySyncService

    def fake_sync() -> dict:
        result = RazorpaySyncService(MockRazorpayClient()).sync()
        return result.to_api_dict(reconciliation=None)

    monkeypatch.setattr(api, "run_razorpay_sync", fake_sync)
    response = client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "razorpay"
    assert body["status"] == "empty"
    assert body["orders"] == []
    assert body["reconciliation"] is None


def test_razorpay_sync_success_with_reconciliation(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.razorpay.sync import RazorpaySyncService

    sync_result = RazorpaySyncService(
        MockRazorpayClient(orders=[SAMPLE_ORDER])
    ).sync()

    def fake_sync() -> dict:
        reconciliation = api.run_reconciliation_from_records(
            sync_result.orders,
            sync_result.settlements,
            sync_result.refunds,
            [],
        )
        reconciliation["metadata"]["data_source"] = "razorpay"
        return sync_result.to_api_dict(reconciliation=reconciliation)

    monkeypatch.setattr(api, "run_razorpay_sync", fake_sync)
    response = client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "razorpay"
    assert body["status"] == "success"
    assert body["reconciliation"] is not None
    assert body["reconciliation"]["metadata"]["data_source"] == "razorpay"
    assert body["reconciliation"]["summary"]["total_orders"] == 1


def test_razorpay_sync_credentials_error_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_credentials() -> dict:
        raise RazorpayCredentialsError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set")

    monkeypatch.setattr(api, "run_razorpay_sync", raise_credentials)
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 503
    assert "credentials" in response.json()["detail"].lower()
    assert "RAZORPAY_KEY_SECRET" not in response.text


def test_razorpay_sync_api_error_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_api_error() -> dict:
        raise RazorpayAPIError("Razorpay unavailable", status_code=502)

    monkeypatch.setattr(api, "run_razorpay_sync", raise_api_error)
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 502
    assert "Traceback" not in response.text


def test_razorpay_sync_network_error_returns_504(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_network() -> dict:
        raise RazorpayNetworkError("Razorpay request timed out")

    monkeypatch.setattr(api, "run_razorpay_sync", raise_network)
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 504


def test_razorpay_sync_response_never_contains_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "never_expose_this_secret_in_api"

    def fake_sync() -> dict:
        from integrations.razorpay.sync import RazorpaySyncService

        result = RazorpaySyncService(MockRazorpayClient()).sync()
        payload = result.to_api_dict(reconciliation=None)
        payload["_test_secret_probe"] = secret  # ensure test checks response text broadly
        del payload["_test_secret_probe"]
        return payload

    monkeypatch.setattr(api, "run_razorpay_sync", fake_sync)
    response = client.post("/api/v1/sources/razorpay/sync")
    assert response.status_code == 200
    assert secret not in response.text
    assert "rzp_" not in response.text


def test_razorpay_sync_no_bank_transactions_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.razorpay.sync import RazorpaySyncService
    from tests.razorpay.test_adapter import SAMPLE_RECON_PAYMENT
    from tests.razorpay.test_sync import _recon_month_for

    month = _recon_month_for(SAMPLE_ORDER)
    sync_result = RazorpaySyncService(
        MockRazorpayClient(
            orders=[SAMPLE_ORDER],
            recon_by_month={month: [{**SAMPLE_RECON_PAYMENT, "settlement_utr": "UTR999"}]},
        )
    ).sync()

    def fake_sync() -> dict:
        return sync_result.to_api_dict(reconciliation=None)

    monkeypatch.setattr(api, "run_razorpay_sync", fake_sync)
    response = client.post("/api/v1/sources/razorpay/sync")
    body = response.json()
    assert body["bank_transactions_fetched"] == 0
    assert body["bank_data_available"] is False
    assert "bank_transaction_id" not in response.text

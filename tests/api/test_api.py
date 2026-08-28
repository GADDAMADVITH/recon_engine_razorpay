"""API endpoint tests for ReconEngine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
from api import app
from tests.conftest import minimal_valid_csv_dict, write_csv_dataset

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_structure():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "recon-engine-api"
    assert data["version"] == "v1"


def test_reconciliation_report_returns_200():
    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 200


def test_reconciliation_report_contains_fifty_orders():
    response = client.get("/api/v1/reconciliation/report")
    report = response.json()
    assert len(report["order_results"]) == 50


def test_reconciliation_summary_consistent_with_report():
    report = client.get("/api/v1/reconciliation/report").json()
    summary = client.get("/api/v1/reconciliation/summary").json()
    assert summary["total_orders"] == report["summary"]["total_orders"]
    assert summary["reconciled_orders"] == report["summary"]["reconciled_orders"]
    assert summary["unreconciled_orders"] == report["summary"]["unreconciled_orders"]
    assert summary["status_counts"] == report["status_counts"]


def test_reconciliation_summary_returns_200():
    response = client.get("/api/v1/reconciliation/summary")
    assert response.status_code == 200


def test_reconciliation_summary_reconciled_unreconciled_counts():
    summary = client.get("/api/v1/reconciliation/summary").json()
    assert summary["reconciled_orders"] == 26
    assert summary["unreconciled_orders"] == 24
    assert summary["total_orders"] == 50


def test_evaluation_returns_200():
    response = client.get("/api/v1/evaluation")
    assert response.status_code == 200


def test_evaluation_reports_fifty_orders():
    evaluation = client.get("/api/v1/evaluation").json()
    assert evaluation["summary"]["orders_evaluated"] == 50


def test_evaluation_binary_f1_is_perfect():
    evaluation = client.get("/api/v1/evaluation").json()
    binary = evaluation["binary_classification"]
    assert binary["f1_score"] == 1.0
    assert evaluation["summary"]["binary_f1_score"] == 1.0


def test_missing_csv_returns_404(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "DATA_DIR", Path("/nonexistent/recon/data"))
    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert "detail" in body
    assert "Missing required CSV files" in body["detail"]
    assert "Traceback" not in response.text


def test_invalid_schema_returns_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    frames = minimal_valid_csv_dict()
    frames["orders"] = frames["orders"].drop(columns=["amount"])
    write_csv_dataset(tmp_path, frames)
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert "detail" in body
    assert "orders column mismatch" in body["detail"]
    assert "Traceback" not in response.text


def test_unexpected_error_returns_500_without_traceback(monkeypatch: pytest.MonkeyPatch):
    def raise_runtime_error() -> None:
        raise RuntimeError("secret internal failure")

    monkeypatch.setattr(api, "run_reconciliation_report", raise_runtime_error)
    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.get("/api/v1/reconciliation/report")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body == {"detail": "Internal server error"}
    assert "Traceback" not in response.text
    assert "secret" not in response.text


def test_cors_preflight_allows_localhost_origin():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_reflects_allowed_origin_on_get():
    response = client.get(
        "/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

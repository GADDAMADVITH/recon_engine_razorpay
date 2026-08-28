"""API endpoint tests for ReconEngine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import app

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

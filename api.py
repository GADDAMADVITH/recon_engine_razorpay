"""HTTP API layer for ReconEngine.

This module exposes reconciliation and evaluation functionality over HTTP.
It orchestrates calls to recon_engine.py and metrics.py and does not implement
reconciliation business logic itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from metrics import build_evaluation, load_ground_truth, validate_schemas
from recon_engine import (
    DATA_DIR,
    _deterministic_report_timestamp,
    build_report,
    load_data,
    normalize_bank_transactions,
    normalize_orders,
    normalize_refunds,
    normalize_settlements,
    reconcile_all,
    validate_inputs,
)

API_VERSION = "v1"
SERVICE_NAME = "recon-engine-api"


# ---------------------------------------------------------
# Service orchestration (no business logic duplication)
# ---------------------------------------------------------


def run_reconciliation_report(data_dir: Path | None = None) -> dict[str, Any]:
    """Run the reconciliation pipeline and return the report dict (no file write)."""
    data_dir = data_dir or DATA_DIR
    raw_data = load_data(data_dir)
    validate_inputs(raw_data)

    settlements = normalize_settlements(raw_data["settlements"])
    valid_settlement_ids = {s.settlement_id for s in settlements}
    orders = normalize_orders(raw_data["orders"])
    refunds = normalize_refunds(raw_data["refunds"])
    bank_transactions = normalize_bank_transactions(raw_data["bank"], valid_settlement_ids)

    order_results, global_exceptions = reconcile_all(
        orders, settlements, refunds, bank_transactions
    )
    report_timestamp = _deterministic_report_timestamp(
        orders, settlements, bank_transactions
    )
    return build_report(
        order_results,
        global_exceptions,
        report_timestamp=report_timestamp,
    )


def run_evaluation(data_dir: Path | None = None) -> dict[str, Any]:
    """Run reconciliation and evaluate against ground truth (evaluation layer only)."""
    data_dir = data_dir or DATA_DIR
    report = run_reconciliation_report(data_dir)
    ground_truth = load_ground_truth(data_dir / "ground_truth.json")
    validate_schemas(ground_truth, report)
    return build_evaluation(ground_truth, report)


def build_api_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Build a concise summary payload from a full reconciliation report."""
    summary = report["summary"]
    exception_counts = {
        key: value
        for key, value in summary.items()
        if key not in ("total_orders", "reconciled_orders", "unreconciled_orders")
    }
    return {
        "total_orders": summary["total_orders"],
        "reconciled_orders": summary["reconciled_orders"],
        "unreconciled_orders": summary["unreconciled_orders"],
        "status_counts": report["status_counts"],
        "exception_counts": exception_counts,
    }


# ---------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status of the API service.")
    service: str = Field(..., description="Service identifier.")
    version: str = Field(..., description="API version prefix.")


class ReconciliationSummaryResponse(BaseModel):
    total_orders: int
    reconciled_orders: int
    unreconciled_orders: int
    status_counts: dict[str, int]
    exception_counts: dict[str, int]


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------


app = FastAPI(
    title="ReconEngine API",
    description=(
        "Deterministic financial reconciliation API. "
        "Reconciliation logic lives in recon_engine.py; "
        "evaluation uses ground_truth.json only in the evaluation layer."
    ),
    version="1.0.0",
)


@app.exception_handler(FileNotFoundError)
async def handle_file_not_found(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(ValueError)
async def handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail="Internal server error").model_dump(),
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Return API health status."""
    return HealthResponse(status="ok", service=SERVICE_NAME, version=API_VERSION)


@app.get(
    f"/api/{API_VERSION}/reconciliation/report",
    tags=["reconciliation"],
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_reconciliation_report() -> dict[str, Any]:
    """Run reconciliation on production CSV inputs and return the full report."""
    return run_reconciliation_report()


@app.get(
    f"/api/{API_VERSION}/reconciliation/summary",
    response_model=ReconciliationSummaryResponse,
    tags=["reconciliation"],
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_reconciliation_summary() -> ReconciliationSummaryResponse:
    """Return a concise reconciliation summary derived from the current report."""
    report = run_reconciliation_report()
    return ReconciliationSummaryResponse(**build_api_summary(report))


@app.get(
    f"/api/{API_VERSION}/evaluation",
    tags=["evaluation"],
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_evaluation() -> dict[str, Any]:
    """Run reconciliation and return evaluation metrics against ground truth."""
    return run_evaluation()

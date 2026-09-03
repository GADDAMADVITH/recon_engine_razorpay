"""HTTP API layer for ReconEngine.

This module exposes reconciliation and evaluation functionality over HTTP.
It orchestrates calls to recon_engine.py and metrics.py and does not implement
reconciliation business logic itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from integrations.data_sources import load_csv_dataset
from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayClient,
    RazorpayConfig,
    RazorpayCredentialsError,
    RazorpayNetworkError,
)
from integrations.razorpay.payment_verification import verify_payment_signature
from integrations.razorpay.sync import RazorpaySyncService
from metrics import build_evaluation, load_ground_truth, validate_schemas
from recon_engine import (
    DATA_DIR,
    NormalizedBankTransaction,
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
    _deterministic_report_timestamp,
    build_report,
    reconcile_all,
)

API_VERSION = "v1"
SERVICE_NAME = "recon-engine-api"

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# ---------------------------------------------------------
# Service orchestration (no business logic duplication)
# ---------------------------------------------------------


def run_reconciliation_from_records(
    orders: list[NormalizedOrder],
    settlements: list[NormalizedSettlement],
    refunds: list[NormalizedRefund],
    bank_transactions: list[NormalizedBankTransaction],
) -> dict[str, Any]:
    """Run reconciliation on pre-normalized records (any data source)."""
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


def run_reconciliation_report(data_dir: Path | None = None) -> dict[str, Any]:
    """Run the reconciliation pipeline and return the report dict (no file write)."""
    data_dir = data_dir or DATA_DIR
    dataset = load_csv_dataset(data_dir)
    report = run_reconciliation_from_records(
        list(dataset.orders),
        list(dataset.settlements),
        list(dataset.refunds),
        list(dataset.bank_transactions),
    )
    report["metadata"]["data_source"] = dataset.source
    return report


def run_razorpay_sync() -> dict[str, Any]:
    """Fetch Razorpay data, map it, and reconcile when orders exist."""
    with RazorpayClient.from_env() as client:
        sync_result = RazorpaySyncService(client).sync()

    reconciliation: dict[str, Any] | None = None
    if sync_result.has_orders:
        reconciliation = run_reconciliation_from_records(
            sync_result.orders,
            sync_result.settlements,
            sync_result.refunds,
            [],
        )
        reconciliation["metadata"]["data_source"] = sync_result.source

    return sync_result.to_api_dict(reconciliation=reconciliation)


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


class RazorpayPaymentVerificationRequest(BaseModel):
    razorpay_order_id: str = Field(..., min_length=1)
    razorpay_payment_id: str = Field(..., min_length=1)
    razorpay_signature: str = Field(..., min_length=1)


class RazorpayPaymentVerificationResponse(BaseModel):
    verified: bool
    message: str


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(RazorpayCredentialsError)
async def handle_razorpay_credentials(
    _request: Request, _exc: RazorpayCredentialsError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            detail="Razorpay credentials are not configured on the server"
        ).model_dump(),
    )


@app.exception_handler(RazorpayAPIError)
async def handle_razorpay_api_error(_request: Request, exc: RazorpayAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(RazorpayNetworkError)
async def handle_razorpay_network_error(
    _request: Request, exc: RazorpayNetworkError
) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(detail=str(exc)).model_dump(),
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


@app.post(
    f"/api/{API_VERSION}/sources/razorpay/sync",
    tags=["sources"],
    responses={
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_razorpay_sync() -> dict[str, Any]:
    """Fetch Razorpay data, map to ReconEngine records, and reconcile when possible."""
    return run_razorpay_sync()


@app.post(
    f"/api/{API_VERSION}/sources/razorpay/verify-payment",
    response_model=RazorpayPaymentVerificationResponse,
    tags=["sources"],
    responses={
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_razorpay_verify_payment(
    body: RazorpayPaymentVerificationRequest,
) -> RazorpayPaymentVerificationResponse:
    """Verify Razorpay Checkout signature server-side (dev/test utility)."""
    config = RazorpayConfig.from_env()
    verified = verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
        key_secret=config.key_secret,
    )
    if verified:
        message = "Payment signature verified by backend"
    else:
        message = "Payment signature verification failed"
    return RazorpayPaymentVerificationResponse(verified=verified, message=message)

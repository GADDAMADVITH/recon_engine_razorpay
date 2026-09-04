"""HTTP API layer for ReconEngine.

This module exposes reconciliation and evaluation functionality over HTTP.
It orchestrates calls to recon_engine.py and metrics.py and does not implement
reconciliation business logic itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import io

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ai_explainer import (
    GeminiConfigurationError,
    GeminiServiceError,
    chat_with_gemini,
    explain_structured_audit_with_gemini,
)
from audit import build_structured_audit
from chat_context import build_chat_grounding
from finance_agent import run_finance_controller
from finance_agent_eval import evaluate_finance_controller, write_evaluation_result
from finance_agent_run import (
    find_run_id_for_order,
    get_approval_queue,
    get_lifecycle_metrics,
    list_agent_run_history,
    run_finance_controller_agent,
)
from finance_agent_plan import build_finance_controller_agent_plan
from finance_actions import (
    FinanceActionError,
    approve_and_record_action,
    reject_action,
    reset_action_store,
)
from integrations.data_sources import load_csv_dataset
from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayClient,
    RazorpayConfig,
    RazorpayCredentialsError,
    RazorpayNetworkError,
)
from integrations.razorpay.demo_fixtures import (
    DEMO_BANK_SOURCE,
    DEMO_BANK_SOURCE_NOTE,
    DEMO_DATA_SOURCE,
    build_demo_reconciliation_input,
    scenario_expectations,
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

# Load local .env into process environment at import time (development).
# Does not override variables already set in the shell/process environment.
# Secrets never appear in source; .env remains gitignored.
PROJECT_ROOT = Path(__file__).resolve().parent


def load_project_env(env_file: Path | None = None) -> bool:
    """Load key/value pairs from a .env file into os.environ.

    Returns True if a file was found and processed. Existing environment
    variables take precedence (override=False).
    """
    path = env_file if env_file is not None else PROJECT_ROOT / ".env"
    return load_dotenv(path, override=False)


load_project_env()

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


def run_razorpay_reconcile_demo() -> dict[str, Any]:
    """Run Phase 4A demo reconciliation with Razorpay-shaped + synthetic bank fixtures.

    Does not call the live Razorpay API. Bank rows are explicitly labelled as
    synthetic fixtures and are never derived from Razorpay settlement_utr.
    """
    demo = build_demo_reconciliation_input()
    reconciliation = run_reconciliation_from_records(
        list(demo.orders),
        list(demo.settlements),
        list(demo.refunds),
        list(demo.bank_transactions),
    )
    reconciliation["metadata"]["data_source"] = demo.data_source
    reconciliation["metadata"]["bank_source"] = demo.bank_source
    reconciliation["metadata"]["bank_source_note"] = demo.bank_source_note

    order_by_id = {r["order_id"]: r for r in reconciliation["order_results"]}
    scenario_results = []
    for expectation in scenario_expectations():
        result = order_by_id[expectation["order_id"]]
        scenario_results.append(
            {
                **expectation,
                "actual_status": result["status"],
                "actual_reconciled": result["reconciled"],
                "matched_expectation": (
                    result["status"] == expectation["expected_status"]
                    and result["reconciled"] == expectation["expected_reconciled"]
                ),
            }
        )

    return {
        "source": DEMO_DATA_SOURCE,
        "bank_source": DEMO_BANK_SOURCE,
        "bank_source_note": DEMO_BANK_SOURCE_NOTE,
        "status": "success",
        "scenario_count": len(scenario_results),
        "scenarios": scenario_results,
        "reconciliation": reconciliation,
    }


_BANK_REQUIRED_COLUMNS = frozenset(
    {"bank_transaction_id", "settlement_ref", "amount", "transaction_date", "description"}
)


def run_bank_import(bank_csv_bytes: bytes) -> dict[str, Any]:
    """Parse uploaded bank CSV, normalise, reconcile against production CSV orders/settlements.

    The bank rows come from the upload; orders/settlements/refunds come from the
    production CSV dataset on disk (same source as GET /api/v1/reconciliation/report).
    """
    from recon_engine import normalize_bank_transactions

    try:
        bank_df = pd.read_csv(io.StringIO(bank_csv_bytes.decode("utf-8")))
    except Exception as exc:
        raise ValueError(f"Bank CSV could not be parsed: {exc}") from exc

    missing_cols = _BANK_REQUIRED_COLUMNS - set(bank_df.columns)
    if missing_cols:
        raise ValueError(
            f"Bank CSV is missing required columns: {', '.join(sorted(missing_cols))}. "
            f"Required: {', '.join(sorted(_BANK_REQUIRED_COLUMNS))}"
        )

    # Load existing orders/settlements/refunds from production CSVs
    dataset = load_csv_dataset(DATA_DIR)

    valid_settlement_ids = {s.settlement_id for s in dataset.settlements}
    try:
        bank_transactions = normalize_bank_transactions(bank_df, valid_settlement_ids)
    except Exception as exc:
        raise ValueError(f"Bank CSV rows could not be normalised: {exc}") from exc

    reconciliation = run_reconciliation_from_records(
        list(dataset.orders),
        list(dataset.settlements),
        list(dataset.refunds),
        bank_transactions,
    )
    reconciliation["metadata"]["data_source"] = "csv"
    reconciliation["metadata"]["bank_source"] = "uploaded_csv"
    reconciliation["metadata"]["bank_rows_imported"] = len(bank_transactions)
    return reconciliation


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


class AuditExplanationResponse(BaseModel):
    order_id: str
    status: str
    reconciled: bool
    confidence_score: int
    explanation: str
    provider: str = "gemini"
    model: str | None = None


class OrderAuditFromResultRequest(BaseModel):
    """Audit/explain from an already-computed order_result (e.g. bank-import run).

    Does not re-run reconciliation — only transforms the provided engine output.
    """

    order_result: dict[str, Any]


class ChatRequest(BaseModel):
    """Conversational question for ReconEngine AI.

    Financial facts in ``page_context`` are ignored. Optional ``order_result``
    must be engine-computed output (same contract as audit/explain POST).
    """

    message: str = Field(..., min_length=1, max_length=4000)
    order_id: str | None = Field(default=None, max_length=64)
    order_result: dict[str, Any] | None = None
    page_context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    message: str
    provider: str = "gemini"
    model: str | None = None


class FinanceControllerRunRequest(BaseModel):
    """Optional payload for the finance controller.

    When omitted, the controller runs on the current production reconciliation
    report. When ``order_results`` is provided, it must be engine-computed
    order_result dicts (e.g. from bank-import) — the agent never invents facts.
    """

    order_results: list[dict[str, Any]] | None = None


class FinanceControllerApproveRequest(BaseModel):
    """Human approval for a simulated, record-only Finance Controller action.

    ``agent_decision`` is verified against the authoritative agent — never trusted.
    Optional ``order_result`` supplies the same engine facts shown in the drawer
    (e.g. bank-import). When omitted, the production report is used.
    """

    order_id: str = Field(..., min_length=1, max_length=64)
    agent_decision: str = Field(..., min_length=1, max_length=64)
    order_result: dict[str, Any] | None = None
    run_id: str | None = Field(default=None, max_length=64)


class FinanceControllerRejectRequest(BaseModel):
    """Human rejection for a simulated Finance Controller action (no money movement)."""

    order_id: str = Field(..., min_length=1, max_length=64)
    agent_decision: str = Field(..., min_length=1, max_length=64)
    order_result: dict[str, Any] | None = None
    run_id: str | None = Field(default=None, max_length=64)


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


@app.exception_handler(FinanceActionError)
async def handle_finance_action_error(
    _request: Request, exc: FinanceActionError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=exc.detail).model_dump(),
    )


@app.exception_handler(GeminiConfigurationError)
async def handle_gemini_configuration_error(
    _request: Request, exc: GeminiConfigurationError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(GeminiServiceError)
async def handle_gemini_service_error(
    _request: Request, exc: GeminiServiceError
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
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
    f"/api/{API_VERSION}/reconciliation/{{order_id}}/audit",
    tags=["reconciliation"],
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_order_audit(order_id: str) -> dict[str, Any]:
    """Return a structured audit trail for a specific order."""
    report = run_reconciliation_report()
    order_result = next(
        (r for r in report["order_results"] if r["order_id"] == order_id),
        None,
    )
    if order_result is None:
        raise ValueError(f"Order {order_id!r} not found in reconciliation report")
    return build_structured_audit(order_result)


@app.get(
    f"/api/{API_VERSION}/reconciliation/{{order_id}}/audit/explain",
    response_model=AuditExplanationResponse,
    tags=["reconciliation"],
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_order_audit_explanation(order_id: str) -> AuditExplanationResponse:
    """Return a grounded Gemini explanation for a specific order's structured audit."""
    report = run_reconciliation_report()
    order_result = next(
        (r for r in report["order_results"] if r["order_id"] == order_id),
        None,
    )
    if order_result is None:
        raise ValueError(f"Order {order_id!r} not found in reconciliation report")

    structured_audit = build_structured_audit(order_result)
    result = explain_structured_audit_with_gemini(structured_audit)
    return AuditExplanationResponse(
        order_id=structured_audit["order_id"],
        status=structured_audit["status"],
        reconciled=structured_audit["reconciled"],
        confidence_score=structured_audit["confidence_score"],
        explanation=result.explanation,
        provider="gemini",
        model=result.model,
    )


def _audit_from_order_result_payload(order_result: dict[str, Any]) -> dict[str, Any]:
    """Validate a client-supplied order_result and build structured audit (read-only)."""
    if not isinstance(order_result, dict):
        raise ValueError("order_result must be an object")
    order_id = order_result.get("order_id")
    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("order_result.order_id is required")
    if "status" not in order_result or "reconciled" not in order_result:
        raise ValueError("order_result must include status and reconciled")
    return build_structured_audit(order_result)


@app.post(
    f"/api/{API_VERSION}/reconciliation/audit",
    tags=["reconciliation"],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_order_audit_from_result(body: OrderAuditFromResultRequest) -> dict[str, Any]:
    """Build structured audit from a provided order_result (bank-import / drawer context).

    Prefer this over GET .../{order_id}/audit when the UI already has a specific
    reconciliation run's order payload (e.g. after CSV bank import).
    """
    return _audit_from_order_result_payload(body.order_result)


@app.post(
    f"/api/{API_VERSION}/reconciliation/audit/explain",
    response_model=AuditExplanationResponse,
    tags=["reconciliation"],
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_order_audit_explanation_from_result(
    body: OrderAuditFromResultRequest,
) -> AuditExplanationResponse:
    """Gemini explanation grounded on a provided order_result's structured audit."""
    structured_audit = _audit_from_order_result_payload(body.order_result)
    result = explain_structured_audit_with_gemini(structured_audit)
    return AuditExplanationResponse(
        order_id=structured_audit["order_id"],
        status=structured_audit["status"],
        reconciled=structured_audit["reconciled"],
        confidence_score=structured_audit["confidence_score"],
        explanation=result.explanation,
        provider="gemini",
        model=result.model,
    )


@app.post(
    f"/api/{API_VERSION}/chat",
    response_model=ChatResponse,
    tags=["chat"],
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_chat(body: ChatRequest) -> ChatResponse:
    """Answer a natural-language question grounded on current reconciliation data.

    Gemini explains evidence only. Reconciliation facts always come from the
    deterministic engine / structured audit — never from client-claimed amounts.
    """
    report = run_reconciliation_report()
    grounding = build_chat_grounding(
        report=report,
        message=body.message,
        order_id=body.order_id,
        order_result=body.order_result,
        page_context=body.page_context,
    )
    result = chat_with_gemini(message=body.message, grounding=grounding)
    return ChatResponse(
        message=result.explanation,
        provider="gemini",
        model=result.model,
    )


@app.post(
    f"/api/{API_VERSION}/finance-controller/run",
    tags=["finance-controller"],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_run(
    body: FinanceControllerRunRequest | None = None,
) -> dict[str, Any]:
    """Run the bounded Finance Controller Agent on reconciliation results.

    Empty body → current production reconciliation report (100+ orders).
    Optional ``order_results`` → engine-computed results (e.g. bank-import batch).

    Read-only: does not mutate reconciliation outcomes, datasets, or Razorpay state.
    """
    payload = body or FinanceControllerRunRequest()
    if payload.order_results is not None:
        batch = run_finance_controller(payload.order_results)
        data_source = "provided_order_results"
    else:
        batch = run_finance_controller(run_reconciliation_report())
        data_source = "production_reconciliation_report"

    payload_out = batch.to_dict()
    # Make ORIGINAL RESULT vs AGENT DECISION explicit in the API envelope.
    enriched: list[dict[str, Any]] = []
    for decision in payload_out["decisions"]:
        enriched.append(
            {
                **decision,
                "original_result": {
                    "order_id": decision["order_id"],
                    "status": decision["original_status"],
                    "reconciled": decision["original_reconciled"],
                    "confidence_score": decision["confidence_score"],
                    "exception_types": list(decision["exception_types"]),
                },
                "agent_decision": {
                    "decision": decision["decision"],
                    "action": decision["action"],
                    "reason": decision["reason"],
                    "requires_approval": decision["requires_approval"],
                    "evidence": decision["evidence"],
                    "provider": decision.get("provider"),
                    "agent": decision.get("agent"),
                    "agent_version": decision.get("agent_version"),
                },
            }
        )
    payload_out["decisions"] = enriched
    payload_out["data_source"] = data_source
    return payload_out


@app.post(
    f"/api/{API_VERSION}/finance-controller/run-agent",
    tags=["finance-controller"],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_run_agent(
    body: FinanceControllerRunRequest | None = None,
) -> dict[str, Any]:
    """Run the Finance Controller as an agent workflow with decision traces.

    Orchestrates existing ``finance_agent.py`` policy — does not change rules.
    Empty body → production reconciliation report.
    Optional ``order_results`` → provided engine-computed results.
    """
    payload = body or FinanceControllerRunRequest()
    if payload.order_results is not None:
        return run_finance_controller_agent(
            payload.order_results,
            data_source="provided_order_results",
        )
    return run_finance_controller_agent(
        run_reconciliation_report(),
        data_source="production_reconciliation_report",
    )


@app.post(
    f"/api/{API_VERSION}/finance-controller/agent-plan",
    tags=["finance-controller"],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_agent_plan(
    body: FinanceControllerRunRequest | None = None,
) -> dict[str, Any]:
    """Batch-level agent orchestration: analysis, priority queue, and work plan.

    Reuses deterministic ``finance_agent.py`` classification — does not call Gemini
    for decisions or priority. Never moves money or mutates reconciliation facts.
    Empty body → production reconciliation report (100+ orders).
    """
    payload = body or FinanceControllerRunRequest()
    if payload.order_results is not None:
        return build_finance_controller_agent_plan(
            payload.order_results,
            data_source="provided_order_results",
        )
    return build_finance_controller_agent_plan(
        run_reconciliation_report(),
        data_source="production_reconciliation_report",
    )


@app.get(
    f"/api/{API_VERSION}/finance-controller/evaluation",
    tags=["finance-controller"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_finance_controller_evaluation() -> dict[str, Any]:
    """Evaluate Finance Controller decisions on the held-out labeled dataset.

    Uses ``data/finance_controller_eval_v1.json`` (not demo/production data).
    Observes the existing agent — does not change policy or reconciliation.
    """
    result = evaluate_finance_controller()
    write_evaluation_result(result)
    return result


@app.post(
    f"/api/{API_VERSION}/finance-controller/actions/approve",
    tags=["finance-controller"],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_approve(
    body: FinanceControllerApproveRequest,
) -> dict[str, Any]:
    """Human-gated approval of a simulated Finance Controller action.

    Recomputes the agent decision from engine evidence. Never trusts the
    client-provided decision. Never moves money or mutates reconciliation facts.
    Idempotent for the same order + mapped action type.
    """
    production_lookup: dict[str, Any] | None = None
    if body.order_result is None:
        report = run_reconciliation_report()
        production_lookup = {
            str(order["order_id"]): order for order in report.get("order_results", [])
        }

    run_id = body.run_id or find_run_id_for_order(body.order_id)
    return approve_and_record_action(
        order_id=body.order_id,
        claimed_agent_decision=body.agent_decision,
        order_result=body.order_result,
        production_lookup=production_lookup,
        run_id=run_id,
    )


@app.post(
    f"/api/{API_VERSION}/finance-controller/actions/reject",
    tags=["finance-controller"],
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_reject(
    body: FinanceControllerRejectRequest,
) -> dict[str, Any]:
    """Human rejection of a proposed simulated Finance Controller action.

    PENDING → REJECTED. Never moves money. Never mutates reconciliation facts.
    Idempotent when already rejected. Invalid after RECORDED/APPROVED.
    """
    production_lookup: dict[str, Any] | None = None
    if body.order_result is None:
        report = run_reconciliation_report()
        production_lookup = {
            str(order["order_id"]): order for order in report.get("order_results", [])
        }

    run_id = body.run_id or find_run_id_for_order(body.order_id)
    return reject_action(
        order_id=body.order_id,
        claimed_agent_decision=body.agent_decision,
        order_result=body.order_result,
        production_lookup=production_lookup,
        run_id=run_id,
    )


@app.get(
    f"/api/{API_VERSION}/finance-controller/approval-queue",
    tags=["finance-controller"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def get_finance_controller_approval_queue(run_id: str | None = None) -> dict[str, Any]:
    """Pending/approval-gated decisions from the latest (or specified) agent run."""
    return get_approval_queue(run_id=run_id)


@app.get(
    f"/api/{API_VERSION}/finance-controller/runs",
    tags=["finance-controller"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def get_finance_controller_runs(limit: int = 20) -> dict[str, Any]:
    """Agent run history with live action lifecycle counts."""
    capped = max(1, min(limit, 50))
    history = list_agent_run_history(limit=capped)
    return {"runs": history, "count": len(history)}


@app.get(
    f"/api/{API_VERSION}/finance-controller/lifecycle",
    tags=["finance-controller"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def get_finance_controller_lifecycle(run_id: str | None = None) -> dict[str, Any]:
    """Batch-level human-in-the-loop lifecycle metrics for a run."""
    return get_lifecycle_metrics(run_id=run_id)


@app.get(
    f"/api/{API_VERSION}/finance-controller/demo-status",
    tags=["finance-controller"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def get_finance_controller_demo_status() -> dict[str, Any]:
    """Compact demo readiness checks for Track 04 evaluation.

    Does not expose secrets. Does not mutate datasets, policy, or reconciliation.
    """
    report = run_reconciliation_report()
    orders = list(report.get("order_results") or [])
    eval_result = evaluate_finance_controller()
    checks = {
        "api_reachable": True,
        "reconciliation_data_available": len(orders) > 0,
        "agent_endpoint_available": True,
        "evaluation_endpoint_available": True,
    }
    ready = all(checks.values()) and len(orders) >= 50 and int(eval_result.get("records_evaluated") or 0) >= 50
    return {
        "ready": ready,
        "checks": checks,
        "operational_batch": {
            "label": "Operational batch",
            "records": len(orders),
        },
        "held_out_evaluation": {
            "label": "Held-out evaluation",
            "records_evaluated": int(eval_result.get("records_evaluated") or 0),
            "accuracy": eval_result.get("accuracy"),
            "measurement_note": eval_result.get("measurement_note"),
        },
        "money_moved": False,
        "simulated_actions_only": True,
        "human_approval_required": True,
        "gemini_in_decision_path": False,
        "secrets_exposed": False,
    }


@app.post(
    f"/api/{API_VERSION}/finance-controller/demo-reset",
    tags=["finance-controller"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def post_finance_controller_demo_reset() -> dict[str, Any]:
    """Clear local/demo simulated action state only.

    Does not alter reconciliation CSVs, held-out evaluation labels, agent policy,
    amounts, confidence, or reconciliation status. Decisions remain deterministic.
    """
    reset_action_store()
    return {
        "reset": True,
        "scope": "local_demo_action_store",
        "datasets_untouched": True,
        "evaluation_untouched": True,
        "policy_untouched": True,
        "reconciliation_untouched": True,
        "money_moved": False,
        "secrets_exposed": False,
        "note": (
            "Cleared simulated finance action records and their audit events only. "
            "Re-run approve/reject for a fresh demo loop."
        ),
    }


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
    f"/api/{API_VERSION}/sources/razorpay/reconcile-demo",
    tags=["sources"],
    responses={
        500: {"model": ErrorResponse},
    },
)
def post_razorpay_reconcile_demo() -> dict[str, Any]:
    """Phase 4A: demonstrate reconciliation with Razorpay-shaped + synthetic bank fixtures.

    Does not call live Razorpay. Bank data is an explicit synthetic fixture source.
    """
    return run_razorpay_reconcile_demo()


@app.post(
    f"/api/{API_VERSION}/reconciliation/import-bank",
    tags=["reconciliation"],
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def post_import_bank(file: UploadFile) -> dict[str, Any]:
    """Upload a bank CSV and reconcile against production orders/settlements.

    Accepts multipart/form-data with field name ``file`` containing a CSV with
    columns: bank_transaction_id, settlement_ref, amount, transaction_date, description.
    Returns the full reconciliation report with an additional bank_source field.
    """
    contents = await file.read()
    return run_bank_import(contents)


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

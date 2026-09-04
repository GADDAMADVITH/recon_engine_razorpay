"""Finance Controller Agent Run / Decision Trace layer.

Orchestrates ``finance_agent.py`` into an auditable agent-run workflow without
changing decision policy.

Architecture:

    Reconciliation Engine
            ↓
    Structured Audit / Evidence
            ↓
    Finance Controller Agent (finance_agent.py)
            ↓
    Agent Run / Decision Trace (this module)
            ↓
    Human Approval → Simulated Action → Audit Trail
"""

from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_actions import DECISION_TO_ACTION
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    FinanceAgentDecision,
    decide_for_order,
    run_finance_controller,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_RUN_STORE_PATH = DATA_DIR / "finance_agent_runs.json"

_lock = threading.Lock()
_runs_by_id: dict[str, dict[str, Any]] = {}
_latest_run_id: str | None = None
_store_path: Path = DEFAULT_RUN_STORE_PATH
_persist: bool = True


def configure_run_store(*, path: Path | None = None, persist: bool | None = None) -> None:
    global _store_path, _persist
    with _lock:
        if path is not None:
            _store_path = path
        if persist is not None:
            _persist = persist


def reset_run_store() -> None:
    with _lock:
        _runs_by_id.clear()
        global _latest_run_id
        _latest_run_id = None
        if _persist and _store_path.exists():
            _store_path.unlink()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_unlocked() -> None:
    global _latest_run_id
    if not _persist or not _store_path.exists():
        return
    with _store_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    _runs_by_id.clear()
    for run in payload.get("runs") or []:
        run_id = run.get("run_id")
        if isinstance(run_id, str) and run_id:
            _runs_by_id[run_id] = run
    _latest_run_id = payload.get("latest_run_id")


def _save_unlocked() -> None:
    if not _persist:
        return
    _store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "latest_run_id": _latest_run_id,
        "runs": list(_runs_by_id.values())[-50:],  # keep last 50 runs for MVP
    }
    # Re-index if trimmed
    if len(payload["runs"]) < len(_runs_by_id):
        _runs_by_id.clear()
        for run in payload["runs"]:
            _runs_by_id[run["run_id"]] = run
    with _store_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def proposed_action_for_decision(decision: str) -> str | None:
    """Reuse allowlisted action mapping; NO_ACTION → no action."""
    if decision == DECISION_NO_ACTION:
        return None
    return DECISION_TO_ACTION.get(decision)


def build_deterministic_rationale(decision: FinanceAgentDecision) -> str:
    """Human-readable rationale from engine/audit evidence only — no invented facts."""
    types = set(decision.exception_types)
    status = decision.original_status
    reconciled = decision.original_reconciled

    if decision.decision == DECISION_NO_ACTION:
        if types:
            return (
                "Reconciliation is successful and no blocking exception requires intervention. "
                f"Informational evidence present: {', '.join(sorted(types))}."
            )
        return (
            "Reconciliation is successful and no blocking exception requires intervention."
        )

    if decision.decision == DECISION_ESCALATE_MISSING_SETTLEMENT:
        return "Settlement is missing; escalation is required."

    if decision.decision == DECISION_ESCALATE_MISSING_BANK:
        return "Bank transaction is missing; escalation is required."

    if decision.decision == DECISION_VERIFY_REFUND:
        return "Refund-adjusted exception detected; refund state requires verification."

    if decision.decision == DECISION_FLAG_FOR_REVIEW:
        if "BANK_AMOUNT_MISMATCH" in types or "SETTLEMENT_AMOUNT_MISMATCH" in types:
            return "Amount mismatch detected; financial result requires human review."
        if "REFUND_NOT_REFLECTED" in types:
            return (
                "Refund not reflected in settlement evidence; financial result requires human review."
            )
        severe = sorted(
            t
            for t in types
            if t
            in {
                "DUPLICATE_SETTLEMENT",
                "DUPLICATE_BANK_TRANSACTION",
                "ORPHAN_BANK_TRANSACTION",
                "TIMESTAMP_OUTSIDE_TOLERANCE",
            }
        )
        if severe:
            return (
                f"Severe exception(s) detected ({', '.join(severe)}); "
                "financial result requires human review."
            )
        if types:
            return (
                f"Exception evidence ({', '.join(sorted(types))}) requires human review "
                f"(status={status}, reconciled={reconciled})."
            )
        return (
            "Ambiguous or unmapped reconciliation state; financial result requires human review."
        )

    # Should not happen for allowlisted decisions; keep fail-safe text.
    return decision.reason


def _audit_evidence_summary(decision: FinanceAgentDecision) -> dict[str, Any]:
    evidence = decision.evidence or {}
    return {
        "status": evidence.get("status", decision.original_status),
        "reconciled": evidence.get("reconciled", decision.original_reconciled),
        "confidence_score": evidence.get("confidence_score", decision.confidence_score),
        "exception_types": list(decision.exception_types),
        "failed_checks": list(evidence.get("failed_checks") or [])[:8],
        "amount_summary": evidence.get("amount_summary") or {},
        "references": evidence.get("references") or {},
    }


def build_decision_trace(
    order_result: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build one immutable decision trace for an engine order_result."""
    before = copy.deepcopy(order_result)
    decision = decide_for_order(order_result)
    after = copy.deepcopy(order_result)
    if before != after:
        raise ValueError("Immutability violation: finance agent mutated order_result")

    proposed = proposed_action_for_decision(decision.decision)
    rationale = build_deterministic_rationale(decision)
    ts = timestamp or _utc_now()

    return {
        "order_id": decision.order_id,
        "original_result": {
            "order_id": decision.order_id,
            "status": decision.original_status,
            "reconciled": decision.original_reconciled,
            "confidence_score": decision.confidence_score,
            "exception_types": list(decision.exception_types),
        },
        "audit_evidence_summary": _audit_evidence_summary(decision),
        "triggered_exceptions": list(decision.exception_types),
        "decision": decision.decision,
        "rationale": rationale,
        "agent_reason": decision.reason,
        "requires_approval": decision.requires_approval,
        "proposed_action": proposed,
        "timestamp": ts,
        "provider": decision.provider,
        "agent": decision.agent,
        "agent_version": decision.agent_version,
    }


@dataclass
class FinanceAgentRun:
    run_id: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    records_processed: int
    no_action_count: int
    review_required_count: int
    unresolved_count: int
    exception_count: int
    pending_approval_count: int
    decisions_by_type: dict[str, int]
    decisions: list[dict[str, Any]] = field(default_factory=list)
    data_source: str = "production_reconciliation_report"
    provider: str = "deterministic_policy"
    agent: str = "reconengine-finance-controller"
    agent_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_finance_controller_agent(
    reconciliation_results: list[dict[str, Any]] | dict[str, Any] | None = None,
    *,
    data_source: str = "production_reconciliation_report",
) -> dict[str, Any]:
    """Execute one Finance Controller agent run with decision traces.

    Calls existing ``run_finance_controller`` / ``decide_for_order`` — does not
    reimplement policy. Empty/missing order list yields a zero-record run.
    """
    started_at = _utc_now()
    t0 = time.perf_counter()

    if reconciliation_results is None:
        orders: list[dict[str, Any]] = []
    elif isinstance(reconciliation_results, dict):
        raw = reconciliation_results.get("order_results")
        if raw is None:
            raise ValueError("report must contain an order_results list")
        if not isinstance(raw, list):
            raise ValueError("report order_results must be a list")
        orders = [o for o in raw if isinstance(o, dict)]
    elif isinstance(reconciliation_results, list):
        orders = [o for o in reconciliation_results if isinstance(o, dict)]
    else:
        raise ValueError("reconciliation_results must be a report dict or order list")

    # Use existing batch engine for metrics consistency, then enrich traces.
    batch = run_finance_controller(orders)
    ts = _utc_now()
    traces = [build_decision_trace(order, timestamp=ts) for order in orders]

    # Align trace decisions with batch (same policy); prefer per-order traces.
    pending_approval = sum(1 for t in traces if t["requires_approval"])
    completed_at = _utc_now()
    elapsed = round(time.perf_counter() - t0, 6)

    run = FinanceAgentRun(
        run_id=f"FCRUN_{uuid.uuid4().hex[:12]}",
        started_at=started_at,
        completed_at=completed_at,
        elapsed_seconds=elapsed,
        records_processed=batch.records_processed,
        no_action_count=batch.no_action_count,
        review_required_count=batch.review_required_count,
        unresolved_count=batch.unresolved_count,
        exception_count=batch.exception_count,
        pending_approval_count=pending_approval,
        decisions_by_type=dict(batch.decisions_by_type),
        decisions=traces,
        data_source=data_source,
        provider=batch.provider,
        agent=batch.agent,
        agent_version=batch.agent_version,
    )
    payload = run.to_dict()

    with _lock:
        if not _runs_by_id and _persist and _store_path.exists():
            _load_unlocked()
        _runs_by_id[run.run_id] = copy.deepcopy(payload)
        global _latest_run_id
        _latest_run_id = run.run_id
        _save_unlocked()

    return payload


def get_agent_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        if not _runs_by_id and _persist and _store_path.exists():
            _load_unlocked()
        run = _runs_by_id.get(run_id)
        return copy.deepcopy(run) if run else None


def get_latest_agent_run() -> dict[str, Any] | None:
    with _lock:
        if not _runs_by_id and _persist and _store_path.exists():
            _load_unlocked()
        if not _latest_run_id:
            return None
        run = _runs_by_id.get(_latest_run_id)
        return copy.deepcopy(run) if run else None


def get_decision_trace_for_order(
    order_id: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any] | None:
    run = get_agent_run(run_id) if run_id else get_latest_agent_run()
    if not run:
        return None
    for decision in run.get("decisions") or []:
        if decision.get("order_id") == order_id:
            return copy.deepcopy(decision)
    return None


def _action_counts_for_run(run: dict[str, Any]) -> dict[str, int]:
    """Compute human-action lifecycle counts from stored action records (not fabricated)."""
    from finance_actions import action_status_for_decision

    completed = 0  # terminal human outcomes (recorded or rejected)
    approved = 0
    rejected = 0
    recorded = 0
    pending = 0
    for decision in run.get("decisions") or []:
        if not decision.get("requires_approval"):
            continue
        status = action_status_for_decision(
            str(decision.get("order_id") or ""),
            decision.get("proposed_action"),
        )
        lifecycle = status["lifecycle_status"]
        if lifecycle == "PENDING":
            pending += 1
        elif lifecycle == "REJECTED":
            rejected += 1
            completed += 1
        elif lifecycle == "RECORDED":
            recorded += 1
            approved += 1
            completed += 1
        elif lifecycle == "APPROVED":
            approved += 1
            completed += 1
    return {
        "completed_action_count": completed,
        "approved_action_count": approved,
        "rejected_action_count": rejected,
        "recorded_action_count": recorded,
        "pending_action_count": pending,
    }


def summarize_agent_run(run: dict[str, Any]) -> dict[str, Any]:
    """History row for one run — metrics from run + live action state."""
    action_counts = _action_counts_for_run(run)
    return {
        "run_id": run.get("run_id"),
        "timestamp": run.get("completed_at") or run.get("started_at"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "records_processed": run.get("records_processed", 0),
        "no_action_count": run.get("no_action_count", 0),
        "review_required_count": run.get("review_required_count", 0),
        "pending_approval_count": action_counts["pending_action_count"],
        "unresolved_count": run.get("unresolved_count", 0),
        "decisions_by_type": dict(run.get("decisions_by_type") or {}),
        "completed_action_count": action_counts["completed_action_count"],
        "approved_action_count": action_counts["approved_action_count"],
        "rejected_action_count": action_counts["rejected_action_count"],
        "recorded_action_count": action_counts["recorded_action_count"],
        "pending_action_count": action_counts["pending_action_count"],
        "data_source": run.get("data_source"),
        "elapsed_seconds": run.get("elapsed_seconds"),
    }


def list_agent_run_history(*, limit: int = 20) -> list[dict[str, Any]]:
    """Newest-first agent run history summaries."""
    with _lock:
        if not _runs_by_id and _persist and _store_path.exists():
            _load_unlocked()
        runs = list(_runs_by_id.values())
    runs.sort(key=lambda r: str(r.get("completed_at") or r.get("started_at") or ""), reverse=True)
    return [summarize_agent_run(copy.deepcopy(r)) for r in runs[: max(1, limit)]]


def get_lifecycle_metrics(*, run_id: str | None = None) -> dict[str, Any]:
    """Batch-level lifecycle metrics for a run (latest if omitted).

    Distinguishes agent decision counts from human action status counts.
    """
    run = get_agent_run(run_id) if run_id else get_latest_agent_run()
    if run is None:
        return {
            "run_id": None,
            "total_decisions": 0,
            "no_action": 0,
            "pending_approval": 0,
            "approved": 0,
            "rejected": 0,
            "recorded": 0,
            "unresolved": 0,
            "review_required": 0,
            "decisions_by_type": {},
        }
    action_counts = _action_counts_for_run(run)
    return {
        "run_id": run.get("run_id"),
        "timestamp": run.get("completed_at") or run.get("started_at"),
        "total_decisions": run.get("records_processed", 0),
        "no_action": run.get("no_action_count", 0),
        "pending_approval": action_counts["pending_action_count"],
        "approved": action_counts["approved_action_count"],
        "rejected": action_counts["rejected_action_count"],
        "recorded": action_counts["recorded_action_count"],
        "unresolved": run.get("unresolved_count", 0),
        "review_required": run.get("review_required_count", 0),
        "decisions_by_type": dict(run.get("decisions_by_type") or {}),
    }


def get_approval_queue(*, run_id: str | None = None) -> dict[str, Any]:
    """Decisions from a run that require human approval, with live action status."""
    from finance_actions import action_status_for_decision

    run = get_agent_run(run_id) if run_id else get_latest_agent_run()
    if run is None:
        return {
            "run_id": None,
            "pending_count": 0,
            "items": [],
            "lifecycle": get_lifecycle_metrics(run_id=run_id),
        }

    items: list[dict[str, Any]] = []
    for decision in run.get("decisions") or []:
        if not decision.get("requires_approval"):
            continue
        order_id = str(decision.get("order_id") or "")
        proposed = decision.get("proposed_action")
        status = action_status_for_decision(order_id, proposed)
        items.append(
            {
                "run_id": run.get("run_id"),
                "order_id": order_id,
                "decision": decision.get("decision"),
                "rationale": decision.get("rationale"),
                "proposed_action": proposed,
                "exceptions": list(decision.get("triggered_exceptions") or []),
                "original_result": copy.deepcopy(decision.get("original_result") or {}),
                "requires_approval": True,
                "approval_status": status["approval_status"],
                "action_status": status["action_status"],
                "lifecycle_status": status["lifecycle_status"],
                "timestamp": decision.get("timestamp"),
            }
        )

    pending_count = sum(1 for i in items if i["lifecycle_status"] == "PENDING")
    return {
        "run_id": run.get("run_id"),
        "pending_count": pending_count,
        "items": items,
        "lifecycle": get_lifecycle_metrics(run_id=str(run.get("run_id"))),
    }


def find_run_id_for_order(order_id: str) -> str | None:
    """Prefer latest run that contains this order_id."""
    with _lock:
        if not _runs_by_id and _persist and _store_path.exists():
            _load_unlocked()
        runs = list(_runs_by_id.values())
    runs.sort(key=lambda r: str(r.get("completed_at") or ""), reverse=True)
    for run in runs:
        for decision in run.get("decisions") or []:
            if decision.get("order_id") == order_id:
                return str(run.get("run_id"))
    return None

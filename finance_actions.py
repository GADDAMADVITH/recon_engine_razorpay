"""Human-gated, simulated Finance Controller action records.

Architecture:

    Finance Controller Decision
            ↓
    Requires Approval?
            ↓
    Human Approval (API)
            ↓
    Simulated Action Record
            ↓
    Audit Event

RECORD-ONLY: never calls Razorpay money APIs, never moves money, never mutates
reconciliation status/amounts/confidence. The agent decision remains authoritative;
clients may only propose a decision for verification.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_agent import (
    APPROVAL_REQUIRED_DECISIONS,
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_STORE_PATH = DATA_DIR / "finance_action_records.json"

# ---------------------------------------------------------------------------
# Allowlisted simulated actions (record-only — no money movement)
# ---------------------------------------------------------------------------

ACTION_RECORD_REVIEW = "RECORD_REVIEW"
ACTION_RECORD_REFUND_VERIFICATION = "RECORD_REFUND_VERIFICATION"
ACTION_RECORD_MISSING_BANK_ESCALATION = "RECORD_MISSING_BANK_ESCALATION"
ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION = "RECORD_MISSING_SETTLEMENT_ESCALATION"

DECISION_TO_ACTION: dict[str, str] = {
    DECISION_FLAG_FOR_REVIEW: ACTION_RECORD_REVIEW,
    DECISION_VERIFY_REFUND: ACTION_RECORD_REFUND_VERIFICATION,
    DECISION_ESCALATE_MISSING_BANK: ACTION_RECORD_MISSING_BANK_ESCALATION,
    DECISION_ESCALATE_MISSING_SETTLEMENT: ACTION_RECORD_MISSING_SETTLEMENT_ESCALATION,
}

APPROVAL_PENDING = "PENDING_APPROVAL"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

ACTION_PENDING = "PENDING"
ACTION_RECORDED = "RECORDED"
ACTION_REJECTED = "REJECTED"


class FinanceActionError(Exception):
    """Domain error for approval/action workflow (maps to 4xx)."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class FinanceActionRecord:
    action_id: str
    order_id: str
    agent_decision: str
    action_type: str
    approval_required: bool
    approval_status: str
    action_status: str
    created_at: str
    approved_at: str | None
    evidence: dict[str, Any]
    audit_event: dict[str, Any] = field(default_factory=dict)
    simulated: bool = True
    money_moved: bool = False
    run_id: str | None = None
    rejected_at: str | None = None
    note: str = (
        "Simulated record-only action. ReconEngine does not move money or "
        "execute live Razorpay financial actions in this MVP."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_lock = threading.Lock()
_actions_by_key: dict[str, FinanceActionRecord] = {}
_audit_events: list[dict[str, Any]] = []
_store_path: Path = DEFAULT_STORE_PATH
_persist: bool = True


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _action_key(order_id: str, action_type: str) -> str:
    return f"{order_id}::{action_type}"


def configure_store(*, path: Path | None = None, persist: bool | None = None) -> None:
    """Test/helper hook to redirect or disable persistence."""
    global _store_path, _persist
    with _lock:
        if path is not None:
            _store_path = path
        if persist is not None:
            _persist = persist


def reset_action_store() -> None:
    """Clear in-memory action records (tests)."""
    with _lock:
        _actions_by_key.clear()
        _audit_events.clear()
        if _persist and _store_path.exists():
            _store_path.unlink()


def _load_unlocked() -> None:
    if not _persist or not _store_path.exists():
        return
    with _store_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    _actions_by_key.clear()
    known = {f.name for f in fields(FinanceActionRecord)}
    for raw in payload.get("actions") or []:
        if not isinstance(raw, dict):
            continue
        filtered = {k: v for k, v in raw.items() if k in known}
        record = FinanceActionRecord(**filtered)
        _actions_by_key[_action_key(record.order_id, record.action_type)] = record
    _audit_events.clear()
    _audit_events.extend(payload.get("audit_events") or [])


def _save_unlocked() -> None:
    if not _persist:
        return
    _store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "actions": [a.to_dict() for a in _actions_by_key.values()],
        "audit_events": list(_audit_events),
    }
    with _store_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def map_decision_to_action(decision: str) -> str:
    if decision == DECISION_NO_ACTION:
        raise FinanceActionError(
            "NO_ACTION does not require approval; there is nothing to approve.",
            status_code=400,
        )
    action = DECISION_TO_ACTION.get(decision)
    if action is None:
        raise FinanceActionError(
            f"Decision {decision!r} has no mapped simulated action.",
            status_code=400,
        )
    return action


def _evidence_snapshot(order_result: dict[str, Any], decision: Any) -> dict[str, Any]:
    """Compact evidence — never includes secrets or mutable live payment state."""
    return {
        "order_id": order_result.get("order_id"),
        "original_status": decision.original_status,
        "original_reconciled": decision.original_reconciled,
        "confidence_score": decision.confidence_score,
        "exception_types": list(decision.exception_types),
        "agent_decision": decision.decision,
        "agent_reason": decision.reason,
        "requires_approval": decision.requires_approval,
        "amount_reference": {
            "order_amount_paise": order_result.get("order_amount_paise"),
            "settlement_gross_paise": (order_result.get("amount_comparison") or {}).get(
                "settlement_gross_paise"
            ),
            "settlement_net_paise": (order_result.get("amount_comparison") or {}).get(
                "settlement_net_paise"
            ),
            "bank_amount_paise": (order_result.get("amount_comparison") or {}).get(
                "bank_amount_paise"
            ),
        },
    }


def resolve_order_result(
    *,
    order_id: str,
    order_result: dict[str, Any] | None,
    production_lookup: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve engine order_result without mutating the source."""
    if order_result is not None:
        if not isinstance(order_result, dict):
            raise FinanceActionError("order_result must be an object", status_code=400)
        provided_id = str(order_result.get("order_id") or "").strip()
        if provided_id != order_id:
            raise FinanceActionError(
                f"order_result.order_id {provided_id!r} does not match request order_id {order_id!r}",
                status_code=400,
            )
        return copy.deepcopy(order_result)

    if production_lookup is None:
        raise FinanceActionError(
            f"Order {order_id!r} not found; provide order_result or use a known production order.",
            status_code=404,
        )
    found = production_lookup.get(order_id)
    if found is None:
        raise FinanceActionError(f"Order {order_id!r} not found.", status_code=404)
    return copy.deepcopy(found)


def _verify_claimed_decision(
    *,
    order_id: str,
    claimed_agent_decision: str,
    order_result: dict[str, Any] | None,
    production_lookup: dict[str, Any] | None,
) -> tuple[dict[str, Any], Any, str]:
    """Resolve order, recompute decision, map action — never trusts client claim."""
    order_id = str(order_id or "").strip()
    if not order_id:
        raise FinanceActionError("order_id is required", status_code=400)
    claimed = str(claimed_agent_decision or "").strip()
    if not claimed:
        raise FinanceActionError("agent_decision is required", status_code=400)

    resolved = resolve_order_result(
        order_id=order_id,
        order_result=order_result,
        production_lookup=production_lookup,
    )
    decision = decide_for_order(resolved)
    if decision.decision != claimed:
        raise FinanceActionError(
            (
                f"Client agent_decision {claimed!r} does not match authoritative "
                f"Finance Controller decision {decision.decision!r}."
            ),
            status_code=409,
        )
    if decision.decision == DECISION_NO_ACTION or not decision.requires_approval:
        raise FinanceActionError(
            "NO_ACTION does not require approval; there is nothing to approve or reject.",
            status_code=400,
        )
    if decision.decision not in APPROVAL_REQUIRED_DECISIONS:
        raise FinanceActionError(
            f"Decision {decision.decision!r} is not approval-gated.",
            status_code=400,
        )
    action_type = map_decision_to_action(decision.decision)
    return resolved, decision, action_type


def _build_transition_audit(
    *,
    event_type: str,
    action_id: str,
    order_id: str,
    run_id: str | None,
    decision: Any,
    action_type: str,
    human_action: str,
    previous_state: str,
    new_state: str,
    approval_status: str,
    action_status: str,
    evidence: dict[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "action_id": action_id,
        "run_id": run_id,
        "order_id": order_id,
        "decision": decision.decision,
        "agent_decision": decision.decision,
        "proposed_action": action_type,
        "action_type": action_type,
        "human_action": human_action,
        "previous_state": previous_state,
        "new_state": new_state,
        "approval_status": approval_status,
        "action_status": action_status,
        "timestamp": timestamp,
        "evidence": evidence,
        "simulated": True,
        "money_moved": False,
    }


def approve_and_record_action(
    *,
    order_id: str,
    claimed_agent_decision: str,
    order_result: dict[str, Any] | None = None,
    production_lookup: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Human approval → simulated action record + audit event.

    State: PENDING → APPROVED/RECORDED (atomic for MVP).
    Forbidden: REJECTED → APPROVED, RECORDED → (re-approve creates idempotent replay only).
    Never trusts ``claimed_agent_decision``. Never mutates ``order_result``. Never moves money.
    """
    resolved, decision, action_type = _verify_claimed_decision(
        order_id=order_id,
        claimed_agent_decision=claimed_agent_decision,
        order_result=order_result,
        production_lookup=production_lookup,
    )
    before = copy.deepcopy(resolved)
    order_id = str(order_id).strip()
    key = _action_key(order_id, action_type)

    with _lock:
        if not _actions_by_key and _persist and _store_path.exists():
            _load_unlocked()

        existing = _actions_by_key.get(key)
        if existing is not None:
            if existing.action_status == ACTION_REJECTED or existing.approval_status == APPROVAL_REJECTED:
                raise FinanceActionError(
                    "Invalid transition: REJECTED → APPROVED is not allowed.",
                    status_code=409,
                )
            if existing.action_status == ACTION_RECORDED:
                after = copy.deepcopy(resolved)
                if before != after:
                    raise FinanceActionError(
                        "Immutability violation: order_result changed during approval.",
                        status_code=500,
                    )
                return {
                    **existing.to_dict(),
                    "idempotent_replay": True,
                    "original_result_unchanged": True,
                }

        now = _utc_now()
        evidence = _evidence_snapshot(resolved, decision)
        action_id = f"ACT_{uuid.uuid4().hex[:12]}"
        audit_event = _build_transition_audit(
            event_type="finance_action_recorded",
            action_id=action_id,
            order_id=order_id,
            run_id=run_id,
            decision=decision,
            action_type=action_type,
            human_action="APPROVE",
            previous_state=ACTION_PENDING,
            new_state=ACTION_RECORDED,
            approval_status=APPROVAL_APPROVED,
            action_status=ACTION_RECORDED,
            evidence=evidence,
            timestamp=now,
        )
        record = FinanceActionRecord(
            action_id=action_id,
            order_id=order_id,
            agent_decision=decision.decision,
            action_type=action_type,
            approval_required=True,
            approval_status=APPROVAL_APPROVED,
            action_status=ACTION_RECORDED,
            created_at=now,
            approved_at=now,
            rejected_at=None,
            evidence=evidence,
            audit_event=audit_event,
            run_id=run_id,
        )
        _actions_by_key[key] = record
        _audit_events.append(audit_event)
        _save_unlocked()

    after = copy.deepcopy(resolved)
    if before != after:
        raise FinanceActionError(
            "Immutability violation: order_result changed during approval.",
            status_code=500,
        )

    return {
        **record.to_dict(),
        "idempotent_replay": False,
        "original_result_unchanged": True,
    }


def reject_action(
    *,
    order_id: str,
    claimed_agent_decision: str,
    order_result: dict[str, Any] | None = None,
    production_lookup: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Human rejection → rejection record + audit event.

    State: PENDING → REJECTED.
    Forbidden: RECORDED → REJECTED, REJECTED → APPROVED (enforced on approve).
    Idempotent when already REJECTED. Never moves money. Never mutates order_result.
    """
    resolved, decision, action_type = _verify_claimed_decision(
        order_id=order_id,
        claimed_agent_decision=claimed_agent_decision,
        order_result=order_result,
        production_lookup=production_lookup,
    )
    before = copy.deepcopy(resolved)
    order_id = str(order_id).strip()
    key = _action_key(order_id, action_type)

    with _lock:
        if not _actions_by_key and _persist and _store_path.exists():
            _load_unlocked()

        existing = _actions_by_key.get(key)
        if existing is not None:
            if existing.action_status == ACTION_RECORDED or existing.approval_status == APPROVAL_APPROVED:
                raise FinanceActionError(
                    "Invalid transition: RECORDED/APPROVED → REJECTED is not allowed.",
                    status_code=409,
                )
            if existing.action_status == ACTION_REJECTED or existing.approval_status == APPROVAL_REJECTED:
                after = copy.deepcopy(resolved)
                if before != after:
                    raise FinanceActionError(
                        "Immutability violation: order_result changed during rejection.",
                        status_code=500,
                    )
                return {
                    **existing.to_dict(),
                    "idempotent_replay": True,
                    "original_result_unchanged": True,
                }

        now = _utc_now()
        evidence = _evidence_snapshot(resolved, decision)
        action_id = f"ACT_{uuid.uuid4().hex[:12]}"
        audit_event = _build_transition_audit(
            event_type="finance_action_rejected",
            action_id=action_id,
            order_id=order_id,
            run_id=run_id,
            decision=decision,
            action_type=action_type,
            human_action="REJECT",
            previous_state=ACTION_PENDING,
            new_state=ACTION_REJECTED,
            approval_status=APPROVAL_REJECTED,
            action_status=ACTION_REJECTED,
            evidence=evidence,
            timestamp=now,
        )
        record = FinanceActionRecord(
            action_id=action_id,
            order_id=order_id,
            agent_decision=decision.decision,
            action_type=action_type,
            approval_required=True,
            approval_status=APPROVAL_REJECTED,
            action_status=ACTION_REJECTED,
            created_at=now,
            approved_at=None,
            rejected_at=now,
            evidence=evidence,
            audit_event=audit_event,
            run_id=run_id,
        )
        _actions_by_key[key] = record
        _audit_events.append(audit_event)
        _save_unlocked()

    after = copy.deepcopy(resolved)
    if before != after:
        raise FinanceActionError(
            "Immutability violation: order_result changed during rejection.",
            status_code=500,
        )

    return {
        **record.to_dict(),
        "idempotent_replay": False,
        "original_result_unchanged": True,
    }


def get_action_for_order(
    order_id: str,
    *,
    action_type: str | None = None,
) -> dict[str, Any] | None:
    """Lookup action record for an order (optional action_type filter)."""
    with _lock:
        if not _actions_by_key and _persist and _store_path.exists():
            _load_unlocked()
        matches = [
            a.to_dict()
            for a in _actions_by_key.values()
            if a.order_id == order_id and (action_type is None or a.action_type == action_type)
        ]
    if not matches:
        return None
    # Prefer most recently created if multiple (should be rare).
    matches.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return copy.deepcopy(matches[0])


def action_status_for_decision(order_id: str, proposed_action: str | None) -> dict[str, str]:
    """Map stored action to approval/action status for queue/lifecycle views."""
    if not proposed_action:
        return {
            "approval_status": "NOT_REQUIRED",
            "action_status": "NONE",
            "lifecycle_status": "NO_ACTION",
        }
    record = get_action_for_order(order_id, action_type=proposed_action)
    if record is None:
        return {
            "approval_status": APPROVAL_PENDING,
            "action_status": ACTION_PENDING,
            "lifecycle_status": "PENDING",
        }
    approval = str(record.get("approval_status") or APPROVAL_PENDING)
    action = str(record.get("action_status") or ACTION_PENDING)
    if action == ACTION_REJECTED or approval == APPROVAL_REJECTED:
        lifecycle = "REJECTED"
    elif action == ACTION_RECORDED:
        lifecycle = "RECORDED"
    elif approval == APPROVAL_APPROVED:
        lifecycle = "APPROVED"
    else:
        lifecycle = "PENDING"
    return {
        "approval_status": approval,
        "action_status": action,
        "lifecycle_status": lifecycle,
    }


def list_action_records() -> list[dict[str, Any]]:
    with _lock:
        if not _actions_by_key and _persist and _store_path.exists():
            _load_unlocked()
        return [a.to_dict() for a in _actions_by_key.values()]


def list_audit_events() -> list[dict[str, Any]]:
    with _lock:
        if not _audit_events and _persist and _store_path.exists():
            _load_unlocked()
        return list(_audit_events)

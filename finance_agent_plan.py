"""Batch-level Finance Controller agent orchestration.

Sits downstream of the deterministic ``finance_agent.py`` policy and the
agent-run / decision-trace layer. Performs batch analysis, grouping,
deterministic prioritization, and work planning — never reclassifies
orders and never calls Gemini for decisions.

Architecture:

    Reconciliation Engine
            ↓
    Structured Audit / Evidence
            ↓
    Finance Controller Agent (deterministic policy)
            ↓
    Agent Run / Decision Trace
            ↓
    Agent Orchestration / Work Plan (this module)
            ↓
    Human Approval → Simulated Action → Audit Trail
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from finance_actions import DECISION_TO_ACTION
from finance_agent import (
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
)
from finance_agent_run import (
    proposed_action_for_decision,
    run_finance_controller_agent,
)

# Higher = more urgent. Explainable decision-class priority.
_DECISION_PRIORITY_BASE: dict[str, int] = {
    DECISION_ESCALATE_MISSING_SETTLEMENT: 90,
    DECISION_ESCALATE_MISSING_BANK: 80,
    DECISION_VERIFY_REFUND: 70,
    DECISION_FLAG_FOR_REVIEW: 60,
    DECISION_NO_ACTION: 0,
}

# Evidence-only severity boosts (capped).
_SEVERE_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "MISSING_SETTLEMENT",
        "MISSING_BANK_TRANSACTION",
        "BANK_AMOUNT_MISMATCH",
        "SETTLEMENT_AMOUNT_MISMATCH",
        "DUPLICATE_SETTLEMENT",
        "DUPLICATE_BANK_TRANSACTION",
        "ORPHAN_BANK_TRANSACTION",
        "TIMESTAMP_OUTSIDE_TOLERANCE",
        "REFUND_NOT_REFLECTED",
    }
)

_INFO_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "TIMESTAMP_WITHIN_TOLERANCE",
        "REFERENCE_VARIATION",
        "REFUND_ADJUSTED",
    }
)

AGENT_ORCHESTRATOR = "reconengine-finance-orchestrator"
AGENT_ORCHESTRATOR_VERSION = "1.0.0"


def compute_priority(trace: dict[str, Any]) -> tuple[int, str]:
    """Deterministic priority score + short explanation from evidence only."""
    decision = str(trace.get("decision") or DECISION_NO_ACTION)
    base = _DECISION_PRIORITY_BASE.get(decision, 50)  # unknown → mid FLAG-like
    exceptions = [
        str(e)
        for e in (
            trace.get("triggered_exceptions")
            or trace.get("exceptions")
            or []
        )
    ]
    original = trace.get("original_result") or {}
    confidence = int(original.get("confidence_score") or 0)

    severe = sorted(e for e in exceptions if e in _SEVERE_EXCEPTIONS)
    blocking = [e for e in exceptions if e not in _INFO_EXCEPTIONS]
    confidence_boost = max(0, (100 - confidence) // 10)
    severe_boost = min(20, 5 * len(severe))
    multi_boost = min(10, 5 * max(0, len(blocking) - 1))

    score = base + confidence_boost + severe_boost + multi_boost
    if decision == DECISION_NO_ACTION:
        score = 0

    parts = [f"decision_base={base}"]
    if confidence_boost:
        parts.append(f"low_confidence(+{confidence_boost})")
    if severe_boost:
        parts.append(f"severe_exceptions(+{severe_boost}: {', '.join(severe)})")
    if multi_boost:
        parts.append(f"multiple_blocking(+{multi_boost})")
    explanation = "; ".join(parts)
    return score, explanation


def _group_unresolved(traces: list[dict[str, Any]]) -> dict[str, Any]:
    by_decision: dict[str, list[str]] = defaultdict(list)
    by_exception: dict[str, list[str]] = defaultdict(list)
    for trace in traces:
        if trace.get("decision") == DECISION_NO_ACTION and not trace.get("requires_approval"):
            continue
        order_id = str(trace.get("order_id") or "")
        decision = str(trace.get("decision") or "")
        by_decision[decision].append(order_id)
        exceptions = list(trace.get("triggered_exceptions") or [])
        blocking = [e for e in exceptions if e not in _INFO_EXCEPTIONS]
        if not blocking:
            by_exception["UNMAPPED_OR_AMBIGUOUS"].append(order_id)
        else:
            # Primary grouping key = first severe, else first blocking (stable order).
            severe_first = [e for e in blocking if e in _SEVERE_EXCEPTIONS]
            primary = severe_first[0] if severe_first else blocking[0]
            by_exception[str(primary)].append(order_id)

    return {
        "by_decision": {k: sorted(v) for k, v in sorted(by_decision.items())},
        "by_exception": {k: sorted(v) for k, v in sorted(by_exception.items())},
        "decision_group_counts": {k: len(v) for k, v in sorted(by_decision.items())},
        "exception_group_counts": {k: len(v) for k, v in sorted(by_exception.items())},
    }


def _work_queue_item(trace: dict[str, Any]) -> dict[str, Any]:
    priority, priority_reason = compute_priority(trace)
    original = copy.deepcopy(trace.get("original_result") or {})
    exceptions = list(trace.get("triggered_exceptions") or [])
    decision = str(trace.get("decision") or "")
    proposed = trace.get("proposed_action")
    if proposed is None and decision != DECISION_NO_ACTION:
        proposed = proposed_action_for_decision(decision) or DECISION_TO_ACTION.get(decision)
    return {
        "order_id": trace.get("order_id"),
        "priority": priority,
        "priority_reason": priority_reason,
        "decision": decision,
        "exceptions": exceptions,
        "rationale": trace.get("rationale")
        or build_deterministic_rationale_from_trace(trace),
        "proposed_action": proposed,
        "requires_approval": bool(trace.get("requires_approval")),
        "original_result": original,
        "evidence_reference": {
            "order_id": original.get("order_id"),
            "status": original.get("status"),
            "reconciled": original.get("reconciled"),
            "confidence_score": original.get("confidence_score"),
            "exception_types": list(original.get("exception_types") or exceptions),
            "audit_evidence_summary": copy.deepcopy(trace.get("audit_evidence_summary") or {}),
        },
        "timestamp": trace.get("timestamp"),
    }


def build_deterministic_rationale_from_trace(trace: dict[str, Any]) -> str:
    """Fallback rationale text if a trace lacks one (should be rare)."""
    decision = str(trace.get("decision") or "")
    types = sorted(str(e) for e in (trace.get("triggered_exceptions") or []))
    if decision == DECISION_NO_ACTION:
        return "Reconciliation is successful and no blocking exception requires intervention."
    if decision == DECISION_ESCALATE_MISSING_SETTLEMENT:
        return "Settlement is missing; escalation is required."
    if decision == DECISION_ESCALATE_MISSING_BANK:
        return "Bank transaction is missing; escalation is required."
    if decision == DECISION_VERIFY_REFUND:
        return "Refund-adjusted exception detected; refund state requires verification."
    if decision == DECISION_FLAG_FOR_REVIEW:
        if any("AMOUNT_MISMATCH" in t for t in types):
            return "Amount mismatch detected; financial result requires human review."
        if types:
            return f"Exception evidence ({', '.join(types)}) requires human review."
        return "Ambiguous or unmapped reconciliation state; financial result requires human review."
    return f"Decision {decision} requires operational follow-up."


def build_batch_analysis(run: dict[str, Any]) -> dict[str, Any]:
    decisions = list(run.get("decisions") or [])
    reconciled_count = sum(
        1
        for d in decisions
        if (d.get("original_result") or {}).get("reconciled") is True
    )
    exception_count = sum(
        1 for d in decisions if (d.get("triggered_exceptions") or d.get("original_result", {}).get("exception_types"))
    )
    unresolved = int(run.get("unresolved_count") or 0)
    approval_required = sum(1 for d in decisions if d.get("requires_approval"))
    return {
        "records_processed": int(run.get("records_processed") or len(decisions)),
        "reconciled_count": reconciled_count,
        "exception_count": exception_count,
        "unresolved_count": unresolved,
        "decisions_by_type": dict(run.get("decisions_by_type") or {}),
        "approval_required_count": approval_required,
        "no_action_count": int(run.get("no_action_count") or 0),
        "review_required_count": int(run.get("review_required_count") or 0),
    }


def build_prioritized_work_queue(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Ranked unresolved / approval-gated work items (deterministic)."""
    items: list[dict[str, Any]] = []
    for trace in run.get("decisions") or []:
        if trace.get("decision") == DECISION_NO_ACTION and not trace.get("requires_approval"):
            continue
        items.append(_work_queue_item(trace))
    # Sort by priority desc, then order_id asc for stable ties.
    items.sort(key=lambda i: (-int(i["priority"]), str(i["order_id"])))
    return items


def build_agent_plan(
    *,
    batch_analysis: dict[str, Any],
    groups: dict[str, Any],
    work_queue: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bounded, auditable plan object — observations and recommendations only."""
    top = work_queue[:10]
    action_counts: dict[str, int] = defaultdict(int)
    for item in work_queue:
        action = item.get("proposed_action") or "none"
        action_counts[str(action)] += 1

    observations = [
        f"Processed {batch_analysis['records_processed']} reconciliation records.",
        f"{batch_analysis['reconciled_count']} records are reconciled; "
        f"{batch_analysis['unresolved_count']} remain unresolved for finance ops.",
        f"{batch_analysis['approval_required_count']} decisions require human approval "
        "before any simulated follow-up.",
        f"Decision mix: {batch_analysis['decisions_by_type']}.",
    ]
    if groups.get("exception_group_counts"):
        observations.append(
            f"Unresolved exception groups: {groups['exception_group_counts']}."
        )

    prioritized_work = [
        {
            "order_id": i["order_id"],
            "priority": i["priority"],
            "decision": i["decision"],
            "proposed_action": i["proposed_action"],
            "rationale": i["rationale"],
        }
        for i in top
    ]

    return {
        "objective": (
            "Close one finance-ops loop over the reconciliation batch: surface "
            "unresolved exceptions, prioritize human review, and propose only "
            "allowlisted simulated actions that require approval."
        ),
        "observations": observations,
        "prioritized_work": prioritized_work,
        "proposed_actions": [
            {"action": action, "count": count}
            for action, count in sorted(action_counts.items(), key=lambda x: (-x[1], x[0]))
        ],
        "unresolved_cases": {
            "count": batch_analysis["unresolved_count"],
            "by_decision": groups.get("decision_group_counts") or {},
            "by_exception": groups.get("exception_group_counts") or {},
        },
        "human_approval_requirements": {
            "required_count": batch_analysis["approval_required_count"],
            "rule": (
                "Every non-NO_ACTION decision requires human approval before a "
                "simulated action may be recorded. NO_ACTION has no follow-up."
            ),
            "state_machine": "PENDING → APPROVED/RECORDED | PENDING → REJECTED",
            "money_moved": False,
        },
        "provider": "deterministic_orchestration",
        "agent": AGENT_ORCHESTRATOR,
        "agent_version": AGENT_ORCHESTRATOR_VERSION,
        "classification_provider": "deterministic_policy",
        "note": (
            "Classification uses finance_agent.py only. This layer plans and "
            "prioritizes; Gemini is not used for decisions or priority."
        ),
    }


def build_finance_controller_agent_plan(
    reconciliation_results: list[dict[str, Any]] | dict[str, Any] | None = None,
    *,
    data_source: str = "production_reconciliation_report",
) -> dict[str, Any]:
    """Run agent orchestration over an existing reconciliation batch.

    Reuses ``run_finance_controller_agent`` so decision distribution matches
    the existing agent-run contract. Does not mutate order results.
    """
    before = copy.deepcopy(reconciliation_results)
    run = run_finance_controller_agent(
        reconciliation_results,
        data_source=data_source,
    )
    after = copy.deepcopy(reconciliation_results)
    if before != after:
        raise ValueError("Immutability violation: agent plan mutated reconciliation input")

    batch_analysis = build_batch_analysis(run)
    groups = _group_unresolved(list(run.get("decisions") or []))
    work_queue = build_prioritized_work_queue(run)
    agent_plan = build_agent_plan(
        batch_analysis=batch_analysis,
        groups=groups,
        work_queue=work_queue,
    )

    return {
        "run_id": run.get("run_id"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "elapsed_seconds": run.get("elapsed_seconds"),
        "records_processed": batch_analysis["records_processed"],
        "batch_analysis": batch_analysis,
        "unresolved_groups": groups,
        "prioritized_work_queue": work_queue,
        "agent_plan": agent_plan,
        "decisions_by_type": batch_analysis["decisions_by_type"],
        "unresolved_count": batch_analysis["unresolved_count"],
        "pending_approval_count": batch_analysis["approval_required_count"],
        "data_source": run.get("data_source") or data_source,
        "provider": AGENT_ORCHESTRATOR,
        "agent": AGENT_ORCHESTRATOR,
        "agent_version": AGENT_ORCHESTRATOR_VERSION,
        "classification_agent": run.get("agent"),
        "classification_provider": run.get("provider"),
        "money_moved": False,
        "simulated": True,
    }

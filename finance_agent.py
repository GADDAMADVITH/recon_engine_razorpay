"""ReconEngine Finance Controller Agent.

Bounded, auditable decision layer that consumes EXISTING reconciliation results
and structured audit evidence. It never re-runs reconciliation, never changes
engine outputs, and never invents financial facts.

Architecture:

    Reconciliation Engine  →  Structured Audit Evidence  →  Finance Controller
         →  Deterministic Policy / Guardrails  →  Agent Decision
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from audit import build_structured_audit

# ---------------------------------------------------------------------------
# Allowlisted decisions — every agent output must be one of these.
# ---------------------------------------------------------------------------

DECISION_NO_ACTION = "NO_ACTION"
DECISION_FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"
DECISION_VERIFY_REFUND = "VERIFY_REFUND"
DECISION_ESCALATE_MISSING_BANK = "ESCALATE_MISSING_BANK"
DECISION_ESCALATE_MISSING_SETTLEMENT = "ESCALATE_MISSING_SETTLEMENT"

ALLOWED_DECISIONS: frozenset[str] = frozenset(
    {
        DECISION_NO_ACTION,
        DECISION_FLAG_FOR_REVIEW,
        DECISION_VERIFY_REFUND,
        DECISION_ESCALATE_MISSING_BANK,
        DECISION_ESCALATE_MISSING_SETTLEMENT,
    }
)

# Decisions that always require human approval before any operational follow-up.
APPROVAL_REQUIRED_DECISIONS: frozenset[str] = frozenset(
    {
        DECISION_FLAG_FOR_REVIEW,
        DECISION_VERIFY_REFUND,
        DECISION_ESCALATE_MISSING_BANK,
        DECISION_ESCALATE_MISSING_SETTLEMENT,
    }
)

# Informational exceptions that do not block an otherwise reconciled order.
_INFO_EXCEPTION_TYPES: frozenset[str] = frozenset(
    {
        "TIMESTAMP_WITHIN_TOLERANCE",
        "REFERENCE_VARIATION",
        "REFUND_ADJUSTED",
    }
)

AGENT_NAME = "reconengine-finance-controller"
AGENT_VERSION = "1.0.0"


@dataclass(frozen=True)
class FinanceAgentDecision:
    """One auditable finance-controller decision for a single order."""

    order_id: str
    original_status: str
    original_reconciled: bool
    confidence_score: int
    exception_types: tuple[str, ...]
    decision: str
    action: str
    reason: str
    evidence: dict[str, Any]
    requires_approval: bool
    provider: str = "deterministic_policy"
    agent: str = AGENT_NAME
    agent_version: str = AGENT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinanceControllerBatchResult:
    """Batch-level finance controller output."""

    decisions: list[FinanceAgentDecision] = field(default_factory=list)
    records_processed: int = 0
    no_action_count: int = 0
    review_required_count: int = 0
    exception_count: int = 0
    unresolved_count: int = 0
    decisions_by_type: dict[str, int] = field(default_factory=dict)
    agent: str = AGENT_NAME
    agent_version: str = AGENT_VERSION
    provider: str = "deterministic_policy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "agent_version": self.agent_version,
            "provider": self.provider,
            "records_processed": self.records_processed,
            "no_action_count": self.no_action_count,
            "review_required_count": self.review_required_count,
            "exception_count": self.exception_count,
            "unresolved_count": self.unresolved_count,
            "decisions_by_type": dict(self.decisions_by_type),
            "decisions": [d.to_dict() for d in self.decisions],
        }


def _exception_types(order_result: dict[str, Any]) -> tuple[str, ...]:
    types: list[str] = []
    seen: set[str] = set()
    for exc in order_result.get("exceptions") or []:
        if not isinstance(exc, dict):
            continue
        exc_type = exc.get("type")
        if isinstance(exc_type, str) and exc_type and exc_type not in seen:
            seen.add(exc_type)
            types.append(exc_type)
    return tuple(types)


def _build_evidence(order_result: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    """Compact, auditable evidence snapshot derived from engine/audit output."""
    amount = audit.get("amount_summary") or {}
    references = audit.get("references") or {}
    failed_checks = [
        {
            "rule": check.get("rule"),
            "label": check.get("label"),
            "outcome": check.get("outcome"),
            "exception_type": check.get("exception_type"),
        }
        for check in (audit.get("checks") or [])
        if isinstance(check, dict) and check.get("passed") is False
    ]
    return {
        "status": audit.get("status"),
        "reconciled": audit.get("reconciled"),
        "confidence_score": audit.get("confidence_score"),
        "exception_types": list(_exception_types(order_result)),
        "exceptions": [
            {"type": e.get("type"), "message": e.get("message")}
            for e in (audit.get("exceptions") or [])
            if isinstance(e, dict)
        ],
        "failed_checks": failed_checks,
        "amount_summary": {
            "order_amount_paise": amount.get("order_amount_paise"),
            "settlement_gross_paise": amount.get("settlement_gross_paise"),
            "settlement_net_paise": amount.get("settlement_net_paise"),
            "bank_amount_paise": amount.get("bank_amount_paise"),
            "total_refund_paise": amount.get("total_refund_paise", 0),
            "settlement_gross_matches_order": amount.get("settlement_gross_matches_order"),
            "bank_matches_settlement_net": amount.get("bank_matches_settlement_net"),
            "settlement_reflects_refund": amount.get("settlement_reflects_refund"),
        },
        "references": {
            "primary_settlement_id": references.get("primary_settlement_id"),
            "valid_bank_transaction_id": references.get("valid_bank_transaction_id"),
            "refund_ids": list(references.get("refund_ids") or []),
        },
    }


def _policy_decide(
    *,
    reconciled: bool,
    exception_types: tuple[str, ...],
) -> tuple[str, str]:
    """Deterministic decision + reason from structured facts only.

    Returns (decision, reason). Unknown/ambiguous cases fail safe to
    FLAG_FOR_REVIEW.
    """
    types = set(exception_types)

    if "MISSING_SETTLEMENT" in types:
        return (
            DECISION_ESCALATE_MISSING_SETTLEMENT,
            "Order has MISSING_SETTLEMENT in engine exceptions; escalate settlement follow-up.",
        )

    if "MISSING_BANK_TRANSACTION" in types:
        return (
            DECISION_ESCALATE_MISSING_BANK,
            "Order has MISSING_BANK_TRANSACTION in engine exceptions; escalate bank follow-up.",
        )

    if "BANK_AMOUNT_MISMATCH" in types or "SETTLEMENT_AMOUNT_MISMATCH" in types:
        mismatch = (
            "BANK_AMOUNT_MISMATCH"
            if "BANK_AMOUNT_MISMATCH" in types
            else "SETTLEMENT_AMOUNT_MISMATCH"
        )
        return (
            DECISION_FLAG_FOR_REVIEW,
            f"Order has {mismatch}; flag for human review. Agent must not clear or reclassify.",
        )

    if "REFUND_NOT_REFLECTED" in types:
        return (
            DECISION_FLAG_FOR_REVIEW,
            "Order has REFUND_NOT_REFLECTED; flag for human review of refund settlement.",
        )

    if any(
        t in types
        for t in (
            "DUPLICATE_SETTLEMENT",
            "DUPLICATE_BANK_TRANSACTION",
            "ORPHAN_BANK_TRANSACTION",
            "TIMESTAMP_OUTSIDE_TOLERANCE",
        )
    ):
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
        return (
            DECISION_FLAG_FOR_REVIEW,
            f"Order has severe exception(s) {severe}; flag for human review.",
        )

    if "REFUND_ADJUSTED" in types:
        return (
            DECISION_VERIFY_REFUND,
            "Order has REFUND_ADJUSTED evidence; verify refund reflection before closing.",
        )

    if reconciled and types.issubset(_INFO_EXCEPTION_TYPES):
        if types:
            return (
                DECISION_NO_ACTION,
                "Order is reconciled with only informational exceptions; no controller action required.",
            )
        return (
            DECISION_NO_ACTION,
            "Order is reconciled with no blocking exceptions; no controller action required.",
        )

    if reconciled and not types:
        return (
            DECISION_NO_ACTION,
            "Order is reconciled with no exceptions; no controller action required.",
        )

    # Unknown / ambiguous / unreconciled without a mapped exception → fail safe.
    return (
        DECISION_FLAG_FOR_REVIEW,
        "Ambiguous or unmapped reconciliation state; fail-safe flag for human review.",
    )


def _enforce_allowlist(decision: str) -> str:
    if decision not in ALLOWED_DECISIONS:
        return DECISION_FLAG_FOR_REVIEW
    return decision


def decide_for_order(order_result: dict[str, Any]) -> FinanceAgentDecision:
    """Produce one finance-controller decision for a single engine order_result.

    Never mutates ``order_result``. Never invents amounts/status/confidence.
    """
    if not isinstance(order_result, dict):
        raise ValueError("order_result must be an object")

    order_id = str(order_result.get("order_id") or "").strip()
    if not order_id:
        raise ValueError("order_result.order_id is required")
    if "status" not in order_result or "reconciled" not in order_result:
        raise ValueError("order_result must include status and reconciled")

    # Snapshot originals — these are copied into the decision and never altered.
    original_status = str(order_result["status"])
    original_reconciled = bool(order_result["reconciled"])
    confidence_score = int(order_result.get("confidence_score") or 0)
    exception_types = _exception_types(order_result)

    audit = build_structured_audit(order_result)
    evidence = _build_evidence(order_result, audit)

    raw_decision, reason = _policy_decide(
        reconciled=original_reconciled,
        exception_types=exception_types,
    )
    decision = _enforce_allowlist(raw_decision)
    if decision != raw_decision:
        reason = (
            f"Policy rejected non-allowlisted decision {raw_decision!r}; "
            f"fail-safe {DECISION_FLAG_FOR_REVIEW}."
        )

    requires_approval = decision in APPROVAL_REQUIRED_DECISIONS
    # NO_ACTION never requires approval; all other allowlisted actions do.
    if decision == DECISION_NO_ACTION:
        requires_approval = False

    return FinanceAgentDecision(
        order_id=order_id,
        original_status=original_status,
        original_reconciled=original_reconciled,
        confidence_score=confidence_score,
        exception_types=exception_types,
        decision=decision,
        action=decision,
        reason=reason,
        evidence=evidence,
        requires_approval=requires_approval,
    )


def run_finance_controller(
    reconciliation_results: list[dict[str, Any]] | dict[str, Any],
) -> FinanceControllerBatchResult:
    """Run the finance controller over a full reconciliation batch.

    Accepts either:
    - a list of order_result dicts, or
    - a full reconciliation report dict containing ``order_results``.
    """
    if isinstance(reconciliation_results, dict):
        orders = reconciliation_results.get("order_results")
        if not isinstance(orders, list):
            raise ValueError("report must contain an order_results list")
    elif isinstance(reconciliation_results, list):
        orders = reconciliation_results
    else:
        raise ValueError("reconciliation_results must be a report dict or order list")

    decisions: list[FinanceAgentDecision] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        decisions.append(decide_for_order(order))

    decisions_by_type: dict[str, int] = {key: 0 for key in sorted(ALLOWED_DECISIONS)}
    no_action = 0
    review_required = 0
    exception_count = 0
    unresolved = 0

    for decision in decisions:
        decisions_by_type[decision.decision] = decisions_by_type.get(decision.decision, 0) + 1
        if decision.decision == DECISION_NO_ACTION:
            no_action += 1
        if decision.requires_approval:
            review_required += 1
        if decision.exception_types:
            exception_count += 1
        if decision.decision != DECISION_NO_ACTION:
            unresolved += 1

    return FinanceControllerBatchResult(
        decisions=decisions,
        records_processed=len(decisions),
        no_action_count=no_action,
        review_required_count=review_required,
        exception_count=exception_count,
        unresolved_count=unresolved,
        decisions_by_type=decisions_by_type,
    )

"""Structured audit trail builder for ReconEngine order results.

Takes the existing OrderReconciliationResult (as a dict from the report) and
produces a clean, display-friendly audit representation.  No reconciliation
logic is duplicated — this module only *reads* existing engine output.
"""

from __future__ import annotations

from typing import Any

# Friendly labels for rules the engine fires.
RULE_LABELS: dict[str, str] = {
    "RULE_1_ORDER_TO_SETTLEMENT": "Order → Settlement matching",
    "RULE_2_SETTLEMENT_TO_BANK": "Settlement → Bank matching",
    "RULE_3_REFUND_ADJUSTMENT": "Refund adjustment check",
}

# Human-readable check outcomes derived from exceptions.
CHECK_OUTCOMES: dict[str, dict[str, str]] = {
    "RULE_1_ORDER_TO_SETTLEMENT": {
        "pass": "Settlement found for order",
        "fail_MISSING_SETTLEMENT": "No settlement found for order",
        "fail_SETTLEMENT_AMOUNT_MISMATCH": "Settlement amount does not match order",
        "fail_DUPLICATE_SETTLEMENT": "Multiple settlements found (duplicate)",
    },
    "RULE_2_SETTLEMENT_TO_BANK": {
        "pass": "Bank transaction matched to settlement",
        "fail_MISSING_BANK_TRANSACTION": "No bank transaction found for settlement",
        "fail_BANK_AMOUNT_MISMATCH": "Bank amount does not match settlement net",
        "fail_TIMESTAMP_OUTSIDE_TOLERANCE": "Timestamp difference exceeds tolerance",
        "fail_DUPLICATE_BANK_TRANSACTION": "Duplicate bank transactions detected",
        "fail_REFERENCE_VARIATION": "Bank reference normalised to settlement ID (variation)",
    },
    "RULE_3_REFUND_ADJUSTMENT": {
        "pass": "Refund correctly reflected in settlement",
        "fail_REFUND_NOT_REFLECTED": "Refund not reflected in settlement gross",
    },
}


def build_structured_audit(order_result: dict[str, Any]) -> dict[str, Any]:
    """Build a structured audit payload from an engine order_result dict.

    This is a *read-only transformation* of existing engine output — it never
    re-runs reconciliation or modifies the source data.
    """
    exception_types = {exc["type"] for exc in order_result.get("exceptions", [])}
    exception_map: dict[str, dict[str, Any]] = {
        exc["type"]: exc for exc in order_result.get("exceptions", [])
    }

    # Build checks list — one per rule triggered
    checks: list[dict[str, Any]] = []
    for rule in order_result.get("rules_triggered", []):
        label = RULE_LABELS.get(rule, rule)
        outcomes = CHECK_OUTCOMES.get(rule, {})
        # Determine if this rule produced a failure exception
        failed_key: str | None = None
        for key in outcomes:
            if key.startswith("fail_"):
                exc_type = key[5:]  # strip "fail_"
                if exc_type in exception_types:
                    failed_key = key
                    break

        if failed_key:
            exc_type = failed_key[5:]
            checks.append({
                "rule": rule,
                "label": label,
                "passed": False,
                "outcome": outcomes[failed_key],
                "exception_type": exc_type,
                "exception": exception_map.get(exc_type),
            })
        else:
            checks.append({
                "rule": rule,
                "label": label,
                "passed": True,
                "outcome": outcomes.get("pass", "Check passed"),
                "exception_type": None,
                "exception": None,
            })

    # Timestamp check (promoted to a standalone check for display clarity)
    ts = order_result.get("timestamp_comparison", {})
    ts_check: dict[str, Any] | None = None
    if ts.get("within_tolerance") is not None:
        ts_check = {
            "label": "Timestamp within tolerance",
            "passed": ts["within_tolerance"],
            "difference_hours": ts.get("difference_hours"),
            "tolerance_hours": ts.get("tolerance_hours"),
        }
        if ts["within_tolerance"] is True and "TIMESTAMP_WITHIN_TOLERANCE" in exception_types:
            ts_check["outcome"] = "Within tolerance"
        elif ts["within_tolerance"] is False:
            ts_check["outcome"] = "Exceeded tolerance"

    # Amount summary for display
    amt = order_result.get("amount_comparison", {})
    amount_summary: dict[str, Any] = {
        "order_amount_paise": amt.get("order_amount_paise"),
        "settlement_gross_paise": amt.get("settlement_gross_paise"),
        "settlement_net_paise": amt.get("settlement_net_paise"),
        "bank_amount_paise": amt.get("bank_amount_paise"),
        "total_refund_paise": amt.get("total_refund_paise", 0),
        "settlement_gross_matches_order": amt.get("settlement_gross_matches_order"),
        "bank_matches_settlement_net": amt.get("bank_matches_settlement_net"),
        "settlement_reflects_refund": amt.get("settlement_reflects_refund"),
    }

    # References
    references: dict[str, Any] = {
        "settlement_ids_considered": order_result.get("settlement_ids_considered", []),
        "primary_settlement_id": order_result.get("primary_settlement_id"),
        "secondary_settlement_ids": order_result.get("secondary_settlement_ids", []),
        "bank_transaction_ids_considered": order_result.get("bank_transaction_ids_considered", []),
        "valid_bank_transaction_id": order_result.get("valid_bank_transaction_id"),
        "refund_ids": order_result.get("refund_ids", []),
        "normalized_references": order_result.get("normalized_references", {}),
    }

    return {
        "order_id": order_result["order_id"],
        "status": order_result["status"],
        "reconciled": order_result["reconciled"],
        "confidence_score": order_result["confidence_score"],
        "order_amount_paise": order_result.get("order_amount_paise"),
        "checks": checks,
        "timestamp_check": ts_check,
        "amount_summary": amount_summary,
        "references": references,
        "exceptions": order_result.get("exceptions", []),
        "timeline": order_result.get("audit_trail", []),
    }

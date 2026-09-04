"""Build grounded application context for the ReconEngine AI chatbot.

Deterministic engine output and structured audits remain the source of truth.
This module only assembles evidence for Gemini; it never changes reconciliation
outcomes.
"""

from __future__ import annotations

import re
from typing import Any

from ai_explainer import _compact_audit_for_prompt
from audit import build_structured_audit

ORDER_ID_PATTERN = re.compile(r"\bORD_\d+\b", re.IGNORECASE)

PRODUCT_KNOWLEDGE = (
    "ReconEngine is a deterministic financial reconciliation engine. "
    "It matches orders, settlements, bank transactions, and refunds using "
    "fixed rules. Confidence scores and statuses come from the engine, not AI. "
    "Gemini only explains evidence; it does not decide reconciliation outcomes. "
    "The Audit Trail shows structured rule checks and evidence for an order. "
    "Explain with AI turns that structured audit into a short business explanation "
    "without changing reconciliation facts. "
    "Bank Import lets evaluators upload a deterministic demo CSV and reconcile "
    "against production-shaped orders without waiting on live Razorpay settlements. "
    "To try the demo: Open ReconEngine → Bank Import → Load Demo CSV → "
    "Run Reconciliation → open a scenario card → Pipeline / Audit Trail → Explain with AI. "
    "The Finance Controller Agent proposes bounded advisory decisions that require human "
    "approval before a simulated action is recorded. ReconEngine does not move money."
)

LANDING_PRODUCT_KNOWLEDGE = (
    PRODUCT_KNOWLEDGE
    + " This conversation is on the public landing page. "
    "Answer product, demo, and educational questions only. "
    "Do not claim access to private customer data, live reconciliation results, "
    "specific order amounts, bank transactions, or Razorpay settlements "
    "unless those facts appear in APPLICATION_CONTEXT (they typically will not)."
)


def extract_order_id_from_text(text: str) -> str | None:
    """Return the first ORD_* token in text, or None."""
    if not text:
        return None
    match = ORDER_ID_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _summary_slice(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    exception_counts = {
        key: value
        for key, value in summary.items()
        if key
        not in {"total_orders", "reconciled_orders", "unreconciled_orders"}
        and isinstance(value, int)
        and value > 0
    }
    top_exceptions = sorted(
        exception_counts.items(), key=lambda item: item[1], reverse=True
    )[:8]
    return {
        "total_orders": summary.get("total_orders"),
        "reconciled_orders": summary.get("reconciled_orders"),
        "unreconciled_orders": summary.get("unreconciled_orders"),
        "status_counts": report.get("status_counts") or {},
        "top_exceptions": [
            {"key": key, "count": count} for key, count in top_exceptions
        ],
    }


def _find_order_result(
    report: dict[str, Any], order_id: str
) -> dict[str, Any] | None:
    target = order_id.strip().upper()
    for order in report.get("order_results") or []:
        if not isinstance(order, dict):
            continue
        if str(order.get("order_id", "")).upper() == target:
            return order
    return None


def build_chat_grounding(
    *,
    report: dict[str, Any],
    message: str,
    order_id: str | None = None,
    order_result: dict[str, Any] | None = None,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble authoritative chat grounding from engine/audit data.

    Client ``page_context`` may only contribute non-financial hints (e.g. page
    name). Any client-supplied status/amounts/confidence values are ignored.
    When ``order_result`` is provided (engine output from a bank-import run),
    structured audit is derived via ``build_structured_audit`` — the same
    read-only transform used by the existing Explain with AI path.
    """
    # Never trust financial fields from page_context.
    safe_page: dict[str, Any] = {}
    mode = None
    if isinstance(page_context, dict):
        for key in ("page", "source", "route", "mode"):
            value = page_context.get(key)
            if isinstance(value, str) and value.strip():
                safe_page[key] = value.strip()[:80]
        raw_mode = page_context.get("mode")
        if isinstance(raw_mode, str):
            mode = raw_mode.strip().lower()

    # Public landing / product-info mode: product knowledge only — no live data.
    if mode == "product_information":
        return {
            "product_knowledge": LANDING_PRODUCT_KNOWLEDGE,
            "application_summary": None,
            "page_hints": safe_page,
            "requested_order_id": None,
            "order_lookup": "none",
            "order_audit": None,
            "conversation_mode": "product_information",
        }

    resolved_order_id = (order_id or "").strip().upper() or None
    if resolved_order_id is None:
        resolved_order_id = extract_order_id_from_text(message)

    grounding: dict[str, Any] = {
        "product_knowledge": PRODUCT_KNOWLEDGE,
        "application_summary": _summary_slice(report),
        "page_hints": safe_page,
        "requested_order_id": resolved_order_id,
        "order_lookup": "none",
        "order_audit": None,
        "conversation_mode": "console",
    }

    if order_result is not None:
        if not isinstance(order_result, dict):
            raise ValueError("order_result must be an object")
        oid = str(order_result.get("order_id") or "").strip()
        if not oid:
            raise ValueError("order_result.order_id is required")
        if "status" not in order_result or "reconciled" not in order_result:
            raise ValueError("order_result must include status and reconciled")
        # Derive audit from engine order_result; ignore any parallel fake facts.
        audit = build_structured_audit(order_result)
        grounding["requested_order_id"] = audit["order_id"]
        grounding["order_lookup"] = "found"
        grounding["order_audit"] = _compact_audit_for_prompt(audit)
        return grounding

    if resolved_order_id:
        found = _find_order_result(report, resolved_order_id)
        if found is None:
            grounding["order_lookup"] = "not_found"
            grounding["order_audit"] = None
        else:
            audit = build_structured_audit(found)
            grounding["order_lookup"] = "found"
            grounding["order_audit"] = _compact_audit_for_prompt(audit)

    return grounding


def build_chat_prompt(*, message: str, grounding: dict[str, Any]) -> str:
    """Build a constrained chat prompt from grounding + user message."""
    import json

    context_json = json.dumps(grounding, separators=(",", ":"), sort_keys=True, default=str)
    landing_extra = ""
    if grounding.get("conversation_mode") == "product_information":
        landing_extra = (
            "- The user is on the public landing page (product_information mode).\n"
            "- Do not claim access to live reconciliation runs, private orders, "
            "bank rows, or Razorpay settlements.\n"
            "- Prefer product, demo-walkthrough, and educational answers.\n"
        )
    return (
        "You are ReconEngine AI, a helpful reconciliation assistant.\n"
        "You explain and answer questions. You do not make financial decisions.\n"
        "Rules:\n"
        "- APPLICATION_CONTEXT below is the only source of truth for application facts.\n"
        "- Never invent orders, transactions, amounts, statuses, confidence scores, "
        "or exceptions.\n"
        "- Never modify or reinterpret deterministic reconciliation results "
        "(status, reconciled, confidence_score, amounts, exception types).\n"
        "- If order_lookup is not_found, say the order could not be found. "
        "Do not invent it.\n"
        "- If information is unavailable in APPLICATION_CONTEXT, say it is unavailable.\n"
        "- For general educational questions (e.g. what is a settlement), "
        "you may answer from general knowledge and briefly note that.\n"
        "- For application-data questions, answer only from APPLICATION_CONTEXT.\n"
        f"{landing_extra}"
        "- Do not claim to have performed actions you did not perform.\n"
        "- Do not approve Finance Controller actions, execute refunds/captures/payouts, "
        "or move money. You are explanation/chat only.\n"
        "- Do not invent or change Finance Controller decisions.\n"
        "- Do not expose secrets, credentials, API keys, or internal URLs.\n"
        "- Do not quote or reprint APPLICATION_CONTEXT JSON.\n"
        "- Write clear plain text (short paragraphs or bullets). No markdown fences.\n"
        "- Keep answers under 180 words unless the user asks for more detail.\n\n"
        f"APPLICATION_CONTEXT:{context_json}\n\n"
        f"USER_MESSAGE:{message.strip()}\n"
    )

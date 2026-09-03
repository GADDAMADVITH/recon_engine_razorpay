"""Gemini-backed grounded explanations for structured reconciliation audits.

This module is strictly an explanation layer. Reconciliation outcomes are
authoritative and computed by recon_engine.py + audit.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# gemini-3.6-flash is valid but currently stalls/times out for this API surface under
# load. gemini-3.5-flash supports thinkingLevel=minimal and returns promptly.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
# Demo-friendly read timeout. With thinkingLevel=minimal, flash models typically
# respond in a few seconds; keep headroom for intermittent API load.
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_OUTPUT_TOKENS = 512
# One retry absorbs intermittent Gemini stalls / high-demand delays.
_MAX_ATTEMPTS = 2


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini configuration is missing or invalid."""


class GeminiServiceError(RuntimeError):
    """Raised when Gemini request/response handling fails."""


@dataclass(frozen=True)
class GeminiExplanationResult:
    """Clean explanation text plus the model that produced it."""

    explanation: str
    model: str


def _compact_audit_for_prompt(audit: dict[str, Any]) -> dict[str, Any]:
    """Shrink structured audit to the evidence Gemini needs for a short explanation."""
    checks_out: list[dict[str, Any]] = []
    for check in audit.get("checks") or []:
        if not isinstance(check, dict):
            continue
        compact_check: dict[str, Any] = {
            "rule": check.get("rule"),
            "label": check.get("label"),
            "passed": check.get("passed"),
            "outcome": check.get("outcome"),
        }
        if check.get("exception_type"):
            compact_check["exception_type"] = check.get("exception_type")
        exc = check.get("exception")
        if isinstance(exc, dict) and exc.get("message"):
            compact_check["exception_message"] = exc.get("message")
        checks_out.append(compact_check)

    exceptions_out: list[dict[str, Any]] = []
    for exc in audit.get("exceptions") or []:
        if not isinstance(exc, dict):
            continue
        exceptions_out.append(
            {
                "type": exc.get("type"),
                "message": exc.get("message"),
            }
        )

    references = audit.get("references") or {}
    amount = audit.get("amount_summary") or {}
    timestamp = audit.get("timestamp_check")

    timeline = audit.get("timeline") or []
    # Keep a short trail only — full engine logs bloat the prompt and slow generation.
    compact_timeline = timeline[-6:] if isinstance(timeline, list) else []

    return {
        "order_id": audit.get("order_id"),
        "status": audit.get("status"),
        "reconciled": audit.get("reconciled"),
        "confidence_score": audit.get("confidence_score"),
        "checks": checks_out,
        "timestamp_check": timestamp,
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
            "refund_ids": references.get("refund_ids") or [],
        },
        "exceptions": exceptions_out,
        "timeline": compact_timeline,
    }


def _build_grounded_prompt(audit: dict[str, Any]) -> str:
    """Build a short, constrained prompt using only grounded audit evidence."""
    compact = _compact_audit_for_prompt(audit)
    payload_json = json.dumps(compact, separators=(",", ":"), sort_keys=True, default=str)

    return (
        "Explain this ReconEngine reconciliation result for a business user.\n"
        "Rules:\n"
        "- The AUDIT_JSON below is the only source of truth.\n"
        "- Do not invent transactions, amounts, IDs, timestamps, or exceptions.\n"
        "- Do not change status, reconciled, or confidence_score.\n"
        "- Do not quote, echo, or reprint AUDIT_JSON.\n"
        "- Do not return markdown code fences or JSON.\n"
        "- Write plain text only in this exact shape:\n"
        "Summary:\n"
        "<1-2 sentences>\n"
        "Why:\n"
        "- <key evidence>\n"
        "What needs attention:\n"
        "- <only if unreconciled/warnings; otherwise omit this section>\n"
        "Keep the whole answer under 120 words.\n\n"
        f"AUDIT_JSON:{payload_json}\n"
    )


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Remove leading/trailing fence lines if present but not a full match.
    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_from_json_blob(text: str) -> str | None:
    """If Gemini returned JSON, pull a usable explanation field."""
    candidate = text.strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    for key in ("explanation", "text", "answer", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    summary = payload.get("summary")
    why = payload.get("why")
    attention = payload.get("what_needs_attention") or payload.get("attention")
    parts: list[str] = []
    if isinstance(summary, str) and summary.strip():
        parts.append(f"Summary:\n{summary.strip()}")
    if isinstance(why, str) and why.strip():
        parts.append(f"Why:\n{why.strip()}")
    elif isinstance(why, list):
        bullets = "\n".join(f"- {item}" for item in why if isinstance(item, str) and item.strip())
        if bullets:
            parts.append(f"Why:\n{bullets}")
    if isinstance(attention, str) and attention.strip():
        parts.append(f"What needs attention:\n{attention.strip()}")
    elif isinstance(attention, list):
        bullets = "\n".join(
            f"- {item}" for item in attention if isinstance(item, str) and item.strip()
        )
        if bullets:
            parts.append(f"What needs attention:\n{bullets}")
    if parts:
        return "\n\n".join(parts)
    return None


def _looks_like_truncated_or_leak(text: str) -> bool:
    """Detect prompt/JSON leakage or mid-token truncation."""
    compact = text.strip()
    if not compact:
        return True
    lowered = compact.lower()
    has_summary = "summary:" in lowered

    leak_markers = (
        "audit_json",
        "structured audit data",
        '"checks"',
        '"amount_summary"',
        '"timeline"',
        "```json",
    )
    if any(marker in lowered for marker in leak_markers):
        return True

    # Truncated status/JSON fragments seen in live MVP validation.
    if re.search(r"`?status`?\s*[:=]", compact) and not has_summary:
        return True
    if compact.count('"') >= 2 and not has_summary and len(compact) < 80:
        return True

    # Extremely short replies without a Summary section are not usable.
    if not has_summary and len(compact) < 24:
        return True

    # Ends mid-token with a dangling underscore / open quote and no summary.
    if not has_summary and re.search(r'(_|"\\?)\s*$', compact) and len(compact) < 120:
        return True
    return False


def normalize_explanation_text(raw: str) -> str:
    """Normalize Gemini text into a clean business explanation.

    Raises GeminiServiceError when the content is empty, leaked, or truncated junk.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise GeminiServiceError("Gemini returned an empty explanation")

    text = _strip_markdown_fences(raw)
    json_extracted = _extract_from_json_blob(text)
    if json_extracted:
        text = json_extracted

    # Drop a single leading "Explanation:" / "AI Explanation:" label.
    text = re.sub(
        r"^(?:ai\s+)?explanation\s*:\s*",
        "",
        text.strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()

    # Prefer content from Summary: onward if the model prepended chatter.
    summary_match = re.search(r"(?im)^summary\s*:", text)
    if summary_match and summary_match.start() > 0:
        text = text[summary_match.start() :].strip()

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if _looks_like_truncated_or_leak(text):
        raise GeminiServiceError(
            "Gemini returned an unusable explanation (truncated or non-text content)"
        )
    return text


def _extract_text_from_gemini_payload(payload: dict[str, Any]) -> str:
    """Collect text parts from Gemini generateContent response robustly."""
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiServiceError("Gemini response contained no candidates")

    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    finish_reason = str(candidate.get("finishReason") or candidate.get("finish_reason") or "")

    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    text_chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        # Skip explicit thought parts when present.
        if part.get("thought") is True:
            continue
        value = part.get("text")
        if isinstance(value, str) and value.strip():
            text_chunks.append(value)

    joined = "\n".join(text_chunks).strip()
    if not joined:
        raise GeminiServiceError("Gemini returned an empty explanation")

    if finish_reason.upper() in {"MAX_TOKENS", "LENGTH"} and _looks_like_truncated_or_leak(joined):
        raise GeminiServiceError(
            "Gemini response was truncated before a complete explanation was produced"
        )
    return joined


def normalize_chat_text(raw: str) -> str:
    """Normalize a chatbot reply (less strict than audit explanation shape)."""
    if not isinstance(raw, str) or not raw.strip():
        raise GeminiServiceError("Gemini returned an empty chat response")

    text = _strip_markdown_fences(raw)
    json_extracted = _extract_from_json_blob(text)
    if json_extracted:
        text = json_extracted

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    lowered = text.lower()
    leak_markers = (
        "application_context",
        "audit_json",
        '"order_audit"',
        '"amount_summary"',
        "```json",
    )
    if any(marker in lowered for marker in leak_markers):
        raise GeminiServiceError(
            "Gemini returned an unusable chat response (context leakage)"
        )
    if len(text) < 8:
        raise GeminiServiceError("Gemini returned an unusable chat response")
    return text


def _generate_with_gemini(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
    normalize=normalize_explanation_text,
) -> GeminiExplanationResult:
    """Shared Gemini generateContent call used by explain + chat."""
    resolved_api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not resolved_api_key:
        raise GeminiConfigurationError(
            "Gemini is not configured on the server (missing GEMINI_API_KEY)"
        )

    resolved_model = (model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
    resolved_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else float(os.environ.get("GEMINI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    )
    if resolved_timeout <= 0:
        raise GeminiConfigurationError("GEMINI_TIMEOUT_SECONDS must be positive")

    url = f"{GEMINI_API_BASE}/models/{resolved_model}:generateContent"
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": DEFAULT_MAX_OUTPUT_TOKENS,
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }

    timeout = httpx.Timeout(
        connect=min(10.0, resolved_timeout),
        read=resolved_timeout,
        write=min(10.0, resolved_timeout),
        pool=min(10.0, resolved_timeout),
    )

    started = time.perf_counter()
    response: httpx.Response | None = None
    last_timeout: httpx.TimeoutException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        attempt_started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    params={"key": resolved_api_key},
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
            break
        except httpx.TimeoutException as exc:
            last_timeout = exc
            attempt_ms = int((time.perf_counter() - attempt_started) * 1000)
            logger.warning(
                "gemini_timeout model=%s path=/models/%s:generateContent "
                "thinking_level=minimal attempt=%s/%s elapsed_ms=%s",
                resolved_model,
                resolved_model,
                attempt,
                _MAX_ATTEMPTS,
                attempt_ms,
            )
            if attempt >= _MAX_ATTEMPTS:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.warning(
                    "gemini_timeout_exhausted model=%s total_elapsed_ms=%s",
                    resolved_model,
                    elapsed_ms,
                )
                raise GeminiServiceError("Gemini request timed out") from exc
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "gemini_http_error model=%s elapsed_ms=%s error_type=%s",
                resolved_model,
                elapsed_ms,
                type(exc).__name__,
            )
            raise GeminiServiceError(f"Gemini request failed: {exc}") from exc

    if response is None:
        raise GeminiServiceError("Gemini request timed out") from last_timeout

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "gemini_response model=%s status=%s elapsed_ms=%s thinking_level=minimal",
        resolved_model,
        response.status_code,
        elapsed_ms,
    )

    if response.status_code >= 400:
        try:
            err_payload = response.json()
            err_msg = (
                err_payload.get("error", {}).get("message")
                or f"HTTP {response.status_code}"
            )
        except Exception:
            err_msg = f"HTTP {response.status_code}"
        raise GeminiServiceError(f"Gemini API error: {err_msg}")

    try:
        payload = response.json()
    except Exception as exc:
        raise GeminiServiceError("Gemini response was not valid JSON") from exc

    raw_text = _extract_text_from_gemini_payload(payload)
    text = normalize(raw_text)
    return GeminiExplanationResult(explanation=text, model=resolved_model)


def explain_structured_audit_with_gemini(
    audit: dict[str, Any],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> GeminiExplanationResult:
    """Generate a concise grounded explanation from structured audit data."""
    prompt = _build_grounded_prompt(audit)
    return _generate_with_gemini(
        prompt,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        normalize=normalize_explanation_text,
    )


def chat_with_gemini(
    *,
    message: str,
    grounding: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> GeminiExplanationResult:
    """Answer a chat message grounded on application context."""
    from chat_context import build_chat_prompt

    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required")

    # Deterministic short-circuit when a requested order is missing.
    if grounding.get("order_lookup") == "not_found":
        oid = grounding.get("requested_order_id") or "that order"
        return GeminiExplanationResult(
            explanation=(
                f"I could not find {oid} in the current reconciliation data. "
                "Please check the order ID, or open it from Bank Import / "
                "Reconciliation if it belongs to a different run."
            ),
            model=(model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
        )

    prompt = build_chat_prompt(message=message, grounding=grounding)
    return _generate_with_gemini(
        prompt,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        normalize=normalize_chat_text,
    )

"""Tests for ReconEngine AI chatbot endpoint and grounded context."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import api
from ai_explainer import (
    DEFAULT_GEMINI_MODEL,
    GeminiConfigurationError,
    GeminiExplanationResult,
    GeminiServiceError,
)
from api import app
from chat_context import build_chat_grounding, extract_order_id_from_text

client = TestClient(app)

CHAT_REPLY = (
    "There are currently several unreconciled orders in the latest run. "
    "The top exceptions include missing settlements and amount mismatches."
)


def test_chat_general_question(monkeypatch):
    captured: dict = {}

    def fake_chat(*, message, grounding, **_kwargs):
        captured["message"] = message
        captured["grounding"] = grounding
        return GeminiExplanationResult(explanation=CHAT_REPLY, model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post(
        "/api/v1/chat",
        json={"message": "How does reconciliation work?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == CHAT_REPLY
    assert body["provider"] == "gemini"
    assert body["model"] == DEFAULT_GEMINI_MODEL
    assert "application_summary" in captured["grounding"]
    assert "product_knowledge" in captured["grounding"]


def test_chat_with_order_id(monkeypatch):
    captured: dict = {}

    def fake_chat(*, message, grounding, **_kwargs):
        captured["grounding"] = grounding
        return GeminiExplanationResult(
            explanation="ORD_0001 reconciled successfully.",
            model=DEFAULT_GEMINI_MODEL,
        )

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Explain this order", "order_id": "ORD_0001"},
    )
    assert response.status_code == 200
    g = captured["grounding"]
    assert g["order_lookup"] == "found"
    assert g["order_audit"]["order_id"] == "ORD_0001"
    assert g["order_audit"]["reconciled"] is True


def test_chat_structured_order_context_passed_to_gemini(monkeypatch):
    captured: dict = {}

    def fake_chat(*, message, grounding, **_kwargs):
        captured["grounding"] = grounding
        return GeminiExplanationResult(explanation="ok", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    # Production CSV: ORD_0019 has BANK_AMOUNT_MISMATCH.
    response = client.post(
        "/api/v1/chat",
        json={"message": "Why is this unreconciled?", "order_id": "ORD_0019"},
    )
    assert response.status_code == 200
    audit = captured["grounding"]["order_audit"]
    assert audit is not None
    assert audit["order_id"] == "ORD_0019"
    assert audit["reconciled"] is False
    exc_types = {e.get("type") for e in audit.get("exceptions") or []}
    check_exc = {c.get("exception_type") for c in audit.get("checks") or []}
    assert "BANK_AMOUNT_MISMATCH" in exc_types or "BANK_AMOUNT_MISMATCH" in check_exc


def test_chat_ord_0002_via_order_result_contains_mismatch(monkeypatch):
    """Bank-import style: pass engine order_result for ORD_0002 mismatch."""
    captured: dict = {}

    def fake_chat(*, message, grounding, **_kwargs):
        captured["grounding"] = grounding
        return GeminiExplanationResult(explanation="mismatch", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)

    # Use production ORD_0019 payload shape via report, rename for demo ID test path.
    report = client.get("/api/v1/reconciliation/report").json()
    source = next(o for o in report["order_results"] if o["order_id"] == "ORD_0019")
    order_result = dict(source)
    order_result["order_id"] = "ORD_0002"

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Why is ORD_0002 unreconciled?",
            "order_id": "ORD_0002",
            "order_result": order_result,
        },
    )
    assert response.status_code == 200
    audit = captured["grounding"]["order_audit"]
    assert audit["order_id"] == "ORD_0002"
    assert audit["reconciled"] is False
    amount = audit.get("amount_summary") or {}
    assert amount.get("bank_matches_settlement_net") is False or any(
        (e.get("type") == "BANK_AMOUNT_MISMATCH") for e in (audit.get("exceptions") or [])
    )


def test_chat_nonexistent_order(monkeypatch):
    calls = {"n": 0}

    def fake_chat(*, message, grounding, **_kwargs):
        calls["n"] += 1
        # Production path uses chat_with_gemini short-circuit; if monkeypatched,
        # emulate the same not_found behavior.
        if grounding.get("order_lookup") == "not_found":
            return GeminiExplanationResult(
                explanation="I could not find ORD_DOES_NOT_EXIST in the current reconciliation data.",
                model=DEFAULT_GEMINI_MODEL,
            )
        return GeminiExplanationResult(explanation="unexpected", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Explain ORD_DOES_NOT_EXIST", "order_id": "ORD_DOES_NOT_EXIST"},
    )
    assert response.status_code == 200
    assert "could not find" in response.json()["message"].lower()


def test_chat_gemini_api_failure(monkeypatch):
    def fake_chat(**_kwargs):
        raise GeminiServiceError("Gemini API error: upstream unavailable")

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 502
    assert "Gemini" in response.json()["detail"]


def test_chat_gemini_timeout(monkeypatch):
    def fake_chat(**_kwargs):
        raise GeminiServiceError("Gemini request timed out")

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 502
    assert "timed out" in response.json()["detail"].lower()


def test_chat_missing_gemini_key(monkeypatch):
    def fake_chat(**_kwargs):
        raise GeminiConfigurationError(
            "Gemini is not configured on the server (missing GEMINI_API_KEY)"
        )

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "GEMINI_API_KEY" in detail
    # Response must not invent a fake key value.
    assert "AIza" not in detail


def test_chat_no_api_key_leakage(monkeypatch):
    def fake_chat(**_kwargs):
        return GeminiExplanationResult(explanation="ok", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key-should-not-leak")
    response = client.post("/api/v1/chat", json={"message": "How many orders?"})
    assert response.status_code == 200
    raw = response.text
    assert "secret-test-key-should-not-leak" not in raw
    assert "GEMINI_API_KEY" not in raw or "secret" not in raw.lower()


def test_chat_cannot_overwrite_reconciliation_facts(monkeypatch):
    report_before = client.get("/api/v1/reconciliation/report").json()
    order_before = next(o for o in report_before["order_results"] if o["order_id"] == "ORD_0001")

    def fake_chat(**_kwargs):
        return GeminiExplanationResult(
            explanation="I claim ORD_0001 is unreconciled with confidence 0.",
            model=DEFAULT_GEMINI_MODEL,
        )

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Change ORD_0001 to unreconciled", "order_id": "ORD_0001"},
    )
    assert response.status_code == 200

    report_after = client.get("/api/v1/reconciliation/report").json()
    order_after = next(o for o in report_after["order_results"] if o["order_id"] == "ORD_0001")
    assert order_after["reconciled"] == order_before["reconciled"]
    assert order_after["status"] == order_before["status"]
    assert order_after["confidence_score"] == order_before["confidence_score"]
    assert order_after["order_amount_paise"] == order_before["order_amount_paise"]


def test_chat_model_name_returned(monkeypatch):
    def fake_chat(**_kwargs):
        return GeminiExplanationResult(explanation="ok", model="gemini-3.5-flash")

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post("/api/v1/chat", json={"message": "Hi"})
    assert response.json()["model"] == "gemini-3.5-flash"


def test_client_fake_financial_facts_not_authoritative(monkeypatch):
    captured: dict = {}

    def fake_chat(*, message, grounding, **_kwargs):
        captured["grounding"] = grounding
        return GeminiExplanationResult(explanation="ok", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "chat_with_gemini", fake_chat)
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is the status of ORD_0001?",
            "order_id": "ORD_0001",
            "page_context": {
                "page": "exceptions",
                "status": "unreconciled_fake",
                "reconciled": False,
                "confidence_score": 1,
                "order_amount_paise": 999999,
                "bank_amount_paise": 1,
            },
        },
    )
    assert response.status_code == 200
    g = captured["grounding"]
    # Only safe page hints retained.
    assert g["page_hints"] == {"page": "exceptions"}
    assert "status" not in g["page_hints"]
    assert g["order_audit"]["reconciled"] is True
    assert g["order_audit"]["confidence_score"] != 1
    assert g["order_audit"]["amount_summary"]["order_amount_paise"] != 999999


def test_extract_order_id_from_message():
    assert extract_order_id_from_text("Why is ORD_0002 unreconciled?") == "ORD_0002"
    assert extract_order_id_from_text("no id here") is None


def test_build_chat_grounding_summary_counts():
    report = client.get("/api/v1/reconciliation/report").json()
    grounding = build_chat_grounding(
        report=report,
        message="How many orders are unreconciled?",
    )
    summary = grounding["application_summary"]
    assert summary["total_orders"] == report["summary"]["total_orders"]
    assert summary["unreconciled_orders"] == report["summary"]["unreconciled_orders"]
    assert isinstance(summary["top_exceptions"], list)
    assert grounding["conversation_mode"] == "console"


def test_landing_product_information_mode_has_no_live_data():
    report = client.get("/api/v1/reconciliation/report").json()
    grounding = build_chat_grounding(
        report=report,
        message="Why is ORD_0002 unreconciled?",
        order_id="ORD_0002",
        page_context={"page": "landing", "mode": "product_information"},
    )
    assert grounding["conversation_mode"] == "product_information"
    assert grounding["application_summary"] is None
    assert grounding["order_audit"] is None
    assert grounding["requested_order_id"] is None
    assert grounding["order_lookup"] == "none"
    assert grounding["page_hints"]["page"] == "landing"
    assert grounding["page_hints"]["mode"] == "product_information"


def test_chat_not_found_short_circuit_without_gemini(monkeypatch):
    """Real chat_with_gemini short-circuits before needing an API key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Import real function path through api
    from ai_explainer import chat_with_gemini as real_chat

    monkeypatch.setattr(api, "chat_with_gemini", real_chat)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Explain ORD_MISSING_XYZ", "order_id": "ORD_MISSING_XYZ"},
    )
    assert response.status_code == 200
    assert "could not find" in response.json()["message"].lower()
    assert response.json()["provider"] == "gemini"
    assert response.json()["model"] == DEFAULT_GEMINI_MODEL

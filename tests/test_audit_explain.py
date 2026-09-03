"""Tests for Gemini-backed audit explanation endpoint and response hardening."""

from __future__ import annotations

from fastapi.testclient import TestClient

import api
from ai_explainer import (
    DEFAULT_GEMINI_MODEL,
    GeminiConfigurationError,
    GeminiExplanationResult,
    GeminiServiceError,
    _compact_audit_for_prompt,
    explain_structured_audit_with_gemini,
    normalize_explanation_text,
)
from api import app

client = TestClient(app)

CLEAN_EXPLANATION = (
    "Summary:\n"
    "This order reconciled within the configured timestamp tolerance.\n\n"
    "Why:\n"
    "- Settlement and bank amounts matched the order evidence.\n"
    "- Confidence score is 100.\n"
)

MISMATCH_EXPLANATION = (
    "Summary:\n"
    "This order is unreconciled because the bank amount does not match settlement net.\n\n"
    "Why:\n"
    "- BANK_AMOUNT_MISMATCH was raised for the settlement-to-bank check.\n\n"
    "What needs attention:\n"
    "- Review the bank transaction amount against the settlement net.\n"
)


def test_audit_explanation_success(monkeypatch):
    captured: dict = {}

    def fake_explain(audit: dict, **_kwargs):
        captured["audit"] = audit
        return GeminiExplanationResult(
            explanation=CLEAN_EXPLANATION,
            model=DEFAULT_GEMINI_MODEL,
        )

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0001/audit/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "ORD_0001"
    assert body["provider"] == "gemini"
    assert body["model"] == DEFAULT_GEMINI_MODEL
    assert "Summary:" in body["explanation"]
    assert captured["audit"]["order_id"] == "ORD_0001"


def test_audit_data_passed_to_ai_service(monkeypatch):
    captured: dict = {}

    def fake_explain(audit: dict, **_kwargs):
        captured["audit"] = audit
        return GeminiExplanationResult(explanation=MISMATCH_EXPLANATION, model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0002/audit/explain")
    assert response.status_code == 200
    sent = captured["audit"]
    assert sent["order_id"] == "ORD_0002"
    assert "status" in sent
    assert "checks" in sent
    assert "amount_summary" in sent
    assert "exceptions" in sent


def test_ord_0001_reconciled_audit_shape_for_prompt():
    audit = client.get("/api/v1/reconciliation/ORD_0001/audit").json()
    assert audit["reconciled"] is True
    assert "reconciled" in audit["status"]
    compact = _compact_audit_for_prompt(audit)
    assert compact["order_id"] == "ORD_0001"
    assert "settlement_ids_considered" not in compact.get("references", {})
    assert len(json_size := __import__("json").dumps(compact)) < 4000
    assert "BANK_AMOUNT_MISMATCH" not in json_size


def test_ord_0002_style_bank_mismatch_audit_shape_for_prompt():
    # Production CSV: ORD_0002 is reconciled; ORD_0019 has BANK_AMOUNT_MISMATCH.
    audit = client.get("/api/v1/reconciliation/ORD_0019/audit").json()
    assert audit["reconciled"] is False
    compact = _compact_audit_for_prompt(audit)
    assert compact["order_id"] == "ORD_0019"
    exc_types = {e.get("type") for e in compact.get("exceptions", [])}
    check_exc = {c.get("exception_type") for c in compact.get("checks", [])}
    assert "BANK_AMOUNT_MISMATCH" in exc_types or "BANK_AMOUNT_MISMATCH" in check_exc


def test_missing_gemini_key_returns_503(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        raise GeminiConfigurationError(
            "Gemini is not configured on the server (missing GEMINI_API_KEY)"
        )

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0001/audit/explain")
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_gemini_api_failure_returns_502(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        raise GeminiServiceError("Gemini API error: upstream unavailable")

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0001/audit/explain")
    assert response.status_code == 502
    assert "Gemini API error" in response.json()["detail"]


def test_gemini_timeout_returns_502(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        raise GeminiServiceError("Gemini request timed out")

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0002/audit/explain")
    assert response.status_code == 502
    assert "timed out" in response.json()["detail"].lower()


def test_order_not_found(monkeypatch):
    called = {"value": False}

    def fake_explain(_audit: dict, **_kwargs):
        called["value"] = True
        return GeminiExplanationResult(explanation="Summary:\nNever called.", model="x")

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_DOES_NOT_EXIST/audit/explain")
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()
    assert called["value"] is False


def test_no_secret_leaks_in_response(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        return GeminiExplanationResult(explanation="Summary:\nAll good.", model=DEFAULT_GEMINI_MODEL)

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    response = client.get("/api/v1/reconciliation/ORD_0001/audit/explain")
    assert response.status_code == 200
    serialized = response.text
    assert "GEMINI_API_KEY" not in serialized
    assert "RAZORPAY_KEY_SECRET" not in serialized
    assert "test-placeholder-key" not in serialized


def test_existing_audit_endpoint_unchanged(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        return GeminiExplanationResult(explanation="Summary:\nWhatever.", model="x")

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    audit_response = client.get("/api/v1/reconciliation/ORD_0001/audit")
    assert audit_response.status_code == 200
    body = audit_response.json()
    assert "checks" in body
    assert "timeline" in body
    assert "explanation" not in body


def test_reconciliation_result_remains_unchanged(monkeypatch):
    baseline = client.get("/api/v1/reconciliation/report").json()
    baseline_order = next(r for r in baseline["order_results"] if r["order_id"] == "ORD_0001")

    def fake_explain(_audit: dict, **_kwargs):
        return GeminiExplanationResult(explanation="Summary:\nStatic explanation.", model="x")

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    _ = client.get("/api/v1/reconciliation/ORD_0001/audit/explain")

    after = client.get("/api/v1/reconciliation/report").json()
    after_order = next(r for r in after["order_results"] if r["order_id"] == "ORD_0001")
    assert baseline_order["status"] == after_order["status"]
    assert baseline_order["reconciled"] == after_order["reconciled"]
    assert baseline_order["confidence_score"] == after_order["confidence_score"]


def test_default_gemini_model_is_gemini_3_6_flash():
    assert DEFAULT_GEMINI_MODEL == "gemini-3.5-flash"


def test_normalize_clean_explanation():
    out = normalize_explanation_text(CLEAN_EXPLANATION)
    assert out.startswith("Summary:")
    assert "timestamp tolerance" in out.lower()


def test_normalize_markdown_fenced_explanation():
    raw = "```markdown\nExplanation:\nSummary:\nOrder reconciled.\n\nWhy:\n- Amounts matched.\n```"
    out = normalize_explanation_text(raw)
    assert "```" not in out
    assert out.startswith("Summary:")
    assert "Amounts matched" in out


def test_normalize_json_explanation_object():
    raw = (
        '{"summary":"Order is unreconciled.",'
        '"why":["Bank amount mismatch"],'
        '"what_needs_attention":["Review bank amount"]}'
    )
    out = normalize_explanation_text(raw)
    assert "Summary:" in out
    assert "Bank amount mismatch" in out
    assert "Review bank amount" in out


def test_normalize_rejects_truncated_status_fragment():
    try:
        normalize_explanation_text('status`: `"reconciled_within_')
        assert False, "expected GeminiServiceError"
    except GeminiServiceError as exc:
        assert "unusable" in str(exc).lower() or "truncated" in str(exc).lower()


def test_normalize_rejects_audit_json_leak():
    try:
        normalize_explanation_text('Here is AUDIT_JSON:{"order_id":"ORD_0001","checks":[]}')
        assert False, "expected GeminiServiceError"
    except GeminiServiceError:
        pass


def _fake_http_client(payload: dict, *, captured: dict | None = None):
    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            if captured is not None:
                captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def post(self, url, params=None, json=None, headers=None):
            if captured is not None:
                captured["url"] = url
                captured["json"] = json
                captured["params_keys"] = sorted((params or {}).keys())
            return FakeResponse()

    return FakeClient


def test_gemini_request_payload_has_no_thinking_config(monkeypatch):
    """Regression: use thinkingLevel=minimal; never send thinkingBudget/temperature/topP."""
    captured: dict = {}
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": CLEAN_EXPLANATION}]},
                }
            ]
        },
        captured=captured,
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    explain_structured_audit_with_gemini(
        {
            "order_id": "ORD_0001",
            "status": "reconciled_within_timestamp_tolerance",
            "reconciled": True,
            "confidence_score": 100,
            "checks": [],
            "exceptions": [],
            "timeline": [],
            "amount_summary": {},
            "references": {},
        },
        api_key="test-placeholder-key",
    )

    body = captured["json"]
    assert set(body.keys()) == {"contents", "generationConfig"}
    assert body["contents"][0]["role"] == "user"
    assert isinstance(body["contents"][0]["parts"][0]["text"], str)
    assert body["contents"][0]["parts"][0]["text"].startswith(
        "Explain this ReconEngine reconciliation result"
    )

    gen = body["generationConfig"]
    assert set(gen.keys()) == {"maxOutputTokens", "thinkingConfig"}
    assert gen["maxOutputTokens"] == 512
    assert gen["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert "thinkingBudget" not in gen["thinkingConfig"]
    assert "temperature" not in gen
    assert "topP" not in gen
    assert captured["url"].endswith("/models/gemini-3.5-flash:generateContent")


def test_gemini_request_uses_default_model_and_returns_model(monkeypatch):
    captured: dict = {}
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": CLEAN_EXPLANATION}]},
                }
            ]
        },
        captured=captured,
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    result = explain_structured_audit_with_gemini(
        {"order_id": "ORD_0001", "status": "reconciled", "reconciled": True},
        api_key="test-placeholder-key",
    )
    assert isinstance(result, GeminiExplanationResult)
    assert result.model == "gemini-3.5-flash"
    assert result.explanation.startswith("Summary:")
    assert captured["url"].endswith("/models/gemini-3.5-flash:generateContent")
    assert "gemini-2.5-flash" not in captured["url"]
    assert captured["params_keys"] == ["key"]
    prompt = captured["json"]["contents"][0]["parts"][0]["text"]
    assert "AUDIT_JSON:" in prompt
    assert "Do not quote, echo, or reprint AUDIT_JSON" in prompt
    assert captured["json"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"
    assert "temperature" not in captured["json"]["generationConfig"]
    assert "topP" not in captured["json"]["generationConfig"]
    assert "thinkingBudget" not in captured["json"]["generationConfig"]["thinkingConfig"]


def test_gemini_model_env_override(monkeypatch):
    captured: dict = {}
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": "Summary:\nOverride."}]}}
            ]
        },
        captured=captured,
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom-test-model")
    result = explain_structured_audit_with_gemini(
        {"order_id": "ORD_0001"},
        api_key="test-placeholder-key",
    )
    assert result.model == "gemini-custom-test-model"
    assert result.explanation.startswith("Summary:")
    assert captured["url"].endswith("/models/gemini-custom-test-model:generateContent")


def test_gemini_parses_markdown_response_from_api(monkeypatch):
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "```\nExplanation:\nSummary:\nReconciled cleanly.\n\n"
                                    "Why:\n- Settlement matched order.\n```"
                                )
                            }
                        ]
                    },
                }
            ]
        }
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    result = explain_structured_audit_with_gemini(
        {"order_id": "ORD_0001", "reconciled": True},
        api_key="test-placeholder-key",
    )
    assert "```" not in result.explanation
    assert result.explanation.startswith("Summary:")
    assert "Settlement matched order" in result.explanation


def test_gemini_parses_json_response_from_api(monkeypatch):
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"explanation":"Summary:\\nBank mismatch found.\\n\\n'
                                    'Why:\\n- BANK_AMOUNT_MISMATCH"}'
                                )
                            }
                        ]
                    },
                }
            ]
        }
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    result = explain_structured_audit_with_gemini(
        {"order_id": "ORD_0002", "reconciled": False},
        api_key="test-placeholder-key",
    )
    assert "BANK_AMOUNT_MISMATCH" in result.explanation
    assert result.explanation.startswith("Summary:")


def test_gemini_rejects_truncated_live_style_fragment(monkeypatch):
    FakeClient = _fake_http_client(
        {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {"parts": [{"text": 'status`: `"reconciled_within_'}]},
                }
            ]
        }
    )
    monkeypatch.setattr("ai_explainer.httpx.Client", FakeClient)
    try:
        explain_structured_audit_with_gemini(
            {"order_id": "ORD_0001"},
            api_key="test-placeholder-key",
        )
        assert False, "expected GeminiServiceError"
    except GeminiServiceError as exc:
        assert "truncated" in str(exc).lower() or "unusable" in str(exc).lower()


def test_gemini_timeout_propagates(monkeypatch):
    calls = {"n": 0}

    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            raise __import__("httpx").TimeoutException("read timed out")

    monkeypatch.setattr("ai_explainer.httpx.Client", TimeoutClient)
    try:
        explain_structured_audit_with_gemini(
            {"order_id": "ORD_0002"},
            api_key="test-placeholder-key",
            timeout_seconds=0.01,
        )
        assert False, "expected GeminiServiceError"
    except GeminiServiceError as exc:
        assert "timed out" in str(exc).lower()
    assert calls["n"] == 2  # one retry after first timeout


def test_gemini_retries_once_after_timeout(monkeypatch):
    calls = {"n": 0}

    class FlakyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise __import__("httpx").TimeoutException("read timed out")

            class FakeResponse:
                status_code = 200

                def json(self):
                    return {
                        "candidates": [
                            {
                                "finishReason": "STOP",
                                "content": {"parts": [{"text": CLEAN_EXPLANATION}]},
                            }
                        ]
                    }

            return FakeResponse()

    monkeypatch.setattr("ai_explainer.httpx.Client", FlakyClient)
    result = explain_structured_audit_with_gemini(
        {"order_id": "ORD_0001"},
        api_key="test-placeholder-key",
        timeout_seconds=0.01,
    )
    assert calls["n"] == 2
    assert result.explanation.startswith("Summary:")
    assert result.model == "gemini-3.5-flash"


def test_endpoint_model_field_populated(monkeypatch):
    def fake_explain(_audit: dict, **_kwargs):
        return GeminiExplanationResult(
            explanation=CLEAN_EXPLANATION,
            model="gemini-3.5-flash",
        )

    monkeypatch.setattr(api, "explain_structured_audit_with_gemini", fake_explain)
    body = client.get("/api/v1/reconciliation/ORD_0001/audit/explain").json()
    assert body["model"] == "gemini-3.5-flash"
    assert body["model"] is not None

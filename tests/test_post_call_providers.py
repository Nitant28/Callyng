"""Unit tests for multi-protocol post-call LLM dispatch.

These are pure unit tests: they never hit the network. They must pass under the
CI suite (session-scoped asyncio loop + autouse Postgres/Redis conftest) and
must not depend on keys loaded from a local ``.env``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from post_call_extract import (
    extract_post_call,
    post_call_llm_configured,
    post_call_missing_key_message,
    post_call_provider,
)

_MIN_SCHEMA = {
    "mode": "fields",
    "fields": [{"name": "intent_status", "type": "string"}],
}

_TRANSCRIPT = [{"role": "user", "content": "interested"}]

_PROVIDER_ENV_KEYS = (
    "POST_CALL_PROVIDER",
    "POST_CALL_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GOOGLE_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear provider-related env so local `.env` / CI secrets cannot leak."""
    for key in _PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _post_json_mock(capture: dict[str, Any], payload: dict[str, Any]):
    async def _fake(
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_sec: float,
    ) -> tuple[Any, None]:
        capture["url"] = url
        capture["headers"] = dict(headers)
        capture["body"] = body
        capture["timeout_sec"] = timeout_sec
        return payload, None

    return _fake


@pytest.mark.asyncio
async def test_openai_compat_uses_base_url_and_bearer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("POST_CALL_MODEL", "meta-llama/test")

    capture: dict[str, Any] = {}
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"intent_status": "Interested"})}}
        ]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        parsed, err, model = await extract_post_call(
            _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
        )

    assert err is None
    assert parsed == {"intent_status": "Interested"}
    assert model == "meta-llama/test"
    assert capture["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert capture["headers"]["Authorization"] == "Bearer sk-test"
    assert capture["body"]["messages"][0]["role"] == "system"
    assert capture["body"]["messages"][1]["role"] == "user"
    assert capture["body"]["model"] == "meta-llama/test"
    assert capture["body"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_openai_falls_back_to_groq_key_and_default_url(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    capture: dict[str, Any] = {}
    payload = {
        "choices": [{"message": {"content": '{"intent_status":"Unknown"}'}}]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        parsed, err, _ = await extract_post_call(
            _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
        )

    assert err is None
    assert parsed["intent_status"] == "Unknown"
    assert capture["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert capture["headers"]["Authorization"] == "Bearer gsk-test"


@pytest.mark.asyncio
async def test_openai_prefers_openai_key_over_groq(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-preferred")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-ignored")

    capture: dict[str, Any] = {}
    payload = {
        "choices": [{"message": {"content": '{"intent_status":"Interested"}'}}]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        await extract_post_call(_TRANSCRIPT, extraction_schema=_MIN_SCHEMA)

    assert capture["headers"]["Authorization"] == "Bearer sk-preferred"



@pytest.mark.asyncio
async def test_groq_provider_prefers_groq_key_over_openai(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "groq")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ignored")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-preferred")

    capture: dict[str, Any] = {}
    payload = {
        "choices": [{"message": {"content": '{"intent_status":"Interested"}'}}]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        await extract_post_call(_TRANSCRIPT, extraction_schema=_MIN_SCHEMA)

    assert capture["headers"]["Authorization"] == "Bearer gsk-preferred"


@pytest.mark.asyncio
async def test_anthropic_messages_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    monkeypatch.setenv("POST_CALL_MODEL", "claude-test")

    capture: dict[str, Any] = {}
    payload = {
        "content": [
            {"type": "text", "text": json.dumps({"intent_status": "Interested"})}
        ]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        parsed, err, model = await extract_post_call(
            _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
        )

    assert err is None
    assert parsed == {"intent_status": "Interested"}
    assert model == "claude-test"
    assert capture["url"] == "https://api.anthropic.com/v1/messages"
    assert capture["headers"]["x-api-key"] == "sk-ant-test"
    assert capture["headers"]["anthropic-version"] == "2023-06-01"
    assert isinstance(capture["body"]["system"], str)
    assert len(capture["body"]["system"]) > 0
    assert capture["body"]["messages"][0]["role"] == "user"
    assert "Extract the JSON object" in capture["body"]["messages"][0]["content"]
    assert "system" not in {m["role"] for m in capture["body"]["messages"]}
    assert capture["body"]["max_tokens"] == 4096
    assert capture["body"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_gemini_generate_content_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test")
    monkeypatch.setenv("POST_CALL_MODEL", "models/gemini-2.0-flash")

    capture: dict[str, Any] = {}
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps({"intent_status": "Interested"})}
                    ]
                }
            }
        ]
    }
    with patch(
        "post_call_extract._post_json",
        new=AsyncMock(side_effect=_post_json_mock(capture, payload)),
    ):
        parsed, err, model = await extract_post_call(
            _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
        )

    assert err is None
    assert parsed == {"intent_status": "Interested"}
    assert model == "models/gemini-2.0-flash"
    assert capture["url"].startswith(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent?"
    )
    assert "key=google-test" in capture["url"]
    assert "systemInstruction" in capture["body"]
    assert capture["body"]["contents"][0]["role"] == "user"
    assert capture["body"]["generationConfig"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_unsupported_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "cohere")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    parsed, err, _ = await extract_post_call(
        _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
    )
    assert parsed is None
    assert err is not None
    assert "unsupported POST_CALL_PROVIDER" in err


def test_post_call_llm_configured_per_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    assert post_call_provider() == "openai"
    assert not post_call_llm_configured()
    assert "OPENAI_API_KEY or GROQ_API_KEY" in post_call_missing_key_message()

    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    assert post_call_llm_configured()

    monkeypatch.setenv("POST_CALL_PROVIDER", "anthropic")
    assert not post_call_llm_configured()
    assert post_call_missing_key_message() == "ANTHROPIC_API_KEY not configured"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    assert post_call_llm_configured()

    monkeypatch.setenv("POST_CALL_PROVIDER", "gemini")
    assert not post_call_llm_configured()
    assert post_call_missing_key_message() == "GOOGLE_API_KEY not configured"
    monkeypatch.setenv("GOOGLE_API_KEY", "gkey")
    assert post_call_llm_configured()


@pytest.mark.asyncio
async def test_missing_key_skips_without_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    parsed, err, model = await extract_post_call(
        _TRANSCRIPT, extraction_schema=_MIN_SCHEMA, model="m"
    )
    assert parsed is None
    assert err is None
    assert model == "m"


@pytest.mark.asyncio
async def test_llm_http_error_returned(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POST_CALL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def _fail(*_a: Any, **_k: Any) -> tuple[None, str]:
        return None, "LLM HTTP 503: overloaded"

    with patch("post_call_extract._post_json", new=AsyncMock(side_effect=_fail)):
        parsed, err, _ = await extract_post_call(
            _TRANSCRIPT, extraction_schema=_MIN_SCHEMA
        )

    assert parsed is None
    assert err == "LLM HTTP 503: overloaded"

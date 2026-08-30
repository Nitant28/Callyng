"""Unit tests for cascade transfer/live-tool tool registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_cascade import cascade_tool_schemas
from script_runtime import CascadeRuntime, build_live_tool_schemas


def _runtime(**overrides) -> CascadeRuntime:
    kwargs = {
        "script_id": "x",
        "source": "script_config",
        "system_prompt": "hi",
        "extraction_schema": {},
        "stt_provider": "sarvam",
        "stt_model": "saaras:v3",
        "stt_settings": {},
        "llm_provider": "groq",
        "llm_model": "openai/gpt-oss-120b",
        "llm_settings": {},
        "tts_provider": "cartesia",
        "tts_model": "sonic-3.5",
        "tts_voice": "",
        "tts_settings": {},
        "push_lead_data_schema": None,
        "live_tools": [],
        "live_tools_enabled": False,
        "transfer_enabled": False,
        "transfer_number": "",
    }
    kwargs.update(overrides)
    return CascadeRuntime(**kwargs)


_PUSH_TOOL = {
    "name": "push_lead_data",
    "description": "Save lead data",
    "properties": {"intent_status": {"type": "string"}},
    "required": ["intent_status"],
}


def test_end_call_always_registered():
    names = {s.name for s in cascade_tool_schemas(_runtime())}
    assert names == {"end_call"}


def test_live_tools_only_when_enabled():
    runtime = _runtime(live_tools=[_PUSH_TOOL], live_tools_enabled=False)
    names = {s.name for s in cascade_tool_schemas(runtime)}
    assert "push_lead_data" not in names
    runtime_on = _runtime(live_tools=[_PUSH_TOOL], live_tools_enabled=True)
    names_on = {s.name for s in cascade_tool_schemas(runtime_on)}
    assert names_on == {"end_call", "push_lead_data"}


def test_transfer_call_only_when_enabled_with_number():
    runtime = _runtime(transfer_enabled=True, transfer_number="")
    names = {s.name for s in cascade_tool_schemas(runtime)}
    assert "transfer_call" not in names
    runtime_on = _runtime(transfer_enabled=True, transfer_number="+919876543210")
    names_on = {s.name for s in cascade_tool_schemas(runtime_on)}
    assert names_on == {"end_call", "transfer_call"}


def test_build_live_tool_schemas_skips_reserved_and_shapeless():
    tools = [
        _PUSH_TOOL,
        {"name": "end_call", "description": "nope"},
        {"name": "lookup_slot", "description": "Find a slot"},
        {"name": "no_desc"},
    ]
    schemas = build_live_tool_schemas(tools)
    assert {s.name for s in schemas} == {"push_lead_data", "lookup_slot"}


@pytest.mark.asyncio
async def test_transfer_plivo_call_posts_aleg_url():
    from telephony import transfer_plivo_call

    session = MagicMock()
    resp = MagicMock()
    resp.status = 202
    resp.content_type = "application/json"
    resp.text = AsyncMock(return_value="{}")
    resp.json = AsyncMock(return_value={"status": "ok"})
    session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=resp),
        __aexit__=AsyncMock(return_value=None),
    )())
    # Use a proper async context manager
    class _CM:
        async def __aenter__(self):
            return resp

        async def __aexit__(self, *args):
            return None

    session.post = MagicMock(return_value=_CM())
    with patch("telephony._plivo_auth", return_value=("AID", "TOK")):
        out = await transfer_plivo_call(
            session,
            "CALL-UUID",
            "+919876543210",
            aleg_url="https://example.test/plivo-transfer-xml?session_call_id=s1",
        )
    assert out == {"status": "ok"}
    args, kwargs = session.post.call_args
    assert args[0].endswith("/Call/CALL-UUID/")
    assert "/Transfer/" not in args[0]
    assert kwargs["json"]["aleg_url"].endswith("session_call_id=s1")
    assert kwargs["json"]["aleg_method"] == "POST"
    assert kwargs["json"]["legs"] == "aleg"

"""Tests for call_transcript finalize helpers (webhook guard, row_id recovery)."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from call_log_db import (
    get_row_id_by_session,
    init_db,
    insert_call_log,
    update_call_log_extraction,
)
from pipecat.processors.aggregators.llm_context import LLMSpecificMessage

from call_transcript import (
    _build_n8n_payload,
    _message_to_turn,
    _resolve_sqlite_row_id,
    _schedule_call_completed_webhook,
    _usage_view,
    apply_transfer_outcome,
    attach_pipeline_finalize,
)
from pricing_sts import compute_sts_cost_inr


@pytest.mark.asyncio
async def test_schedule_webhook_swallows_send_failures():
    """Webhook exceptions must not propagate to the finalize caller."""
    registry: set[asyncio.Task] = set()
    from background_tasks import bind_background_tasks

    bind_background_tasks(registry)

    with patch(
        "call_transcript.send_call_completed_webhook",
        new_callable=AsyncMock,
        side_effect=RuntimeError("n8n down"),
    ):
        _schedule_call_completed_webhook({"call": {"id": 1}})
        assert len(registry) == 1
        task = next(iter(registry))
        # Let the background task complete; exception is swallowed inside _send
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
        assert task.exception() is None


@pytest.mark.asyncio
async def test_schedule_webhook_success():
    registry: set[asyncio.Task] = set()
    from background_tasks import bind_background_tasks

    bind_background_tasks(registry)
    mock_send = AsyncMock()

    with patch("call_transcript.send_call_completed_webhook", mock_send):
        payload = {"call": {"id": 42}}
        _schedule_call_completed_webhook(payload)
        task = next(iter(registry))
        await asyncio.wait_for(task, timeout=2.0)
        mock_send.assert_awaited_once_with(payload)


def test_resolve_sqlite_row_id_passthrough():
    assert _resolve_sqlite_row_id(7, "sess") == 7


def test_resolve_sqlite_row_id_recovery(tmp_path, monkeypatch):
    db = tmp_path / "call_logs.db"
    monkeypatch.setenv("CALL_LOG_DB_PATH", str(db))
    init_db(str(db))

    row_id = insert_call_log(
        session_call_id="sess-recover",
        plivo_call_id=None,
        route="sts",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:01:00+00:00",
        duration_ms=1000.0,
        transcript=[{"role": "user", "content": "hi"}],
    )
    assert row_id > 0
    recovered = _resolve_sqlite_row_id(-1, "sess-recover")
    assert recovered == row_id


def test_update_call_log_extraction_skips_invalid_row_id(tmp_path, monkeypatch):
    db = tmp_path / "call_logs.db"
    monkeypatch.setenv("CALL_LOG_DB_PATH", str(db))
    # Should not raise
    update_call_log_extraction(
        -1,
        extraction_json='{"x": 1}',
        extraction_error=None,
        extraction_model="test",
    )


def test_usage_view_includes_stt_and_audio_tokens():
    view = _usage_view(
        {
            "llm_prompt_tokens": 10,
            "llm_completion_tokens": 4,
            "llm_total_tokens": 14,
            "tts_characters": 20,
            "stt_audio_seconds": 2.5,
            "llm_input_audio_tokens": 8,
            "llm_output_audio_tokens": 6,
            "llm_cache_read_input_audio_tokens": 1,
        }
    )
    assert view["stt_audio_seconds"] == 2.5
    assert view["llm_input_audio_tokens"] == 8
    assert view["llm_output_audio_tokens"] == 6
    assert view["llm_cache_read_input_audio_tokens"] == 1


def test_usage_view_defaults_when_absent():
    view = _usage_view(None)
    assert view["stt_audio_seconds"] == 0.0
    assert view["llm_input_audio_tokens"] == 0
    assert view["llm_prompt_tokens"] == 0


def test_n8n_payload_usage_includes_new_keys():
    payload = _build_n8n_payload(
        row_id=1,
        session_call_id="s",
        plivo_call_id=None,
        route="sts",
        started_at="t0",
        ended_at="t1",
        duration_ms=1000,
        transcript=[],
        usage_prompt_tokens=10,
        usage_completion_tokens=4,
        usage_total_tokens=14,
        usage_tts_characters=20,
        usage_stt_audio_seconds=1.5,
        usage_input_audio_tokens=3,
        usage_output_audio_tokens=2,
        usage_cache_read_input_audio_tokens=1,
        cost_inr=0.1,
        extraction=None,
        extraction_error=None,
        extraction_model=None,
        post_call_extraction_skipped=True,
    )
    assert payload["usage"]["stt_audio_seconds"] == 1.5
    assert payload["usage"]["llm_input_audio_tokens"] == 3
    assert payload["usage"]["llm_output_audio_tokens"] == 2
    assert payload["usage"]["llm_cache_read_input_audio_tokens"] == 1


def test_n8n_payload_usage_defaults_new_keys_to_zero():
    payload = _build_n8n_payload(
        row_id=1,
        session_call_id="s",
        plivo_call_id=None,
        route="cascade",
        started_at="t0",
        ended_at="t1",
        duration_ms=1,
        transcript=[],
        usage_prompt_tokens=0,
        usage_completion_tokens=0,
        usage_total_tokens=0,
        usage_tts_characters=0,
        cost_inr=None,
        extraction=None,
        extraction_error=None,
        extraction_model=None,
        post_call_extraction_skipped=True,
    )
    assert payload["usage"]["stt_audio_seconds"] == 0
    assert payload["usage"]["llm_input_audio_tokens"] == 0


def test_message_to_turn_skips_llm_specific_message():
    msg = LLMSpecificMessage(llm="gemini-live", message={"x": 1})
    assert _message_to_turn(msg) is None
    assert _message_to_turn({"role": "user", "content": "hi"})["content"] == "hi"
    assert _message_to_turn({"role": "assistant", "content": "ok"})["role"] == "assistant"


def test_attach_pipeline_finalize_accepts_optional_providers():
    params = inspect.signature(attach_pipeline_finalize).parameters
    assert "providers" in params
    assert params["providers"].default is None
    assert "transfer_state" in params
    assert params["transfer_state"].default is None


def test_apply_transfer_outcome_sets_intent_status():
    assert apply_transfer_outcome({"intent_status": "Unknown"}, None) == {
        "intent_status": "Unknown"
    }
    assert apply_transfer_outcome({"intent_status": "Unknown"}, {"transferred": False}) == {
        "intent_status": "Unknown"
    }
    assert apply_transfer_outcome({"intent_status": "Unknown"}, {"transferred": True}) == {
        "intent_status": "Transferred"
    }
    assert apply_transfer_outcome(None, {"transferred": True}) == {
        "intent_status": "Transferred"
    }


def test_sts_cost_uses_only_prompt_and_completion_tokens(monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE_INPUT_USD_PER_1M", "1")
    monkeypatch.setenv("GEMINI_LIVE_OUTPUT_USD_PER_1M", "2")
    monkeypatch.setenv("USD_INR", "80")
    import inspect

    params = inspect.signature(compute_sts_cost_inr).parameters
    assert "usage_prompt_tokens" in params
    assert "usage_completion_tokens" in params
    assert "input_audio_tokens" not in params
    cost = compute_sts_cost_inr(
        "sts",
        usage_prompt_tokens=1_000_000,
        usage_completion_tokens=1_000_000,
    )
    assert cost == 240.0


def test_get_row_id_by_session(tmp_path, monkeypatch):
    db = tmp_path / "call_logs.db"
    monkeypatch.setenv("CALL_LOG_DB_PATH", str(db))
    init_db(str(db))
    assert get_row_id_by_session("missing") is None
    rid = insert_call_log(
        session_call_id="sess-a",
        plivo_call_id=None,
        route="sts",
        started_at="t0",
        ended_at="t1",
        duration_ms=1.0,
        transcript=[],
    )
    assert get_row_id_by_session("sess-a") == rid

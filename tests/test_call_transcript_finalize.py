"""Tests for call_transcript finalize helpers (webhook guard, row_id recovery)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from call_log_db import (
    get_row_id_by_session,
    init_db,
    insert_call_log,
    update_call_log_extraction,
)
from call_transcript import (
    _resolve_sqlite_row_id,
    _schedule_call_completed_webhook,
)


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

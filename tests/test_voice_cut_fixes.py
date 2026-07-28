"""Warmup Redis race + SQLite insert + prompt logging + prewarm gate tests."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_wait_for_warmup_ready_deletes_key():
    from db import warmup_state

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=["pending", "ready"])
    redis.delete = AsyncMock()

    with patch("db.warmup_state.get_redis", return_value=redis), patch(
        "db.warmup_state.asyncio.sleep", new_callable=AsyncMock
    ):
        ok = await warmup_state.wait_for_warmup("c1", timeout_s=1.0)

    assert ok is True
    redis.delete.assert_awaited()


@pytest.mark.asyncio
async def test_wait_for_warmup_timeout_leaves_pending_key():
    from db import warmup_state

    redis = AsyncMock()
    redis.get = AsyncMock(return_value="pending")
    redis.delete = AsyncMock()

    # Force an immediate deadline miss after first pending read.
    mono = iter([100.0, 100.5, 102.0, 102.0])

    with patch("db.warmup_state.get_redis", return_value=redis), patch(
        "db.warmup_state.time.monotonic", side_effect=lambda: next(mono)
    ), patch("db.warmup_state.asyncio.sleep", new_callable=AsyncMock):
        ok = await warmup_state.wait_for_warmup("c2", timeout_s=1.0)

    assert ok is False
    redis.delete.assert_not_awaited()


def test_insert_call_log_does_not_call_init_db(tmp_path, monkeypatch):
    import call_log_db

    db_path = str(tmp_path / "calls.db")
    monkeypatch.setenv("CALL_LOG_DB_PATH", db_path)
    call_log_db.init_db(db_path)

    with patch.object(call_log_db, "init_db") as init_mock:
        row_id = call_log_db.insert_call_log(
            session_call_id="s1",
            plivo_call_id="p1",
            route="sts",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:01:00+00:00",
            duration_ms=60000.0,
            transcript=[{"role": "user", "content": "hi"}],
        )
    assert row_id > 0
    init_mock.assert_not_called()

    with sqlite3.connect(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


def test_log_prompt_summary_info_is_compact():
    from script_runtime import _log_prompt_summary

    big = "X" * 30_000
    with patch("script_runtime.logger") as mock_logger:
        _log_prompt_summary(big, [{"content": "bootstrap"}])
        for call in mock_logger.info.call_args_list:
            rendered = " ".join(str(a) for a in call.args)
            assert big not in rendered
        assert mock_logger.info.call_args_list[0].args[1] == 30000
        debug_joined = " ".join(
            " ".join(str(a) for a in call.args)
            for call in mock_logger.debug.call_args_list
        )
        assert big in debug_joined


@pytest.mark.asyncio
async def test_prewarm_disabled_by_default_sets_ready(monkeypatch):
    monkeypatch.delenv("GEMINI_PREWARM", raising=False)
    monkeypatch.setenv("BOT_ROUTE", "sts")

    # Import after env so BOT_ROUTE module constant is already set; patch helper.
    import server

    set_ready = AsyncMock()
    with patch.object(server, "set_warmup_ready", set_ready), patch.object(
        server, "_gemini_prewarm_enabled", return_value=False
    ), patch("google.genai.Client") as client_cls:
        await server._prewarm_gemini("call-xyz")

    set_ready.assert_awaited_once_with("call-xyz")
    client_cls.assert_not_called()

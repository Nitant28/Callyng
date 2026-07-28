"""Unit tests for TranscriptBuffer debounced PG replace path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from call_transcript import TranscriptBuffer


class _FakeAggregator:
    """Minimal stand-in that supports Pipecat-style event_handler registration."""

    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}

    def event_handler(self, name: str):
        def decorator(fn):
            self._handlers[name] = fn
            return fn

        return decorator

    async def fire(self, name: str, *args):
        handler = self._handlers[name]
        return await handler(self, *args)


@pytest.mark.asyncio
async def test_transcript_buffer_skips_pg_without_session_id():
    buffer = TranscriptBuffer()
    user = _FakeAggregator()
    assistant = _FakeAggregator()
    buffer.register(user, assistant)

    with patch("call_transcript._pg_pool", return_value=object()), patch(
        "call_transcript._pg_write_live", new_callable=AsyncMock
    ) as mock_write:
        msg = SimpleNamespace(content="hello", timestamp="2026-01-01T00:00:00+00:00")
        await user.fire("on_user_turn_stopped", None, msg)
        await asyncio.sleep(0)

    assert len(buffer.turns) == 1
    assert buffer.turns[0]["role"] == "user"
    assert buffer._pg_flush_task is None
    mock_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcript_buffer_debounced_replace_with_session_id():
    buffer = TranscriptBuffer(session_call_id="sess-1")
    user = _FakeAggregator()
    assistant = _FakeAggregator()

    async def _consume(coro):
        if asyncio.iscoroutine(coro):
            await coro
        return None

    with patch("call_transcript._TRANSCRIPT_DEBOUNCE_S", 0.05), patch(
        "call_transcript._pg_pool", return_value="pool"
    ), patch(
        "call_transcript._pg_write_live", side_effect=_consume
    ) as mock_write, patch(
        "db.postgres.replace_transcript", new_callable=AsyncMock
    ) as replace_mock:
        buffer.register(user, assistant)
        msg = SimpleNamespace(content="hello", timestamp="2026-01-01T00:00:00+00:00")
        await user.fire("on_user_turn_stopped", None, msg)
        msg2 = SimpleNamespace(content="again", timestamp="2026-01-01T00:00:01+00:00")
        await user.fire("on_user_turn_stopped", None, msg2)

        assert len(buffer.turns) == 2
        assert buffer._pg_flush_task is not None
        await asyncio.sleep(0.15)
        if buffer._pg_flush_task and not buffer._pg_flush_task.done():
            await buffer._pg_flush_task

        assert mock_write.await_count == 1
        replace_mock.assert_called_once()
        assert replace_mock.call_args[0][1] == "sess-1"
        assert len(replace_mock.call_args[0][2]) == 2


@pytest.mark.asyncio
async def test_transcript_buffer_assistant_turn_schedules_flush():
    buffer = TranscriptBuffer(session_call_id="sess-2")
    user = _FakeAggregator()
    assistant = _FakeAggregator()

    async def _consume(coro):
        if asyncio.iscoroutine(coro):
            await coro
        return None

    with patch("call_transcript._TRANSCRIPT_DEBOUNCE_S", 0.05), patch(
        "call_transcript._pg_pool", return_value="pool"
    ), patch(
        "call_transcript._pg_write_live", side_effect=_consume
    ) as mock_write, patch(
        "db.postgres.replace_transcript", new_callable=AsyncMock
    ):
        buffer.register(user, assistant)
        msg = SimpleNamespace(
            content="namaste",
            timestamp="2026-01-01T00:00:01+00:00",
            interrupted=False,
        )
        await assistant.fire("on_assistant_turn_stopped", msg)

        assert len(buffer.turns) == 1
        assert buffer.turns[0]["role"] == "assistant"
        await asyncio.sleep(0.15)
        if buffer._pg_flush_task and not buffer._pg_flush_task.done():
            await buffer._pg_flush_task
        assert mock_write.await_count == 1

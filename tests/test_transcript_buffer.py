"""Unit tests for TranscriptBuffer real-time PG append path."""

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
        "call_transcript._pg_write", new_callable=AsyncMock
    ) as mock_write:
        msg = SimpleNamespace(content="hello", timestamp="2026-01-01T00:00:00+00:00")
        await user.fire("on_user_turn_stopped", None, msg)

    assert len(buffer.turns) == 1
    assert buffer.turns[0]["role"] == "user"
    mock_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcript_buffer_appends_pg_with_session_id():
    buffer = TranscriptBuffer(session_call_id="sess-1")
    user = _FakeAggregator()
    assistant = _FakeAggregator()

    async def _consume(coro):
        if asyncio.iscoroutine(coro):
            await coro
        return None

    with patch("call_transcript._pg_pool", return_value="pool"), patch(
        "call_transcript._pg_write", side_effect=_consume
    ) as mock_write, patch(
        "db.postgres.append_transcript_turn", new_callable=AsyncMock
    ) as append_mock:
        buffer.register(user, assistant)
        msg = SimpleNamespace(content="hello", timestamp="2026-01-01T00:00:00+00:00")
        await user.fire("on_user_turn_stopped", None, msg)

        assert len(buffer.turns) == 1
        assert buffer.turns[0]["content"] == "hello"
        assert mock_write.await_count == 1
        append_mock.assert_called_once()
        assert append_mock.call_args[0][1] == "sess-1"
        assert append_mock.call_args[0][2] == "user"
        assert append_mock.call_args[0][3] == "hello"


@pytest.mark.asyncio
async def test_transcript_buffer_assistant_turn_with_session_id():
    buffer = TranscriptBuffer(session_call_id="sess-2")
    user = _FakeAggregator()
    assistant = _FakeAggregator()

    async def _consume(coro):
        if asyncio.iscoroutine(coro):
            await coro
        return None

    with patch("call_transcript._pg_pool", return_value="pool"), patch(
        "call_transcript._pg_write", side_effect=_consume
    ) as mock_write, patch(
        "db.postgres.append_transcript_turn", new_callable=AsyncMock
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
        assert mock_write.await_count == 1

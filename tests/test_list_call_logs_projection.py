"""API / DB projection tests for voice-cut load reductions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_list_call_logs_excludes_heavy_jsonb_columns():
    from db import postgres as pg_db

    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=0)
    pool.fetch = AsyncMock(return_value=[])

    await pg_db.list_call_logs(pool, uuid4(), limit=10, offset=0)

    sql = pool.fetch.await_args.args[0]
    assert "cl.transcript" not in sql
    assert "extraction_json" not in sql
    assert "plivo_hangup_json" not in sql
    assert "cl.session_call_id" in sql
    assert "cl.in_progress" in sql
    # call_data may appear only in the is_test_call WHERE filter, not as a selected column
    assert "cl.call_data," not in sql and "cl.call_data " not in sql


@pytest.mark.asyncio
async def test_answer_exempt_from_rate_limit(client):
    """Plivo /answer must remain available; handler is marked SlowAPI-exempt."""
    import server

    assert "server.answer_xml" in server.limiter._exempt_routes
    assert "server.start_call" in server.limiter._exempt_routes
    assert "server.plivo_hangup" in server.limiter._exempt_routes
    assert "server.plivo_recording" in server.limiter._exempt_routes
    assert "server.health" in server.limiter._exempt_routes

    res = await client.get("/answer")
    assert res.status_code == 200
    assert "<Stream" in res.text

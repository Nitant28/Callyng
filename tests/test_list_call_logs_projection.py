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
    # Must not project the full transcript JSONB blob as a returned column.
    assert "cl.transcript AS" not in sql
    assert ", cl.transcript\n" not in sql
    assert "transcript_turns" in sql
    assert "COALESCE(cl.transcript" in sql
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


@pytest.mark.asyncio
async def test_list_campaign_leads_query_syntax():
    from db import postgres as pg_db

    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=0)
    pool.fetch = AsyncMock(return_value=[])

    campaign_id = uuid4()
    client_id = uuid4()
    await pg_db.list_campaign_leads(pool, campaign_id, client_id, limit=10, offset=0)

    sql = pool.fetch.await_args.args[0]
    assert "FROM leads l" in sql
    assert "LEFT JOIN LATERAL (" in sql
    assert "lc.transcript_turns" in sql
    assert "COALESCE(lc.turn_count, 0) AS turns" in sql
    assert "WHERE l.campaign_id = $1 AND l.client_id = $2" in sql


def test_public_call_detail_strips_hangup_and_storage_keys():
    from db import postgres as pg_db

    row = {
        "session_call_id": "abc",
        "transcript": [{"role": "user", "content": "hi"}],
        "extraction_json": {"intent": "x"},
        "plivo_hangup_json": {"HangupCause": "NORMAL"},
        "recording_url": "plivo:https://media.plivo.com/very-long-key",
        "call_data": {
            "setup_charge": 0.6,
            "duration_charge": 1.2,
            "is_test_call": False,
            "post_call_snapshot": {"system_instruction": "huge"},
        },
        "credits_charged": 1.8,
        "cost_usd": 0.42,
    }
    out = pg_db.public_call_detail(row)
    assert "plivo_hangup_json" not in out
    assert "recording_url" not in out
    assert "cost_usd" not in out
    assert out["has_recording"] is True
    assert out["call_data"] == {
        "setup_charge": 0.6,
        "duration_charge": 1.2,
        "is_test_call": False,
    }
    assert out["transcript"][0]["content"] == "hi"
    assert out["extraction_json"]["intent"] == "x"


@pytest.mark.asyncio
async def test_finalize_call_log_sql_includes_cost_usd():
    from db import postgres as pg_db

    pool = MagicMock()
    pool.execute = AsyncMock()

    await pg_db.finalize_call_log(
        pool,
        session_call_id="s1",
        duration_seconds=10,
        outcome="Interested",
        extraction_json={},
        billed_minutes=1,
        credits_charged=0,
        usage={"cost_usd": 0.123456},
    )

    sql = pool.execute.await_args.args[0]
    args = pool.execute.await_args.args[1:]
    assert "cost_usd" in sql
    assert "COALESCE($14, cost_usd)" in sql
    assert args[13] == 0.123456
    assert args[14] == "s1"



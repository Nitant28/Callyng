"""Tests for Redis/DB pg context recovery (Bug #4)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
from dotenv import load_dotenv
from call_transcript import resolve_pg_context

load_dotenv(override=True)


async def _db_pool():
    from db import postgres as pg_db

    try:
        return await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


async def _setup_campaign(pool):
    from db import postgres as pg_db

    client_id, _ = await pg_db.create_client(
        pool,
        f"PgCtx {uuid4().hex[:8]}",
        f"pgctx-{uuid4().hex[:8]}@test.com",
        "other",
    )
    bot_id = await pg_db.create_bot_config(
        pool,
        client_id,
        name="Test Bot",
        route="sts",
        script_id="pyramid_mr",
        telephony_number="+911234567890",
        credits_per_minute=2.5,
    )
    await pg_db.add_credits(pool, client_id, 500.0, "pytest pg context recovery")
    campaign_id = await pg_db.create_campaign(
        pool, client_id, bot_id, "PgCtx Camp", budget_credits=100.0
    )
    row = await pg_db.insert_single_lead(
        pool,
        {
            "client_id": client_id,
            "campaign_id": campaign_id,
            "phone": f"+9199{uuid4().int % 10**8:08d}",
            "name": "Recovery Lead",
        },
    )
    lead_id = UUID(str(row["id"]))
    return client_id, bot_id, campaign_id, lead_id


@pytest.mark.asyncio
async def test_resolve_pg_context_prefers_redis():

    redis_ctx = {
        "client_id": "00000000-0000-4000-8000-000000000001",
        "campaign_id": "00000000-0000-4000-8000-000000000002",
        "lead_id": "00000000-0000-4000-8000-000000000003",
        "bot_config_id": "00000000-0000-4000-8000-000000000004",
    }

    if True:
        result = await resolve_pg_context(None, "session-1", redis_ctx)
        assert result is redis_ctx


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_resolve_pg_context_from_call_log():
    from db import postgres as pg_db

    if True:
        pool = await _db_pool()
        client_id = bot_id = campaign_id = lead_id = None
        session_id = f"test-pgctx-{uuid4()}"
        try:
            client_id, bot_id, campaign_id, lead_id = await _setup_campaign(pool)
            await pg_db.insert_call_log_start(
                pool,
                session_call_id=session_id,
                client_id=client_id,
                campaign_id=campaign_id,
                lead_id=lead_id,
                bot_config_id=bot_id,
                route="sts",
                started_at=datetime.now(timezone.utc),
            )
            result = await resolve_pg_context(pool, session_id, None)
            assert result is not None
            assert result["client_id"] == str(client_id)
            assert result["campaign_id"] == str(campaign_id)
            assert result["lead_id"] == str(lead_id)
            assert result["bot_config_id"] == str(bot_id)
            assert result["route"] == "sts"
        finally:
            if client_id:
                await pool.execute(
                    "DELETE FROM call_logs WHERE session_call_id = $1", session_id
                )
                await pool.execute(
                    "DELETE FROM leads WHERE campaign_id = $1", campaign_id
                )
                await pool.execute("DELETE FROM campaigns WHERE id = $1", campaign_id)
                await pool.execute(
                    "DELETE FROM bot_configs WHERE id = $1", bot_id
                )
                await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_resolve_pg_context_returns_none_without_campaign():
    from db import postgres as pg_db

    if True:
        pool = await _db_pool()
        client_id = None
        session_id = f"test-no-camp-{uuid4()}"
        try:
            client_id, _ = await pg_db.create_client(
                pool,
                f"NoCamp {uuid4().hex[:8]}",
                f"nocamp-{uuid4().hex[:8]}@test.com",
                "other",
            )
            await pg_db.insert_call_log_start(
                pool,
                session_call_id=session_id,
                client_id=client_id,
                campaign_id=None,
                lead_id=None,
                bot_config_id=None,
                route="sts",
                started_at=datetime.now(timezone.utc),
            )
            result = await resolve_pg_context(pool, session_id, None)
            assert result is None
        finally:
            if client_id:
                await pool.execute(
                    "DELETE FROM call_logs WHERE session_call_id = $1", session_id
                )
                await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()


@pytest.mark.asyncio
async def test_no_dev_client_finalize():
    import call_transcript
    from db import postgres as pg_db

    assert not hasattr(call_transcript, "_write_pg_dev_finalize")
    assert not hasattr(call_transcript, "_DEV_CLIENT_ID")
    assert not hasattr(pg_db, "finalize_call_log_dev")

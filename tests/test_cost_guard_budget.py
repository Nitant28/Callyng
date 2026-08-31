"""CostGuard budget reservation tests (require DATABASE_URL)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from dotenv import load_dotenv

from billing import reservation_credits

load_dotenv(override=True)

_RATE = Decimal("2.5")
_SETUP = Decimal("0.60")
_R = reservation_credits(_SETUP, _RATE)  # 6.20


async def _db_pool():
    from db import postgres as pg_db

    try:
        return await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


async def _setup_campaign(pool, *, budget_credits: float, budget_used: float = 0):
    from db import postgres as pg_db

    client_id, _ = await pg_db.create_client(
        pool,
        f"CostGuard {uuid4().hex[:8]}",
        f"costguard-{uuid4().hex[:8]}@test.com",
        "other",
    )
    bot_id = await pg_db.create_bot_config(
        pool,
        client_id,
        name="Test Bot",
        route="sts",
        script_id="pyramid_mr",
        telephony_number="+911234567890",
        credits_per_minute=float(_RATE),
    )
    await pg_db.add_credits(pool, client_id, 500.0, "pytest cost guard")
    campaign_id = await pg_db.create_campaign(
        pool, client_id, bot_id, "CostGuard Camp", budget_credits=budget_credits
    )
    if budget_used:
        await pool.execute(
            "UPDATE campaigns SET budget_used_credits = $2 WHERE id = $1",
            campaign_id,
            budget_used,
        )
    return client_id, bot_id, campaign_id


async def _insert_pending_leads(pool, client_id, campaign_id, count: int):
    from db import postgres as pg_db

    leads = []
    for i in range(count):
        leads.append(
            {
                "client_id": client_id,
                "campaign_id": campaign_id,
                "phone": f"+9199{uuid4().int % 10**8:08d}",
                "name": f"Lead {i}",
            }
        )
    await pg_db.bulk_insert_leads(pool, leads)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_claim_leads_zero_when_remaining_below_r():
    from db import postgres as pg_db

    pool = await _db_pool()
    try:
        client_id, _, campaign_id = await _setup_campaign(
            pool, budget_credits=10.0, budget_used=8.0
        )
        await _insert_pending_leads(pool, client_id, campaign_id, 5)

        claimed = await pg_db.claim_leads_for_dialer(
            pool, campaign_id, client_id, slots=10
        )
        assert len(claimed) == 0
    finally:
        await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_claim_leads_caps_by_remaining_budget():
    from db import postgres as pg_db

    pool = await _db_pool()
    try:
        # remaining == one R; used should become previous + R
        previous = Decimal("10.00") - _R
        client_id, _, campaign_id = await _setup_campaign(
            pool, budget_credits=10.0, budget_used=float(previous)
        )
        await _insert_pending_leads(pool, client_id, campaign_id, 5)

        claimed = await pg_db.claim_leads_for_dialer(
            pool, campaign_id, client_id, slots=10
        )
        used = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )

        assert len(claimed) == 1
        assert Decimal(str(claimed[0]["budget_reserved_credits"])) == _R
        assert Decimal(str(used)) == previous + _R
    finally:
        await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_settle_call_budget_nets_reserved_amount():
    from db import postgres as pg_db

    pool = await _db_pool()
    try:
        client_id, _, campaign_id = await _setup_campaign(
            pool, budget_credits=100.0, budget_used=0.0
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                await pg_db.reserve_campaign_budget(
                    conn, campaign_id, client_id, _R
                )
                await pg_db.settle_call_budget(
                    conn, campaign_id, client_id, Decimal("2.50"), _R
                )

        used = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        assert Decimal(str(used)) == Decimal("2.50")
    finally:
        await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_release_lead_before_call_log_refunds_reservation():
    from db import postgres as pg_db
    from dialer.concurrent_dialer import _release_lead_to_pending

    pool = await _db_pool()
    try:
        client_id, _, campaign_id = await _setup_campaign(
            pool, budget_credits=100.0, budget_used=0.0
        )
        await _insert_pending_leads(pool, client_id, campaign_id, 1)
        claimed = await pg_db.claim_leads_for_dialer(
            pool, campaign_id, client_id, slots=1
        )
        assert len(claimed) == 1

        used_after_claim = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        assert Decimal(str(used_after_claim)) == _R

        await _release_lead_to_pending(
            pool, claimed[0], campaign_id, client_id
        )

        used_after_release = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        assert Decimal(str(used_after_release)) == Decimal("0")
    finally:
        await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_settle_without_reservation_charges_actual_only():
    from db import postgres as pg_db

    pool = await _db_pool()
    try:
        client_id, _, campaign_id = await _setup_campaign(
            pool, budget_credits=100.0, budget_used=0.0
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                await pg_db.settle_call_budget(
                    conn, campaign_id, client_id, 2.5, 0
                )

        used = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        assert Decimal(str(used)) == Decimal("2.5")
    finally:
        await pool.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_budget_reserved_stored_on_call_log():
    from db import postgres as pg_db

    pool = await _db_pool()
    try:
        client_id, bot_id, campaign_id = await _setup_campaign(
            pool, budget_credits=100.0
        )
        await _insert_pending_leads(pool, client_id, campaign_id, 1)
        claimed = await pg_db.claim_leads_for_dialer(
            pool, campaign_id, client_id, slots=1
        )
        lead_id = UUID(str(claimed[0]["id"]))
        session_call_id = f"test-{uuid4().hex}"

        await pg_db.insert_call_log_start(
            pool,
            session_call_id=session_call_id,
            client_id=client_id,
            campaign_id=campaign_id,
            lead_id=lead_id,
            bot_config_id=bot_id,
            route="sts",
            started_at=datetime.now(timezone.utc),
            budget_reserved_credits=claimed[0]["budget_reserved_credits"],
            credits_per_minute=claimed[0]["credits_per_minute"],
            fixed_start_credits=claimed[0]["fixed_start_credits"],
        )

        call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
        reserved = pg_db.budget_reserved_from_call_data(call_log.get("call_data"))
        assert reserved == _R
        data = call_log.get("call_data") or {}
        assert Decimal(str(data["credits_per_minute"])) == _RATE
        assert Decimal(str(data["fixed_start_credits"])) == _SETUP
    finally:
        await pool.close()

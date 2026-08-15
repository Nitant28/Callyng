import pytest
import os
import uuid
from db import postgres as pg_db

@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_settle_unanswered_call_retry():
    pool = pg_db.get_pool()
    if not pool:
        pytest.skip("No DB pool available")

    # Ephemeral setup
    client_id = uuid.uuid4()
    bot_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    call_id = uuid.uuid4()
    
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO clients (id, name, api_key_hash) VALUES ($1, 'Test', $2)", client_id, str(client_id))
            await conn.execute("INSERT INTO bot_configs (id, client_id, name, route, script_id, credits_per_minute) VALUES ($1, $2, 'Bot', 'sts', 'pyramid_hi', 1.0)", bot_id, client_id)
            await conn.execute("INSERT INTO campaigns (id, client_id, bot_config_id, name, status, max_attempts, retry_delay_minutes) VALUES ($1, $2, $3, 'Camp', 'running', 3, 10)", campaign_id, client_id, bot_id)
            await conn.execute("INSERT INTO leads (id, campaign_id, client_id, phone, status, attempts) VALUES ($1, $2, $3, '+1234567890', 'calling', 1)", lead_id, campaign_id, client_id)
            await conn.execute("INSERT INTO call_logs (session_call_id, client_id, campaign_id, bot_config_id, lead_id, in_progress) VALUES ($1, $2, $3, $4, $5, TRUE)", str(call_id), client_id, campaign_id, bot_id, lead_id)
            
        call_log = {
            "session_call_id": str(call_id),
            "lead_id": str(lead_id),
            "campaign_id": str(campaign_id),
            "client_id": str(client_id),
            "call_data": {}
        }
        
        # Action
        await pg_db.settle_unanswered_call(pool, call_log, retry_delay_minutes=10, base_outcome="Busy")
        
        # Assertions
        async with pool.acquire() as conn:
            lead_row = await conn.fetchrow("SELECT status, outcome, next_attempt_at, attempts FROM leads WHERE id = $1", lead_id)
            assert lead_row["status"] == "callback_scheduled"
            assert lead_row["outcome"] == "Busy"
            assert lead_row["next_attempt_at"] is not None
            assert lead_row["attempts"] == 1
            sched = await conn.fetchval(
                "SELECT scheduled_callback_at FROM leads WHERE id = $1", lead_id
            )
            assert sched is not None
            
            call_row = await conn.fetchrow("SELECT in_progress, outcome FROM call_logs WHERE session_call_id = $1", str(call_id))
            assert not call_row["in_progress"]
            assert call_row["outcome"] == "Busy"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM clients WHERE id = $1", client_id)

@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_settle_unanswered_call_exhaustion():
    pool = pg_db.get_pool()
    if not pool:
        pytest.skip("No DB pool available")

    # Ephemeral setup
    client_id = uuid.uuid4()
    bot_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    call_id = uuid.uuid4()
    
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO clients (id, name, api_key_hash) VALUES ($1, 'Test', $2)", client_id, str(client_id))
            await conn.execute("INSERT INTO bot_configs (id, client_id, name, route, script_id, credits_per_minute) VALUES ($1, $2, 'Bot', 'sts', 'pyramid_hi', 1.0)", bot_id, client_id)
            await conn.execute("INSERT INTO campaigns (id, client_id, bot_config_id, name, status, max_attempts, retry_delay_minutes) VALUES ($1, $2, $3, 'Camp', 'running', 3, 10)", campaign_id, client_id, bot_id)
            await conn.execute("INSERT INTO leads (id, campaign_id, client_id, phone, status, attempts) VALUES ($1, $2, $3, '+1234567891', 'calling', 3)", lead_id, campaign_id, client_id)
            await conn.execute("INSERT INTO call_logs (session_call_id, client_id, campaign_id, bot_config_id, lead_id, in_progress) VALUES ($1, $2, $3, $4, $5, TRUE)", str(call_id), client_id, campaign_id, bot_id, lead_id)
            
        call_log = {
            "session_call_id": str(call_id),
            "lead_id": str(lead_id),
            "campaign_id": str(campaign_id),
            "client_id": str(client_id),
            "call_data": {}
        }
        
        # Action
        await pg_db.settle_unanswered_call(pool, call_log, retry_delay_minutes=10, base_outcome="Busy")
        
        # Assertions
        async with pool.acquire() as conn:
            lead_row = await conn.fetchrow("SELECT status, outcome FROM leads WHERE id = $1", lead_id)
            assert lead_row["status"] == "failed"
            assert lead_row["outcome"] == "Max_Attempts_Reached"
            
            call_row = await conn.fetchrow("SELECT in_progress, outcome FROM call_logs WHERE session_call_id = $1", str(call_id))
            assert not call_row["in_progress"]
            assert call_row["outcome"] == "Max_Attempts_Reached"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM clients WHERE id = $1", client_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_settle_unanswered_call_charges_setup_from_snapshot():
    import json
    from decimal import Decimal

    pool = pg_db.get_pool()
    if not pool:
        pytest.skip("No DB pool available")

    client_id = uuid.uuid4()
    bot_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    call_id = uuid.uuid4()
    call_data = json.dumps({
        "budget_reserved_credits": 5.6,
        "credits_per_minute": 2.5,
        "fixed_start_credits": 0.6,
    })

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO clients (id, name, api_key_hash, balance_credits) VALUES ($1, 'Test', $2, 100)",
                client_id,
                str(client_id),
            )
            await conn.execute(
                "INSERT INTO bot_configs (id, client_id, name, route, script_id, credits_per_minute) VALUES ($1, $2, 'Bot', 'sts', 'pyramid_hi', 2.5)",
                bot_id,
                client_id,
            )
            await conn.execute(
                """
                INSERT INTO campaigns (
                    id, client_id, bot_config_id, name, status,
                    max_attempts, retry_delay_minutes, budget_credits, budget_used_credits
                ) VALUES ($1, $2, $3, 'Camp', 'running', 3, 10, 100, 5.60)
                """,
                campaign_id,
                client_id,
                bot_id,
            )
            await conn.execute(
                "INSERT INTO leads (id, campaign_id, client_id, phone, status, attempts) VALUES ($1, $2, $3, '+1234567892', 'calling', 1)",
                lead_id,
                campaign_id,
                client_id,
            )
            await conn.execute(
                """
                INSERT INTO call_logs (
                    session_call_id, client_id, campaign_id, bot_config_id, lead_id,
                    in_progress, call_data
                ) VALUES ($1, $2, $3, $4, $5, TRUE, $6::jsonb)
                """,
                str(call_id),
                client_id,
                campaign_id,
                bot_id,
                lead_id,
                call_data,
            )

        call_log = {
            "session_call_id": str(call_id),
            "lead_id": str(lead_id),
            "campaign_id": str(campaign_id),
            "client_id": str(client_id),
            "call_data": json.loads(call_data),
        }
        await pg_db.settle_unanswered_call(
            pool,
            call_log,
            retry_delay_minutes=10,
            base_outcome="Busy",
            charge_setup=True,
        )

        async with pool.acquire() as conn:
            call_row = await conn.fetchrow(
                "SELECT credits_charged, billed_minutes FROM call_logs WHERE session_call_id = $1",
                str(call_id),
            )
            assert Decimal(str(call_row["credits_charged"])) == Decimal("0.6000")
            assert Decimal(str(call_row["billed_minutes"] or 0)) == Decimal("0")
            used = await conn.fetchval(
                "SELECT budget_used_credits FROM campaigns WHERE id = $1",
                campaign_id,
            )
            assert Decimal(str(used)) == Decimal("0.60")
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM clients WHERE id = $1", client_id)


"""Phase 2 integration tests (require DATABASE_URL + migrated schema for DB tests)."""

from __future__ import annotations

import os
import re

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

SCRIPT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def test_script_id_regex_rejects_traversal():
    assert SCRIPT_RE.fullmatch("pyramid_mr")
    assert not SCRIPT_RE.fullmatch("../secrets")





def test_outcome_to_event_mapping():
    from n8n_webhook import outcome_to_event

    assert outcome_to_event("Interested") == "lead_qualified"
    assert outcome_to_event("Callback_Requested") == "lead_callback"
    assert outcome_to_event("Busy") == "lead_failed"


def test_outcome_to_event_early_disconnect():
    from n8n_webhook import outcome_to_event

    assert outcome_to_event("Early_Disconnect") == "lead_callback"


def test_resolve_post_call_transition_callee_hangup_from_calling():

    from post_call_processor import resolve_post_call_transition

    new_status, next_at, sched_cb, fire_webhook = resolve_post_call_transition(
        "calling",
        "Unknown",
        1,
        3,
        120,
        {},
        lead_next_attempt_at=None,
        lead_scheduled_callback_at=None,
        callee_hangup=True,
    )
    assert new_status == "callback_scheduled"
    assert next_at is not None
    assert sched_cb == next_at
    assert fire_webhook is False

    failed_status, _, _, _ = resolve_post_call_transition(
        "calling",
        "Unknown",
        3,
        3,
        120,
        {},
        lead_next_attempt_at=None,
        lead_scheduled_callback_at=None,
        callee_hangup=True,
    )
    assert failed_status == "failed"


def test_resolve_post_call_preserves_callback_scheduled():
    from datetime import datetime, timezone

    from post_call_processor import resolve_post_call_transition

    due = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    new_status, next_at, sched_cb, _ = resolve_post_call_transition(
        "callback_scheduled",
        "Busy",
        2,
        3,
        120,
        {},
        lead_next_attempt_at=due,
        lead_scheduled_callback_at=due,
        callee_hangup=False,
    )
    assert new_status == "callback_scheduled"
    assert next_at == due
    assert sched_cb == due


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_create_client_roundtrip():

    import asyncpg

    from db import postgres as pg_db

    if True:
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")
        try:
            client_id, raw_key = await pg_db.create_client(
                pool, "Pytest Client", "pytest@test.com", "other"
            )
            found = await pg_db.get_client_by_token(pool, raw_key)
            assert found is not None
            assert str(found["id"]) == str(client_id)
        finally:
            await pool.close()



@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_try_settle_campaign_budget_idempotent():
    from decimal import Decimal
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db

    if True:
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")

        has_col = await pool.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'campaigns' AND column_name = 'budget_returned_at'
            )
            """
        )
        if not has_col:
            await pool.close()
            pytest.skip("Run just db-migrate for budget_returned_at column")

        try:
            client_id, _ = await pg_db.create_client(
                pool, f"Settle Test {uuid4().hex[:8]}", "settle@test.com", "other"
            )
            bot_id = await pg_db.create_bot_config(
                pool,
                client_id,
                name="Test Bot",
                route="sts",
                script_id="pyramid_mr",
                telephony_number="+911234567890",
                credits_per_minute=1.0,
            )
            await pg_db.add_credits(pool, client_id, 100.0, "pytest settle test")
            campaign_id = await pg_db.create_campaign(
                pool, client_id, bot_id, "Settle Campaign", budget_credits=50.0
            )
            await pool.execute(
                "UPDATE campaigns SET status = 'running' WHERE id = $1",
                campaign_id,
            )
            async with pool.acquire() as conn:
                async with conn.transaction():
                    first = await pg_db.try_settle_campaign_budget(
                        campaign_id,
                        client_id,
                        final_status="completed",
                        conn=conn,
                    )
                    second = await pg_db.try_settle_campaign_budget(
                        campaign_id,
                        client_id,
                        final_status="completed",
                        conn=conn,
                    )
            assert first == (Decimal("50"), True)
            assert second == (Decimal("0"), False)
            returned_at = await pool.fetchval(
                "SELECT budget_returned_at FROM campaigns WHERE id = $1",
                campaign_id,
            )
            assert returned_at is not None
        finally:
            await pool.close()



@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_finalize_call_log_after_early_in_progress_clear():
    """Post-call must finalize even after mark_call_log_not_in_progress (dialer unblock)."""
    from datetime import datetime, timezone
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db

    if True:
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")
        sid = str(uuid4())
        try:
            client_id, _ = await pg_db.create_client(
                pool, f"Finalize {uuid4().hex[:8]}", "fin@test.com", "other"
            )
            bot_id = await pg_db.create_bot_config(
                pool,
                client_id,
                name="Fin Bot",
                route="sts",
                script_id="pyramid_mr",
                telephony_number="+911234567891",
                credits_per_minute=1.0,
            )
            await pg_db.add_credits(pool, client_id, 100.0, "pytest finalize test")
            campaign_id = await pg_db.create_campaign(
                pool, client_id, bot_id, "Fin Campaign", budget_credits=10.0
            )
            await pg_db.bulk_insert_leads(
                pool,
                [
                    {
                        "client_id": client_id,
                        "campaign_id": campaign_id,
                        "phone": f"+9199{uuid4().int % 10**7:07d}",
                        "name": "Test Lead",
                    }
                ],
            )
            lead_id = await pool.fetchval(
                "SELECT id FROM leads WHERE campaign_id = $1 LIMIT 1",
                campaign_id,
            )
            await pg_db.insert_call_log_start(
                pool,
                sid,
                client_id,
                campaign_id,
                lead_id,
                bot_id,
                "sts",
                datetime.now(timezone.utc),
            )
            assert await pg_db.mark_call_log_not_in_progress(pool, sid)
            transcript = [{"role": "user", "content": "hello"}]
            await pg_db.finalize_call_log(
                pool,
                session_call_id=sid,
                duration_seconds=60,
                outcome="Not_Interested",
                extraction_json={"intent_status": "Not_Interested", "callback_time": None},
                billed_minutes=1,
                credits_charged=1.0,
                usage={},
                transcript=transcript,
            )
            row = await pool.fetchrow(
                """
                SELECT outcome, duration_seconds,
                       jsonb_array_length(transcript) AS turns,
                       extraction_json->>'intent_status' AS intent
                FROM call_logs WHERE session_call_id = $1
                """,
                sid,
            )
            assert row["outcome"] == "Not_Interested"
            assert row["duration_seconds"] == 60
            assert row["turns"] == 1
            assert row["intent"] == "Not_Interested"
        finally:
            await pool.close()


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_release_stuck_ignore_wrap_grace():
    """Manual release bypasses wrap-up grace when ignore_wrap_grace=True."""
    from datetime import datetime, timezone
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db

    try:
        pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    sid = str(uuid4())
    try:
        client_id, _ = await pg_db.create_client(
            pool, f"Release {uuid4().hex[:8]}", "rel@test.com", "other"
        )
        bot_id = await pg_db.create_bot_config(
            pool,
            client_id,
            name="Rel Bot",
            route="sts",
            script_id="pyramid_mr",
            telephony_number="+911234567892",
            credits_per_minute=1.0,
        )
        await pg_db.add_credits(pool, client_id, 100.0, "pytest release stuck")
        campaign_id = await pg_db.create_campaign(
            pool, client_id, bot_id, "Release Campaign", budget_credits=10.0
        )
        await pg_db.bulk_insert_leads(
            pool,
            [
                {
                    "client_id": client_id,
                    "campaign_id": campaign_id,
                    "phone": f"+9199{uuid4().int % 10**7:07d}",
                    "name": "Stuck Lead",
                }
            ],
        )
        lead_id = await pool.fetchval(
            "SELECT id FROM leads WHERE campaign_id = $1 LIMIT 1",
            campaign_id,
        )
        await pool.execute(
            "UPDATE leads SET status = 'calling' WHERE id = $1",
            lead_id,
        )
        await pool.execute(
            """
            UPDATE campaigns
            SET calling_leads = 1,
                pending_leads = GREATEST(pending_leads - 1, 0)
            WHERE id = $1
            """,
            campaign_id,
        )
        await pg_db.insert_call_log_start(
            pool,
            sid,
            client_id,
            campaign_id,
            lead_id,
            bot_id,
            "sts",
            datetime.now(timezone.utc),
            budget_reserved_credits=2.0,
        )
        await pg_db.mark_call_log_not_in_progress(
            pool, sid
        )

        blocked = await pg_db.release_stuck_calling_leads(
            pool, campaign_id, client_id
        )
        assert blocked == 0

        released = await pg_db.release_stuck_calling_leads(
            pool, campaign_id, client_id, ignore_wrap_grace=True
        )
        assert released == 1
        status = await pool.fetchval("SELECT status FROM leads WHERE id = $1", lead_id)
        assert status == "callback_scheduled"
    finally:
        await pool.close()


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_recover_abandoned_session_moves_calling_lead():
    """WS recovery runs post-call for leads left in calling after disconnect."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db
    from post_call_processor import recover_abandoned_session

    try:
        pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    sid = str(uuid4())
    try:
        client_id, _ = await pg_db.create_client(
            pool, f"Recover {uuid4().hex[:8]}", "rec@test.com", "other"
        )
        bot_id = await pg_db.create_bot_config(
            pool,
            client_id,
            name="Rec Bot",
            route="sts",
            script_id="pyramid_mr",
            telephony_number="+911234567893",
            credits_per_minute=1.0,
        )
        await pg_db.add_credits(pool, client_id, 100.0, "pytest recover session")
        campaign_id = await pg_db.create_campaign(
            pool, client_id, bot_id, "Recover Campaign", budget_credits=10.0
        )
        await pg_db.bulk_insert_leads(
            pool,
            [
                {
                    "client_id": client_id,
                    "campaign_id": campaign_id,
                    "phone": f"+9199{uuid4().int % 10**7:07d}",
                    "name": "Recover Lead",
                }
            ],
        )
        lead_id = await pool.fetchval(
            "SELECT id FROM leads WHERE campaign_id = $1 LIMIT 1",
            campaign_id,
        )
        await pool.execute(
            "UPDATE leads SET status = 'calling' WHERE id = $1",
            lead_id,
        )
        await pool.execute(
            """
            UPDATE campaigns
            SET calling_leads = 1,
                pending_leads = GREATEST(pending_leads - 1, 0),
                budget_used_credits = budget_used_credits + 2
            WHERE id = $1
            """,
            campaign_id,
        )
        await pg_db.insert_call_log_start(
            pool,
            sid,
            client_id,
            campaign_id,
            lead_id,
            bot_id,
            "sts",
            datetime.now(timezone.utc),
            budget_reserved_credits=2.0,
            credits_per_minute=3.5,
            fixed_start_credits=0.6,
        )
        budget_before = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        await pg_db.mark_call_log_not_in_progress(
            pool, sid
        )

        recovered = await recover_abandoned_session(pool, sid)
        assert recovered is True

        status = await pool.fetchval("SELECT status FROM leads WHERE id = $1", lead_id)
        assert status != "calling"
        budget_after = await pool.fetchval(
            "SELECT budget_used_credits FROM campaigns WHERE id = $1",
            campaign_id,
        )
        assert Decimal(str(budget_after)) <= Decimal(str(budget_before))
    finally:
        await pool.close()


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_client_release_stuck_calling_endpoint(client):
    """Client API can release stuck calling leads with ignore_wrap_grace."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from db import postgres as pg_db

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not configured")
    pool = pg_db.get_pool()
    if not pool:
        pytest.skip("Database pool not available")
    sid = str(uuid4())
    try:
        client_id, api_key = await pg_db.create_client(
            pool, f"API Rel {uuid4().hex[:8]}", "api_rel@test.com", "other"
        )
        bot_id = await pg_db.create_bot_config(
            pool,
            client_id,
            "Sales Bot",
            "sts",
            "pyramid_mr",
            "+919999999001",
            1.0,
        )
        await pg_db.add_credits(pool, client_id, 100.0, "deposit")
        camp_id = await pg_db.create_campaign(
            pool, client_id, bot_id, "API Release Campaign", budget_credits=50.0
        )
        await pg_db.update_campaign_status(pool, camp_id, client_id, "running")
        await pg_db.bulk_insert_leads(
            pool,
            [
                {
                    "client_id": client_id,
                    "campaign_id": camp_id,
                    "phone": f"+9199{uuid4().int % 10**7:07d}",
                    "name": "API Stuck Lead",
                }
            ],
        )
        lead_id = await pool.fetchval(
            "SELECT id FROM leads WHERE campaign_id = $1 LIMIT 1",
            camp_id,
        )
        await pool.execute(
            "UPDATE leads SET status = 'calling' WHERE id = $1",
            lead_id,
        )
        await pool.execute(
            """
            UPDATE campaigns
            SET calling_leads = 1,
                pending_leads = GREATEST(pending_leads - 1, 0)
            WHERE id = $1
            """,
            camp_id,
        )
        await pg_db.insert_call_log_start(
            pool,
            sid,
            client_id,
            camp_id,
            lead_id,
            bot_id,
            "sts",
            datetime.now(timezone.utc),
        )
        await pg_db.mark_call_log_not_in_progress(
            pool, sid
        )

        res = await client.post(
            f"/api/campaigns/{camp_id}/release-stuck-calling",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["released"] == 1
        assert body["counters"]["calling_leads"] == 0
    finally:
        pass


@pytest.mark.asyncio
async def test_auth_admin_rejects_client_token(test_client):
    


    os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-for-pytest")
    client = test_client
    resp = await client.get(
        "/internal/clients",
        headers={"Authorization": "Bearer wrong-not-admin"},
    )
    assert resp.status_code in (401, 403)

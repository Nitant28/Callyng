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


def test_compliance_dnd_list():
    import compliance

    phone = "+919999999001"
    compliance.add_dnd(phone)
    allowed, reason = compliance.is_call_allowed(phone)
    assert allowed is False
    assert "DND" in reason


def test_outcome_to_event_mapping():
    from n8n_webhook import outcome_to_event

    assert outcome_to_event("Interested") == "lead_qualified"
    assert outcome_to_event("Callback_Requested") == "lead_callback"
    assert outcome_to_event("Busy") == "lead_failed"


def test_resolve_post_call_transition_callee_hangup_from_calling():
    from datetime import datetime, timezone

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
    assert fire_webhook is True


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
def test_create_client_roundtrip():
    import asyncio

    import asyncpg

    from db import postgres as pg_db

    async def _run():
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
            await pg_db.close_pool()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
def test_try_settle_campaign_budget_idempotent():
    import asyncio
    from decimal import Decimal
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db

    async def _run():
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
            await pg_db.close_pool()
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
            assert first == Decimal("50")
            assert second == Decimal("0")
            returned_at = await pool.fetchval(
                "SELECT budget_returned_at FROM campaigns WHERE id = $1",
                campaign_id,
            )
            assert returned_at is not None
        finally:
            await pg_db.close_pool()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
def test_finalize_call_log_after_early_in_progress_clear():
    """Post-call must finalize even after mark_call_log_not_in_progress (dialer unblock)."""
    import asyncio
    import json
    from datetime import datetime, timezone
    from uuid import uuid4

    import asyncpg

    from db import postgres as pg_db

    async def _run():
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
                sid,
                60,
                "Not_Interested",
                {"intent_status": "Not_Interested", "callback_time": None},
                1,
                1.0,
                {},
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
            await pg_db.close_pool()

    asyncio.run(_run())


def test_auth_admin_rejects_client_token():
    from fastapi.testclient import TestClient

    import server

    os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-for-pytest")
    client = TestClient(server.app)
    resp = client.get(
        "/internal/clients",
        headers={"Authorization": "Bearer wrong-not-admin"},
    )
    assert resp.status_code in (401, 403)

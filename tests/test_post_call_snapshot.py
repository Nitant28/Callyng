"""DB tests for post_call_snapshot persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from script_runtime import build_post_call_snapshot_from_prefetch


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_insert_call_log_start_with_snapshot():
    import asyncpg

    from db import postgres as pg_db

    if True:
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")
        client_id = None
        session_id = f"test-snap-{uuid4()}"
        try:
            client_id, _ = await pg_db.create_client(
                pool, f"Snap Test {uuid4().hex[:8]}", "snap@test.com", "other"
            )
            snapshot = build_post_call_snapshot_from_prefetch(
                {
                    "script_config_id": str(uuid4()),
                    "version": 2,
                    "extraction_schema": {"mode": "fields", "fields": []},
                    "normalization_rules": [],
                    "outcome_event_map": {},
                    "outcome_terminal": ["Interested"],
                    "outcome_retry": ["Busy"],
                    "outcome_callback": ["Callback_Requested"],
                }
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
                call_data=snapshot,
            )
            row = await pg_db.get_call_log_by_session(pool, session_id)
            assert row is not None
            call_data = row.get("call_data") or {}
            if isinstance(call_data, str):
                import json

                call_data = json.loads(call_data)
            assert call_data.get("post_call_snapshot") is not None
            assert call_data["post_call_snapshot"]["version"] == 2
        finally:
            if client_id:
                await pool.execute(
                    "DELETE FROM call_logs WHERE session_call_id = $1", session_id
                )
                await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)
@pytest.mark.asyncio
async def test_patch_call_log_post_call_snapshot_idempotent():
    import asyncpg

    from db import postgres as pg_db

    if True:
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")
        client_id = None
        session_id = f"test-patch-{uuid4()}"
        try:
            client_id, _ = await pg_db.create_client(
                pool, f"Patch Test {uuid4().hex[:8]}", "patch@test.com", "other"
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
            snap = build_post_call_snapshot_from_prefetch(
                {
                    "script_config_id": None,
                    "version": None,
                    "extraction_schema": {"mode": "fields", "fields": []},
                }
            )
            first = await pg_db.patch_call_log_post_call_snapshot(
                pool, session_id, snap
            )
            second = await pg_db.patch_call_log_post_call_snapshot(
                pool, session_id, snap
            )
            assert first is True
            assert second is False
        finally:
            if client_id:
                await pool.execute(
                    "DELETE FROM call_logs WHERE session_call_id = $1", session_id
                )
                await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()

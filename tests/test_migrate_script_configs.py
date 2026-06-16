"""Integration test for migrate_script_configs."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from db import postgres as pg_db
from scripts.migrate_script_configs import migrate_script_configs


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_migrate_script_configs_links_bot_configs():
    async def _run():
        try:
            pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Postgres not reachable: {exc}")

        client_id = None
        try:
            client_id, _ = await pg_db.create_client(
                pool, f"Migrate Test {uuid4().hex[:8]}", "migrate@test.com", "other"
            )
            bot_sts = await pg_db.create_bot_config(
                pool,
                client_id,
                "STS Bot",
                "sts",
                "pyramid_hi",
                "+919999999100",
                1.0,
            )
            bot_cascade = await pg_db.create_bot_config(
                pool,
                client_id,
                "Cascade Bot",
                "cascaded",
                "prowave",
                "+919999999101",
                1.0,
            )

            results, errors = await migrate_script_configs(pool)
            assert not errors
            assert any(r.client_id == str(client_id) for r in results)

            rows = await pool.fetch(
                """
                SELECT id, route, script_id, script_config_id
                FROM bot_configs
                WHERE id = ANY($1::uuid[])
                ORDER BY route
                """,
                [bot_sts, bot_cascade],
            )
            assert len(rows) == 2
            assert rows[0]["script_config_id"] is not None
            assert rows[1]["script_config_id"] is not None

            sc_rows = await pool.fetch(
                """
                SELECT route, script_id
                FROM script_configs
                WHERE client_id = $1
                ORDER BY route, script_id
                """,
                client_id,
            )
            exported = {(r["route"], r["script_id"]) for r in sc_rows}
            assert ("sts", "pyramid_hi") in exported
            assert ("cascaded", "prowave") in exported
        finally:
            if client_id is not None:
                await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pg_db.close_pool()

    asyncio.run(_run())

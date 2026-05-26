"""Alembic env: applies SQL from db/schema when upgrading."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv

load_dotenv(override=True)

config = context.config
target_metadata = None

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "db" / "schema"


def get_url() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def _read_sql(name: str) -> str:
    return (SCHEMA_DIR / name).read_text(encoding="utf-8")


async def _apply_migrations() -> None:
    import asyncpg

    conn = await asyncpg.connect(get_url())
    try:
        has_version = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
            )
            """
        )
        current: str | None = None
        if has_version:
            current = await conn.fetchval(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )

        has_clients = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'clients'
            )
            """
        )

        if not has_clients and current != "002_compat":
            await conn.execute(_read_sql("001_initial.sql"))

        if current not in ("002_compat", "003_campaign_settlement"):
            await conn.execute(_read_sql("002_compat.sql"))

        if current != "003_campaign_settlement":
            await conn.execute(_read_sql("003_campaign_settlement.sql"))

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL PRIMARY KEY
            )
            """
        )
        await conn.execute("DELETE FROM alembic_version")
        await conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('003_campaign_settlement')"
        )
    finally:
        await conn.close()


def run_migrations_offline() -> None:
    context.configure(url=get_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(_apply_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

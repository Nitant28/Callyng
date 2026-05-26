#!/usr/bin/env python3
"""List public Postgres tables (used by `just db-check`)."""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv(override=True)


async def main() -> None:
    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)
    pool = await asyncpg.create_pool(dsn)
    try:
        rows = await pool.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        print("Tables:", [r["tablename"] for r in rows])
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

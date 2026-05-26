#!/usr/bin/env python3
"""Set max_concurrent_calls on all clients and campaigns (Plivo outbound limit)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env", override=True)


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    if limit < 1:
        print("Limit must be >= 1", file=sys.stderr)
        sys.exit(1)

    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    from db import postgres as pg_db

    pool = await pg_db.create_db_pool(dsn)
    try:
        clients = await pool.execute(
            "UPDATE clients SET max_concurrent_calls = $1",
            limit,
        )
        campaigns = await pool.execute(
            "UPDATE campaigns SET max_concurrent_calls = $1",
            limit,
        )
        print(f"Set max_concurrent_calls={limit} on all clients ({clients})")
        print(f"Set max_concurrent_calls={limit} on all campaigns ({campaigns})")
        rows = await pool.fetch(
            """
            SELECT c.name, c.max_concurrent_calls,
                   (SELECT COUNT(*)::int FROM campaigns cam WHERE cam.client_id = c.id)
                   AS campaign_count
            FROM clients c
            ORDER BY c.name
            """
        )
        for row in rows:
            print(
                f"  {row['name']}: client_max={row['max_concurrent_calls']} "
                f"campaigns={row['campaign_count']}"
            )
    finally:
        await pg_db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

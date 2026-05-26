#!/usr/bin/env python3
"""Recompute campaign denorm counters from leads table."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env", override=True)


async def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: uv run python scripts/reconcile_campaign.py <campaign_id>",
            file=sys.stderr,
        )
        sys.exit(1)

    campaign_id = UUID(sys.argv[1])
    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    from db import postgres as pg_db

    pool = await pg_db.create_db_pool(dsn)
    try:
        row = await pool.fetchrow(
            "SELECT client_id FROM campaigns WHERE id = $1",
            campaign_id,
        )
        if row is None:
            print(f"Campaign not found: {campaign_id}", file=sys.stderr)
            sys.exit(1)
        counts = await pg_db.reconcile_campaign_counters(
            pool, campaign_id, row["client_id"]
        )
        print("Reconciled counters:", counts)
    finally:
        await pg_db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

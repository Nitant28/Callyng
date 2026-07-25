#!/usr/bin/env python3
"""Release leads stuck in ``calling`` for a campaign (recovery helper)."""

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
            "Usage: uv run python scripts/release_stuck_leads.py <campaign_id> [client_id]",
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
        if len(sys.argv) >= 3:
            client_id = UUID(sys.argv[2])
        else:
            row = await pool.fetchrow(
                "SELECT client_id FROM campaigns WHERE id = $1",
                campaign_id,
            )
            if row is None:
                print(f"Campaign not found: {campaign_id}", file=sys.stderr)
                sys.exit(1)
            client_id = row["client_id"]

        before = await pool.fetch(
            """
            SELECT id, phone, status FROM leads
            WHERE campaign_id = $1 AND client_id = $2
            ORDER BY created_at
            """,
            campaign_id,
            client_id,
        )
        print(f"Leads before release ({len(before)}):")
        for row in before:
            print(f"  {row['id']}  {row['phone']}  {row['status']}")

        n = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
        counts = await pg_db.reconcile_campaign_counters(
            pool, campaign_id, client_id
        )
        print(f"Released {n} lead(s) from calling → pending for campaign {campaign_id}")
        print("Reconciled counters:", counts)
        if counts["calling_leads"] > 0:
            print(
                "WARNING: still have calling_leads > 0 — stop dialer (just stop-campaign) and re-run",
                file=sys.stderr,
            )
            sys.exit(1)
    finally:
        await pg_db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

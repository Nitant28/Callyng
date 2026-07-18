#!/usr/bin/env python3
"""Verify Postgres seed and campaign budget pre-allocation (dev)."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from uuid import UUID

from dotenv import load_dotenv

load_dotenv(override=True)

DEV_CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
DEV_CAMPAIGN_ID = UUID("00000000-0000-4000-8000-000000000003")


async def main() -> int:
    from db import postgres as pg

    if not pg.database_url():
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    await pg.init_pool()
    try:
        pool = pg.get_pool()
        tables = await pool.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        names = {r["tablename"] for r in tables}
        expected = {
            "bot_configs",
            "call_logs",
            "campaigns",
            "clients",
            "leads",
            "webhook_configs",
        }
        missing = expected - names
        if missing:
            print(f"Missing tables: {sorted(missing)}", file=sys.stderr)
            return 1
        print(f"Tables OK: {sorted(names & expected)}")

        row = await pool.fetchrow(
            "SELECT balance_credits FROM clients WHERE id = $1",
            DEV_CLIENT_ID,
        )
        if row is None:
            print("Dev client not seeded", file=sys.stderr)
            return 1
        balance_before = Decimal(str(row["balance_credits"]))
        print(f"Dev client balance (before allocate): {balance_before}")
        if balance_before < 100:
            print("Expected balance >= 100 after seed", file=sys.stderr)
            return 1

        # Reset campaign to draft for repeatable verify
        await pool.execute(
            """
            UPDATE campaigns
            SET status = 'draft', budget_credits = 0, budget_used_credits = 0,
                completed_at = NULL
            WHERE id = $1 AND client_id = $2
            """,
            DEV_CAMPAIGN_ID,
            DEV_CLIENT_ID,
        )

        await pg.allocate_campaign_budget(DEV_CAMPAIGN_ID, DEV_CLIENT_ID, 100)

        after = await pool.fetchrow(
            """
            SELECT c.balance_credits AS client_balance,
                   cam.budget_credits,
                   cam.status
            FROM clients c
            JOIN campaigns cam ON cam.client_id = c.id
            WHERE c.id = $1 AND cam.id = $2
            """,
            DEV_CLIENT_ID,
            DEV_CAMPAIGN_ID,
        )
        client_balance = Decimal(str(after["client_balance"]))
        budget = Decimal(str(after["budget_credits"]))
        if budget != 100:
            print(f"Allocate failed: budget={budget} status={after['status']}", file=sys.stderr)
            return 1
        if client_balance != balance_before - 100:
            print(
                f"Balance mismatch: {client_balance} != {balance_before - 100}",
                file=sys.stderr,
            )
            return 1
        print(f"Allocate OK: campaign budget=100, client balance={client_balance}")

        idx = await pool.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE indexname = 'idx_leads_dialer'
            """
        )
        if not idx:
            print("Missing index idx_leads_dialer", file=sys.stderr)
            return 1
        print("Index idx_leads_dialer OK")

        print("All checks passed.")
        return 0
    finally:
        await pg.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

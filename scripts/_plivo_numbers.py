#!/usr/bin/env python3
"""List Plivo numbers and clean stuck failed test call_log."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import plivo
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")


def list_numbers() -> None:
    auth_id = os.environ["PLIVO_AUTH_ID"]
    auth_token = os.environ["PLIVO_AUTH_TOKEN"]
    configured = (os.getenv("PLIVO_PHONE_NUMBER") or "").strip()
    print("configured PLIVO_PHONE_NUMBER:", configured)
    client = plivo.RestClient(auth_id, auth_token)
    resp = client.numbers.list(limit=20, offset=0)
    # plivo SDK returns object with objects list
    objs = getattr(resp, "objects", None) or resp
    print("account numbers:")
    if isinstance(objs, list):
        for n in objs:
            num = getattr(n, "number", None) or (n.get("number") if isinstance(n, dict) else n)
            print(" ", num)
    else:
        print(objs)


async def cleanup_stuck(session_call_id: str) -> None:
    from db import postgres as pg_db

    pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    try:
        row = await pool.fetchrow(
            "SELECT id, lead_id, in_progress FROM call_logs WHERE session_call_id = $1",
            session_call_id,
        )
        print("stuck row:", dict(row) if row else None)
        if row and row["in_progress"]:
            await pool.execute(
                """
                UPDATE call_logs
                SET in_progress = FALSE,
                    ended_at = COALESCE(ended_at, NOW()),
                    outcome = COALESCE(outcome, 'Unknown'),
                    duration_seconds = COALESCE(duration_seconds, 0)
                WHERE session_call_id = $1
                """,
                session_call_id,
            )
            print("cleared in_progress for", session_call_id)
        if row and row["lead_id"]:
            await pool.execute(
                "UPDATE leads SET status = 'pending' WHERE id = $1 AND status = 'calling'",
                row["lead_id"],
            )
    finally:
        await pool.close()


if __name__ == "__main__":
    list_numbers()
    sid = sys.argv[1] if len(sys.argv) > 1 else "b896dd32-26ed-4e76-98cf-7641f695ff04"
    asyncio.run(cleanup_stuck(sid))

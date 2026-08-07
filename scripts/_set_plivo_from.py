#!/usr/bin/env python3
"""Set bot telephony to +918031150443 and clear stuck calls."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

CHOSEN = "+918031150443"


async def main() -> None:
    from db import postgres as pg_db

    print("env PLIVO_PHONE_NUMBER:", (os.getenv("PLIVO_PHONE_NUMBER") or "").strip())
    pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    try:
        r = await pool.execute(
            """
            UPDATE bot_configs
            SET telephony_number = $1
            WHERE active = TRUE
              AND id IN (
                'bd2bab05-ed8b-41e3-aeed-abf10fd9fd04',
                '00000000-0000-4000-8000-000000000004',
                'bfed4b54-f1e7-4c9f-825d-bf84ea226ab4'
              )
            """,
            CHOSEN,
        )
        print("bots_update:", r)
        rows = await pool.fetch(
            """
            SELECT id, name, telephony_number
            FROM bot_configs
            WHERE active = TRUE
            ORDER BY name
            """
        )
        for row in rows:
            print(dict(row))
        s = await pool.execute(
            """
            UPDATE call_logs
            SET in_progress = FALSE,
                ended_at = COALESCE(ended_at, NOW()),
                outcome = COALESCE(outcome, 'Unknown'),
                duration_seconds = COALESCE(duration_seconds, 0)
            WHERE in_progress = TRUE
            """
        )
        print("cleared_stuck:", s)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

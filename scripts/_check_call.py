#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()


async def main():
    from db import postgres as pg_db

    sid = sys.argv[1] if len(sys.argv) > 1 else ""
    pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    if sid:
        r = await pool.fetchrow(
            "SELECT * FROM call_logs WHERE session_call_id = $1", sid
        )
        rows = [r] if r else []
    else:
        rows = await pool.fetch(
            """
            SELECT session_call_id, outcome, duration_seconds, recording_url,
                   in_progress, call_sid,
                   CASE WHEN transcript IS NULL THEN 0 ELSE jsonb_array_length(transcript) END AS turns
            FROM call_logs ORDER BY started_at DESC NULLS LAST LIMIT 3
            """
        )
    for r in rows:
        d = dict(r)
        print(json.dumps({k: str(v) if k == "id" else v for k, v in d.items()}, default=str, indent=2)[:4000])
        print("---")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

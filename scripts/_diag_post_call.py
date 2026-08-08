#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

SESSION = "2cf136bc-5ee7-4868-b217-558103346284"
LEAD = UUID("e8f0988e-b855-4aa7-b6f7-0eefdf23e142")


async def main() -> None:
    from db import postgres as pg_db

    pool = await pg_db.init_pool()
    try:
        rows = await pool.fetch(
            """
            SELECT session_call_id, in_progress, duration_seconds, outcome,
                   extraction_json, extraction_error, recording_url,
                   ended_at, started_at, lead_id, call_sid,
                   left(coalesce(transcript::text, ''), 400) AS transcript_preview,
                   call_data
            FROM call_logs
            WHERE session_call_id = $1 OR lead_id = $2
            ORDER BY started_at DESC NULLS LAST
            LIMIT 8
            """,
            SESSION,
            LEAD,
        )
        print("rows", len(rows))
        for r in rows:
            d = dict(r)
            print("---")
            for k in (
                "session_call_id",
                "call_sid",
                "in_progress",
                "duration_seconds",
                "outcome",
                "ended_at",
                "started_at",
                "extraction_error",
                "recording_url",
            ):
                print(f"  {k}: {d.get(k)}")
            print("  extraction:", str(d.get("extraction_json"))[:400])
            print("  transcript:", d.get("transcript_preview"))
            cd = d.get("call_data")
            if isinstance(cd, str):
                try:
                    cd = json.loads(cd)
                except Exception:
                    pass
            if isinstance(cd, dict):
                print("  call_data keys:", list(cd.keys())[:20])
                snap = cd.get("post_call_snapshot")
                if snap:
                    print("  snapshot keys:", list(snap.keys()) if isinstance(snap, dict) else type(snap))
        lead = await pool.fetchrow(
            "SELECT id, status, outcome, attempts, metadata FROM leads WHERE id = $1",
            LEAD,
        )
        print("LEAD", dict(lead) if lead else None)
    finally:
        await pg_db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

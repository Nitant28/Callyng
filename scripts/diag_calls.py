#!/usr/bin/env python3
"""Quick diagnostic for call_logs, leads, ngrok."""
import asyncio
import json
import os
from uuid import UUID

import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def main():
    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    sid = "e123392f-c5a1-44fc-b1ad-15f2512d3718"
    r = await pool.fetchrow("SELECT * FROM call_logs WHERE session_call_id = $1", sid)
    if r:
        d = dict(r)
        t = d.get("transcript")
        if isinstance(t, str):
            try:
                t = json.loads(t)
            except json.JSONDecodeError:
                t = []
        cd = d.get("call_data")
        if isinstance(cd, str):
            try:
                cd = json.loads(cd)
            except json.JSONDecodeError:
                pass
        print("=== call", sid, "===")
        print("call_sid:", d.get("call_sid"))
        print("outcome:", d.get("outcome"))
        print("duration:", d.get("duration_seconds"))
        print("recording:", d.get("recording_url"))
        print("transcript_turns:", len(t or []))
        print("in_progress:", d.get("in_progress"))
        if cd:
            print("call_data:", json.dumps(cd, default=str)[:600])
        ph = d.get("plivo_hangup_json")
        if ph:
            if isinstance(ph, str):
                try:
                    ph = json.loads(ph)
                except json.JSONDecodeError:
                    pass
            print("hangup:", json.dumps(ph, default=str)[:500])

    lead_id = UUID("df5d43df-2cf1-42d7-9fbb-cbfbbae99026")
    r2 = await pool.fetchrow("SELECT id, phone, status, campaign_id FROM leads WHERE id = $1", lead_id)
    r3 = await pool.fetchrow(
        "SELECT session_call_id, outcome FROM call_logs WHERE lead_id = $1 ORDER BY created_at DESC LIMIT 1",
        lead_id,
    )
    print("\n=== lead df5d43df ===", dict(r2) if r2 else None)
    print("latest call_log:", dict(r3) if r3 else "NONE")

    scripts = await pool.fetch(
        "SELECT id, name, route FROM script_configs WHERE active = true ORDER BY created_at DESC LIMIT 3"
    )
    print("\n=== active script_configs ===")
    for s in scripts:
        print(dict(s))

    await pool.close()

    ngrok = (os.getenv("NGROK_URL") or "").strip()
    if ngrok:
        url = f"{ngrok.rstrip('/')}/answer?call_id=diag-test"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                body = await resp.text()
                print(f"\n=== ngrok GET {url} -> {resp.status} ===")
                print(body[:400])


if __name__ == "__main__":
    asyncio.run(main())

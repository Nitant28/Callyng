#!/usr/bin/env python3
"""End-to-end call pipeline check: dial, poll call_log for transcript + recording."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


async def check_ngrok() -> bool:
    import aiohttp

    base = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    if not base:
        print("FAIL: NGROK_URL not set — Plivo cannot reach your server")
        return False
    url = f"{base}/answer?call_id=health-check"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                body = await resp.text()
                ok = resp.status == 200 and "<Stream" in body
                print(f"ngrok {url} -> {resp.status} {'OK' if ok else 'BAD'}")
                if not ok:
                    print(body[:300])
                return ok
    except Exception as exc:
        print(f"FAIL: ngrok unreachable: {exc}")
        return False


async def check_plivo_balance() -> bool:
    import aiohttp
    from telephony import fetch_plivo_cash_credits

    try:
        async with aiohttp.ClientSession() as session:
            bal = await fetch_plivo_cash_credits(session)
            print(f"Plivo balance: ${bal}")
            if bal <= 0:
                print("WARN: Plivo balance is zero or negative")
                return False
            return True
    except Exception as exc:
        print(f"FAIL: Plivo balance check: {exc}")
        return False


async def verify_call_log(pool, session_call_id: str) -> dict:
    row = await pool.fetchrow(
        """
        SELECT session_call_id, in_progress, duration_seconds, outcome, recording_url,
               CASE WHEN transcript IS NULL THEN 0 ELSE jsonb_array_length(transcript) END AS turns
        FROM call_logs WHERE session_call_id = $1
        """,
        session_call_id,
    )
    return dict(row) if row else {}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="E.164 number to dial")
    parser.add_argument("--script-config-id", required=True)
    parser.add_argument("--route", default="sts")
    parser.add_argument("--poll-seconds", type=int, default=90)
    args = parser.parse_args()

    if not await check_ngrok():
        return 1
    if not await check_plivo_balance():
        return 1

    # Delegate to test_call.py
    sys.path.insert(0, str(_ROOT))
    from scripts import test_call

    ns = argparse.Namespace(
        script_config_id=args.script_config_id,
        phone=args.phone,
        route=args.route,
        client_id=str(test_call.DEV_CLIENT_ID),
        campaign_id=str(test_call.SANDBOX_CAMPAIGN_ID),
        lead_name="E2E Test",
        city="Mumbai",
        poll_seconds=args.poll_seconds,
        host="localhost:7860",
    )
    rc = await test_call.run_test_call(ns)
    if rc != 0 and rc != 2:
        return rc

    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        # Find most recent call_log
        row = await pool.fetchrow(
            "SELECT session_call_id FROM call_logs ORDER BY started_at DESC NULLS LAST LIMIT 1"
        )
        if not row:
            print("FAIL: no call_log row after dial")
            return 1
        sid = row["session_call_id"]
        log = await verify_call_log(pool, sid)
        print("\n=== E2E verification ===")
        print(json.dumps(log, default=str, indent=2))

        issues = []
        if log.get("in_progress"):
            issues.append("call still in_progress after poll window")
        if log.get("duration_seconds") is None:
            issues.append("duration_seconds is null — call may not have connected/finalized")
        if (log.get("turns") or 0) < 1:
            issues.append("transcript empty — agent/user speech not captured")
        if not log.get("recording_url"):
            issues.append("no recording_url — Plivo recording webhook may have failed")

        if issues:
            print("\nISSUES:")
            for i in issues:
                print(f"  - {i}")
            return 2
        print("\nPASS: transcript + recording present")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""E2E agent test call — telephony/speech keys taken only from .env."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import aiohttp
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

PHONE = "+917397867643"
SCRIPT_CONFIG_ID = UUID("831d6c15-54be-4f8d-ae36-2be8d53d9f01")  # nitest
CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
ROUTE = "sts"
POLL_SECONDS = 240


def require_env(*keys: str) -> dict[str, str]:
    out = {}
    missing = []
    for k in keys:
        v = (os.getenv(k) or "").strip()
        if not v:
            missing.append(k)
        else:
            out[k] = v
    if missing:
        raise SystemExit(f"Missing required env: {', '.join(missing)}")
    return out


async def snapshot(pool, label: str) -> dict:
    credits = await pool.fetchrow(
        "SELECT id, balance_credits FROM clients WHERE id = $1",
        CLIENT_ID,
    )
    recent = await pool.fetch(
        """
        SELECT session_call_id, in_progress, duration_seconds, outcome,
               started_at, ended_at, lead_id
        FROM call_logs
        ORDER BY started_at DESC NULLS LAST
        LIMIT 5
        """
    )
    out = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "credits": dict(credits) if credits else None,
        "recent_calls": [dict(r) for r in recent],
    }
    print(f"\n=== {label} ===")
    print("credits:", out["credits"])
    for c in out["recent_calls"]:
        print(
            f"  session={c.get('session_call_id')} in_progress={c.get('in_progress')} "
            f"duration={c.get('duration_seconds')} outcome={c.get('outcome')}"
        )
    return out


async def main() -> int:
    from compliance import is_call_allowed
    from db import postgres as pg_db
    from dialer.concurrent_dialer import _release_lead_to_pending, fire_call
    from scripts.test_call import (
        SANDBOX_CAMPAIGN_ID,
        _call_log_finalized,
        _claim_throwaway_lead,
        _ensure_campaign_bot,
        _poll_call_log,
        _print_summary,
        _resolve_bot_config,
    )
    from telephony import normalize_plivo_number

    env = require_env(
        "DATABASE_URL",
        "PLIVO_AUTH_ID",
        "PLIVO_AUTH_TOKEN",
        "PLIVO_PHONE_NUMBER",
        "GOOGLE_API_KEY",
        "NGROK_URL",
    )
    from_number = normalize_plivo_number(env["PLIVO_PHONE_NUMBER"])
    print("from_number (env):", from_number)
    print("google_api_key: set")
    print("ngrok:", env["NGROK_URL"][:48] + "...")

    allowed, reason = is_call_allowed()
    print("compliance:", allowed, reason)
    if not allowed:
        return 1

    pool = await pg_db.create_db_pool(env["DATABASE_URL"])
    try:
        from db import redis_client as redis_db

        await redis_db.init_redis()
        before = await snapshot(pool, "BEFORE CALL")

        script_config = await pg_db.get_script_config(pool, SCRIPT_CONFIG_ID, CLIENT_ID)
        if script_config is None:
            print("ERROR: script_config missing", file=sys.stderr)
            return 1
        print(
            "script:",
            script_config.get("script_id"),
            "voice=",
            script_config.get("gemini_voice"),
            "model=",
            script_config.get("gemini_model"),
            "lang=",
            script_config.get("gemini_language"),
        )

        bot_config = await _resolve_bot_config(
            pool,
            client_id=CLIENT_ID,
            script_config_id=SCRIPT_CONFIG_ID,
            route=ROUTE,
        )
        bot_config = dict(bot_config)
        # Always dial using env caller ID (with +)
        bot_config["telephony_number"] = from_number

        campaign = await _ensure_campaign_bot(
            pool,
            campaign_id=SANDBOX_CAMPAIGN_ID,
            client_id=CLIENT_ID,
            bot_config_id=UUID(str(bot_config["id"])),
        )

        lead = await _claim_throwaway_lead(
            pool,
            client_id=CLIENT_ID,
            campaign_id=SANDBOX_CAMPAIGN_ID,
            dial_phone=PHONE,
            lead_name="E2E Test Lead",
            city="Pune",
        )
        lead_id = UUID(str(lead["id"]))
        print(f"Dialing {PHONE} from {from_number} lead={lead_id}")

        try:
            async with aiohttp.ClientSession() as session:
                session_call_id = await fire_call(
                    session,
                    lead,
                    campaign,
                    bot_config,
                    host="localhost:7860",
                    pool=pool,
                    client_id=CLIENT_ID,
                    campaign_id=SANDBOX_CAMPAIGN_ID,
                    dial_phone=PHONE,
                    is_test_call=True,
                )
        except Exception as exc:
            print(f"ERROR: dial failed: {exc}", file=sys.stderr)
            await _release_lead_to_pending(pool, lead, SANDBOX_CAMPAIGN_ID, CLIENT_ID)
            await snapshot(pool, "AFTER FAILED DIAL")
            return 1

        if not session_call_id:
            print("ERROR: call skipped", file=sys.stderr)
            await _release_lead_to_pending(pool, lead, SANDBOX_CAMPAIGN_ID, CLIENT_ID)
            return 1

        print(f"Plivo dial placed session={session_call_id}. Polling {POLL_SECONDS}s…")
        print("Answer the phone — agent should speak via Gemini (GOOGLE_API_KEY).")
        call_log = await _poll_call_log(pool, session_call_id, timeout_s=POLL_SECONDS)
        _print_summary(session_call_id=session_call_id, call_log=call_log)
        after = await snapshot(pool, "AFTER CALL")
        print("before_credits:", before.get("credits"))
        print("after_credits:", after.get("credits"))

        if call_log and _call_log_finalized(call_log):
            print("\nRESULT: E2E call finalized OK")
            return 0
        print("\nRESULT: call not finalized within poll window", file=sys.stderr)
        return 2
    finally:
        await pool.close()
        try:
            from db import redis_client as redis_db

            await redis_db.close_redis()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

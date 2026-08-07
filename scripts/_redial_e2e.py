#!/usr/bin/env python3
"""Redial target on existing Prowave Excel campaign with verified Plivo from-number."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
CAMPAIGN_ID = UUID("7985243e-eb03-463c-9d7c-07addc6e1898")
TARGET = "+917397867643"
FROM_FALLBACK = "+918035463696"


async def main() -> int:
    import aiohttp
    from db import postgres as pg_db
    from dialer.concurrent_dialer import fire_call, _release_lead_to_pending

    pool = await pg_db.init_pool()
    try:
        from db import redis_client as redis_db

        await redis_db.init_redis()

        camp = await pg_db.get_campaign(pool, CAMPAIGN_ID, CLIENT_ID)
        if not camp:
            print("campaign missing", file=sys.stderr)
            return 1

        lead_row = await pool.fetchrow(
            "SELECT * FROM leads WHERE campaign_id = $1 AND phone = $2 LIMIT 1",
            CAMPAIGN_ID,
            TARGET,
        )
        if not lead_row:
            print("lead missing", file=sys.stderr)
            return 1
        lead = pg_db.record_to_dict(lead_row)

        # Clear wrap-up / in_progress guards from prior failed dial
        await pool.execute(
            """
            UPDATE call_logs
            SET in_progress = FALSE,
                ended_at = NOW() - INTERVAL '30 minutes',
                outcome = COALESCE(NULLIF(TRIM(outcome), ''), 'Unknown'),
                duration_seconds = COALESCE(duration_seconds, 0)
            WHERE lead_id = $1 OR in_progress = TRUE
            """,
            lead["id"],
        )

        bot = await pg_db.get_bot_config(pool, UUID(str(camp["bot_config_id"])), CLIENT_ID)
        bot = dict(bot)
        bot["telephony_number"] = FROM_FALLBACK

        await pool.execute(
            """
            UPDATE leads
            SET status = 'calling', last_attempted_at = NOW(),
                attempts = GREATEST(attempts, 1)
            WHERE id = $1
            """,
            lead["id"],
        )
        lead["status"] = "calling"

        print(f"Dialing {TARGET} from {FROM_FALLBACK}")
        print("(env PLIVO_PHONE_NUMBER +918031150443 is not on this Plivo account)")
        print("Answer the phone — agent should speak.")

        async with aiohttp.ClientSession() as session:
            try:
                sid = await fire_call(
                    session,
                    lead,
                    camp,
                    bot,
                    host="localhost:7860",
                    pool=pool,
                    client_id=CLIENT_ID,
                    campaign_id=CAMPAIGN_ID,
                    dial_phone=TARGET,
                    is_test_call=True,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                await _release_lead_to_pending(pool, lead, CAMPAIGN_ID, CLIENT_ID)
                return 1

        print("session_call_id:", sid)
        return 0 if sid else 1
    finally:
        try:
            from db import redis_client as redis_db

            await redis_db.close_redis()
        except Exception:
            pass
        await pg_db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""Create concurrency=4 campaign with ONLY +917397867643, start it, dial once (not test-call)."""

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
TARGET = "+917397867643"
FROM_FALLBACK = "+918035463696"  # verified on this Plivo account


async def main() -> int:
    import aiohttp
    from compliance import is_call_allowed
    from db import postgres as pg_db
    from db import redis_client as redis_db
    from dialer.concurrent_dialer import fire_call, _release_lead_to_pending

    allowed, reason = is_call_allowed()
    print("compliance:", allowed, reason)
    if not allowed:
        return 1

    print("POST_CALL_MODEL=", os.getenv("POST_CALL_MODEL"))
    print("from=", FROM_FALLBACK)

    pool = await pg_db.init_pool()
    try:
        await redis_db.init_redis()

        # Pause other running campaigns so only this dialer work matters
        paused = await pool.execute(
            """
            UPDATE campaigns
            SET status = 'paused'
            WHERE client_id = $1 AND status IN ('running', 'pausing')
            """,
            CLIENT_ID,
        )
        print("paused other campaigns:", paused)

        bot = await pool.fetchrow(
            """
            SELECT * FROM bot_configs
            WHERE client_id = $1 AND active = TRUE
              AND script_config_id IS NOT NULL AND route = 'sts'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            CLIENT_ID,
        )
        if bot is None:
            print("ERROR: no STS bot", file=sys.stderr)
            return 1
        bot = pg_db.record_to_dict(bot)
        print("bot:", bot["id"], bot.get("name"))

        await pool.execute(
            "UPDATE bot_configs SET telephony_number = $1 WHERE id = $2",
            FROM_FALLBACK,
            UUID(str(bot["id"])),
        )
        bot["telephony_number"] = FROM_FALLBACK

        campaign_id = await pg_db.create_campaign(
            pool,
            client_id=CLIENT_ID,
            bot_config_id=UUID(str(bot["id"])),
            name="Concurrent Live Slots v4",
            budget_credits=100,
            max_concurrent_calls=4,
            calls_per_minute=10,
            max_attempts=3,
            retry_delay_minutes=30,
        )
        print("campaign_id:", campaign_id)

        n = await pg_db.bulk_insert_leads(
            pool,
            [
                {
                    "client_id": CLIENT_ID,
                    "campaign_id": campaign_id,
                    "phone": TARGET,
                    "name": "Live Slot Test",
                    "lead_type": "warm",
                    "status": "pending",
                    "max_attempts": 3,
                    "metadata": {
                        "location": "Pune",
                        "language": "hi",
                        "bhk": "2BHK",
                        "intent": "test",
                        "call_summary": "concurrency-4 live slot test",
                    },
                }
            ],
        )
        print("leads_inserted:", n)

        await pg_db.update_campaign_status(pool, campaign_id, CLIENT_ID, "running")
        camp = await pg_db.get_campaign(pool, campaign_id, CLIENT_ID)
        print(
            "campaign:",
            camp["id"],
            "status=",
            camp["status"],
            "max_concurrent=",
            camp["max_concurrent_calls"],
        )

        lead_row = await pool.fetchrow(
            "SELECT * FROM leads WHERE campaign_id = $1 AND phone = $2 LIMIT 1",
            campaign_id,
            TARGET,
        )
        lead = pg_db.record_to_dict(lead_row)

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
        await pool.execute(
            """
            UPDATE campaigns
            SET calling_leads = 1,
                pending_leads = GREATEST(pending_leads - 1, 0)
            WHERE id = $1 AND client_id = $2
            """,
            campaign_id,
            CLIENT_ID,
        )

        print(f"Dialing {TARGET} from {FROM_FALLBACK} (is_test_call=False)")
        print("Answer the phone — lead must stay Live at top of leads table.")

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
                    campaign_id=campaign_id,
                    dial_phone=TARGET,
                    is_test_call=False,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                await _release_lead_to_pending(pool, lead, campaign_id, CLIENT_ID)
                return 1

        print("session_call_id:", sid)
        print("lead_id:", lead["id"])
        print("Open campaign in UI:", f"/app/campaigns/{campaign_id}")
        return 0 if sid else 1
    finally:
        try:
            await redis_db.close_redis()
        except Exception:
            pass
        await pg_db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

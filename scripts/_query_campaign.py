import asyncio
import os
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()


async def main():
    import asyncpg

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    camps = await pool.fetch("SELECT id, name, status, bot_config_id FROM campaigns ORDER BY created_at DESC LIMIT 5")
    print("campaigns", [dict(c) for c in camps])
    if camps:
        cid = camps[0]["id"]
        camp = camps[0]
    else:
        camp = None
        cid = None
    leads = []
    if cid:
        leads = await pool.fetch(
            "SELECT id, phone, name, status FROM leads WHERE campaign_id = $1 ORDER BY created_at DESC LIMIT 5",
            cid,
        )
    bot = None
    if camp:
        bot = await pool.fetchrow(
            "SELECT id, route, script_config_id, script_id FROM bot_configs WHERE id = $1",
            camp["bot_config_id"],
        )
    calls = await pool.fetch(
        "SELECT session_call_id, outcome, duration_seconds FROM call_logs ORDER BY started_at DESC LIMIT 3"
    )
    print("campaign", dict(camp) if camp else None)
    print("bot", dict(bot) if bot else None)
    print("leads", [dict(l) for l in leads])
    print("recent_calls", [dict(c) for c in calls])
    await pool.close()


asyncio.run(main())

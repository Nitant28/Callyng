import asyncio
from db import postgres as pg_db
from api.routes.campaigns import _get_lead_schema
from uuid import UUID
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    cid = UUID("00000000-0000-0000-0000-000000000000")
    campaign_id = UUID("9c7f6687-82e8-4f60-aac0-68d160880e71")
    
    camp = await pool.fetchrow("SELECT * FROM campaigns WHERE id = $1", campaign_id)
    if not camp:
        print("Campaign not found")
        return
    cid = camp["client_id"]
    
    camp_dict = pg_db.record_to_dict(camp)
    print("Camp dict:", camp_dict)
    
    bot_record = await pg_db.get_bot_config(pool, UUID(str(camp_dict["bot_config_id"])), cid)
    bot = dict(bot_record) if bot_record else None
    print("Bot:", bot)
    
    lead_schema = await _get_lead_schema(pool, bot, cid) if bot else {"fields": []}
    print("Lead Schema:", lead_schema)

if __name__ == "__main__":
    asyncio.run(main())

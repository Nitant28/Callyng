import asyncio
from dotenv import load_dotenv
from db import postgres as pg_db
import json

load_dotenv(".env")

async def main():
    await pg_db.init_pool()
    pool = await pg_db.get_pool()
    print("Pool connected")
    rows = await pool.fetch("SELECT session_call_id, call_data FROM call_logs WHERE campaign_id IS NULL AND client_id IS NOT NULL ORDER BY created_at DESC LIMIT 1")
    print(f"Found {len(rows)} rows")
    for r in rows:
        print(f"Session: {r['session_call_id']}")
        print(f"call_data: {r['call_data']}")
    
    await pool.close()

asyncio.run(main())

import asyncio
from dotenv import load_dotenv
from db import postgres as pg_db

load_dotenv(".env")

async def main():
    await pg_db.init_pool()
    pool = await pg_db.get_pool()
    
    rows = await pool.fetch("""
        SELECT session_call_id, recording_url 
        FROM call_logs 
        WHERE recording_url IS NOT NULL 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    print(f"Found {len(rows)} calls with recordings:")
    for r in rows:
        print(f"Session: {r['session_call_id']} | URL: {r['recording_url']}")
        
    await pool.close()

asyncio.run(main())

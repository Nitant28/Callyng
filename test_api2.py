import asyncio
from db import postgres as pg_db
import asyncpg
import json

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    await pg_db._init_connection(pool) # wait, asyncpg pool init is pg_db.init_pool!
    
    rows = await pool.fetch("""
        SELECT session_call_id, client_id FROM call_logs LIMIT 1;
    """)
    if not rows:
        print("No calls")
        return
        
    session_call_id = rows[0]['session_call_id']
    cid = rows[0]['client_id']
    
    call = await pg_db.get_call_log(pool, session_call_id, cid)
    if call:
        print("Call loaded")
    else:
        print("Call not found")

if __name__ == "__main__":
    asyncio.run(main())

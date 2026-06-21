import asyncio
from db import postgres as pg_db
import asyncpg
import json

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    
    # Get a random call
    row = await pool.fetchrow("""
        SELECT session_call_id, client_id FROM call_logs LIMIT 1;
    """)
    if not row:
        print("No calls")
        return
        
    session_call_id = row['session_call_id']
    cid = row['client_id']
    
    call = await pg_db.get_call_log(pool, session_call_id, cid)
    print("Call keys:", call.keys())
    print("Transcript type:", type(call['transcript']))
    if isinstance(call['transcript'], str):
        print("Transcript snippet:", call['transcript'][:50])

if __name__ == "__main__":
    asyncio.run(main())

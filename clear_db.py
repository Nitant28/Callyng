import asyncio
from db import postgres as pg_db
from server import app

async def clear_db():
    pool = await pg_db.init_pool()
    async with pool.acquire() as conn:
        print("Clearing call_logs...")
        await conn.execute("DELETE FROM call_logs")
        
        print("Clearing leads...")
        await conn.execute("DELETE FROM leads")
        
        print("Clearing campaigns...")
        await conn.execute("DELETE FROM campaigns")
        
        print("Clearing test bot configs (except seeds and diya)...")
        # Keep seeds (starts with CLI Sandbox) and 'diya0pyramid parkland'
        await conn.execute("""
            DELETE FROM bot_configs 
            WHERE name NOT LIKE 'CLI Sandbox%' 
            AND name NOT ILIKE '%diya%pyramid%parkland%'
        """)
        
        print("Cleanup complete!")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(clear_db())

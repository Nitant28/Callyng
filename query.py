import asyncio
import asyncpg
from db.postgres import get_pool

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:aakashvani@localhost:5432/aakashvani")
    rows = await pool.fetch("SELECT session_call_id, recording_url FROM call_logs ORDER BY created_at DESC LIMIT 5;")
    for row in rows:
        print(row)
    await pool.close()

asyncio.run(main())

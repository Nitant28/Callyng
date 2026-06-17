import asyncio
import asyncpg
import os

async def run():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    row = await pool.fetchrow("SELECT transcript FROM call_logs LIMIT 1")
    if row:
        print(repr(row["transcript"]))
    await pool.close()

asyncio.run(run())

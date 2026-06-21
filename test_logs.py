import asyncio
from db import postgres as pg_db
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    rows = await pool.fetch("SELECT session_call_id, in_progress, outcome, duration_seconds FROM call_logs ORDER BY created_at DESC LIMIT 5;")
    for row in rows:
        print(dict(row))

if __name__ == "__main__":
    asyncio.run(main())

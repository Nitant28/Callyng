import asyncio
from db import postgres as pg_db
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgresql://aakashvani:devpassword@localhost:5432/aakashvani")
    rows = await pool.fetch("""
        SELECT c.session_call_id, c.outcome, c.in_progress, l.id as lead_id, l.status as lead_status, l.name
        FROM call_logs c
        JOIN leads l ON c.lead_id = l.id
        ORDER BY c.created_at DESC
        LIMIT 5;
    """)
    for row in rows:
        print(dict(row))

if __name__ == "__main__":
    asyncio.run(main())

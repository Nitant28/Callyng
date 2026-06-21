import asyncio
from db import postgres as pg_db
import dotenv
dotenv.load_dotenv()

async def main():
    await pg_db.init_pool()
    pool = pg_db.get_pool()
    calls, total = await pg_db.list_call_logs(pool, None, limit=10, offset=0)
    for c in calls:
        print(c['session_call_id'], "in_progress =", c.get('in_progress'), type(c.get('in_progress')), "outcome =", c.get('outcome'))
    await pg_db.close_pool()

if __name__ == '__main__':
    asyncio.run(main())

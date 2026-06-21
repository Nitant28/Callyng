import asyncio
from db import postgres as pg_db
import dotenv
dotenv.load_dotenv()

async def main():
    await pg_db.init_pool()
    pool = pg_db.get_pool()
    calls, total = await pg_db.list_call_logs(pool, None, limit=200, offset=0)
    for c in calls:
        if c.get('in_progress'):
            print("FOUND LIVE CALL:", c['session_call_id'])
    print("Done")
    await pg_db.close_pool()

if __name__ == '__main__':
    asyncio.run(main())

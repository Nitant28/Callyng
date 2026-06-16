import asyncio
from dotenv import load_dotenv
from db import postgres as pg_db

load_dotenv(".env")

async def main():
    pool = await pg_db.get_pool()
    rows = await pool.fetch("SELECT id, script_id, route, client_id FROM script_configs")
    print(f"Total script_configs: {len(rows)}")
    for r in rows:
        print(f" - {r['script_id']} ({r['route']})")
    
    bot_configs = await pool.fetch("SELECT id, script_id, route, script_config_id FROM bot_configs WHERE active = TRUE")
    print(f"Total active bot_configs: {len(bot_configs)}")
    for b in bot_configs:
        print(f" - bot {b['id']}: script_id={b['script_id']} linked_config={b['script_config_id']}")
    
    await pool.close()

asyncio.run(main())

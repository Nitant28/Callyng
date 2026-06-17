import asyncio
import os
import json
from dotenv import load_dotenv
load_dotenv(".env")
from db.postgres import create_db_pool, database_url

async def run():
    pool = await create_db_pool(database_url())
    # fetch all call logs
    rows = await pool.fetch("SELECT id, transcript, extraction_json, call_data FROM call_logs")
    for r in rows:
        updates = {}
        if isinstance(r["transcript"], str):
            try: updates["transcript"] = json.loads(r["transcript"])
            except: pass
        if isinstance(r["extraction_json"], str):
            try: updates["extraction_json"] = json.loads(r["extraction_json"])
            except: pass
        if isinstance(r["call_data"], str):
            try: updates["call_data"] = json.loads(r["call_data"])
            except: pass
            
        if updates:
            print(f"Fixing {r['id']}")
            set_clauses = ", ".join([f"{k} = ${i+2}::jsonb" for i, k in enumerate(updates.keys())])
            args = [r["id"]] + list(updates.values())
            await pool.execute(f"UPDATE call_logs SET {set_clauses} WHERE id = $1", *args)
            
    await pool.close()

asyncio.run(run())

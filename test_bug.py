import asyncio
from db import postgres as pg_db
from api.routes.campaigns import _get_lead_schema
from uuid import UUID
import asyncpg

async def main():
    pool = await asyncpg.create_pool("postgres://satyam:password@localhost:5432/aakashvani")
    # Using a known campaign id from logs
    cid = UUID("aac068d1-6088-0e71-82e8-4f60aac068d1") # wait, the UUID is 9c7f6687-82e8-4f60-aac0-68d160880e71
    # But wait, I don't know the client_id.
    

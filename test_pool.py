import asyncio
from httpx import AsyncClient, ASGITransport
from server import app
from db import postgres as pg_db
import logging
import os
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.DEBUG)

async def main():
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            print("Client ready")
            print("app.state.pool:", getattr(app.state, "pool", None))
            print("pg_db._pool:", pg_db._pool)
            r = await client.get("/api/credits")
            print("Result:", r.status_code)
            print("Body:", r.text)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())

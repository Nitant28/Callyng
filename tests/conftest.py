"""Pytest path setup for repo-root imports."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest_asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from server import app
from db import postgres as pg_db
from db import redis_client as redis_db
import aiohttp
from unittest.mock import patch

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_globals():
    """Manually initialize the database and redis pools for the test session."""
    pool = await pg_db.init_pool()
    app.state.pool = pool
    await redis_db.init_redis(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    app.state.dialer_tasks = {}
    app.state.session = aiohttp.ClientSession()
    app.state.background_tasks = set()
    from background_tasks import bind_background_tasks
    bind_background_tasks(app.state.background_tasks)
    
    yield
    
    # Clean up all test-generated garbage data from the database
    print("\nCleaning up test-generated database records...")
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Delete logs and leads (non-existent in seed)
                await conn.execute("DELETE FROM call_logs")
                await conn.execute("DELETE FROM leads")
                
                # Delete campaigns except for the seed campaigns
                await conn.execute(
                    "DELETE FROM campaigns WHERE id NOT IN ("
                    "'00000000-0000-4000-8000-000000000003', "
                    "'00000000-0000-4000-8000-000000000006'"
                    ")"
                )
                
                # Delete bot configs except for the seed bots
                await conn.execute(
                    "DELETE FROM bot_configs WHERE id NOT IN ("
                    "'00000000-0000-4000-8000-000000000002', "
                    "'00000000-0000-4000-8000-000000000004', "
                    "'00000000-0000-4000-8000-000000000005'"
                    ")"
                )
                
                # Delete webhook configs, credit transactions, and script configs
                # for any client other than the seed client
                await conn.execute(
                    "DELETE FROM webhook_configs WHERE client_id != '00000000-0000-4000-8000-000000000001'"
                )
                await conn.execute(
                    "DELETE FROM credit_transactions WHERE client_id != '00000000-0000-4000-8000-000000000001'"
                )
                await conn.execute(
                    "DELETE FROM script_configs WHERE client_id != '00000000-0000-4000-8000-000000000001'"
                )
                
                # Delete clients except for the seed client
                await conn.execute(
                    "DELETE FROM clients WHERE id != '00000000-0000-4000-8000-000000000001'"
                )
        print("Cleanup completed successfully.")
    except Exception as e:
        print(f"Warning: Failed to clean up database records: {e}")
        
    await app.state.session.close()
    await pg_db.close_pool()

@pytest_asyncio.fixture(scope="session")
async def _global_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c

@pytest.fixture
def client(_global_client):
    return _global_client

@pytest.fixture
def test_client(_global_client):
    return _global_client

@pytest.fixture(autouse=True)
def mock_is_call_allowed():
    with patch("dialer.concurrent_dialer.is_call_allowed", return_value=(True, "Allowed")), \
         patch("api.routes.campaigns.is_call_allowed", return_value=(True, "Allowed")), \
         patch("api.routes.leads.is_call_allowed", return_value=(True, "Allowed")):
        yield

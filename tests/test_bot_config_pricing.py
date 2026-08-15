"""Admin bot-config pricing: POST/PATCH/GET fixed_start_credits."""

from __future__ import annotations

import os
import uuid

import pytest
from dotenv import load_dotenv

from db import postgres as pg_db

load_dotenv(override=True)


def _admin_headers() -> dict[str, str]:
    key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not key:
        pytest.skip("ADMIN_API_KEY not set")
    return {"X-Admin-Key": key}


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_bot_config_fixed_start_credits_roundtrip(client):
    if not pg_db.get_pool():
        pytest.skip("No DB pool available")
    pool = pg_db.get_pool()
    client_id, _ = await pg_db.create_client(
        pool,
        f"Price API {uuid.uuid4().hex[:8]}",
        "price@test.com",
        "other",
    )
    headers = _admin_headers()
    create = await client.post(
        "/internal/bot-configs",
        headers=headers,
        json={
            "client_id": str(client_id),
            "name": "Custom Pricing Bot",
            "route": "sts",
            "script_id": "pyramid_hi",
            "telephony_number": "+911234567890",
            "credits_per_minute": 5.50,
            "fixed_start_credits": 0.60,
        },
    )
    assert create.status_code == 200, create.text
    bot_id = create.json()["id"]

    got = await client.get(f"/internal/bot-configs/{bot_id}", headers=headers)
    assert got.status_code == 200
    bot = got.json()["bot_config"]
    assert bot["credits_per_minute"] == 5.5
    assert abs(bot["fixed_start_credits"] - 0.6) < 1e-9

    patched = await client.patch(
        f"/internal/bot-configs/{bot_id}",
        headers=headers,
        json={"credits_per_minute": 6.00, "fixed_start_credits": 0.50},
    )
    assert patched.status_code == 200, patched.text

    got2 = await client.get(f"/internal/bot-configs/{bot_id}", headers=headers)
    bot2 = got2.json()["bot_config"]
    assert bot2["credits_per_minute"] == 6.0
    assert abs(bot2["fixed_start_credits"] - 0.5) < 1e-9

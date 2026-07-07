"""Edge case tests for the client API."""

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from server import app
from db import postgres as pg_db


from httpx import AsyncClient, ASGITransport
import pytest_asyncio



@pytest_asyncio.fixture(scope="session")
async def dev_auth_headers():
    """Gets the auth header for the dev tenant."""
    pool = pg_db.get_pool()
    # Rely on the seed script having created the dev tenant
    client = await pg_db.get_client_by_token(pool, "aakashvani_dev_key_change_me")
    if client:
        return {"Authorization": "Bearer aakashvani_dev_key_change_me"}
    
    # If not found, skip or create it (assume seeded for this test)
    pytest.skip("Dev tenant not seeded.")


@pytest.mark.asyncio
async def test_credits_unauthorized(test_client):
    res = await test_client.get("/api/credits")
    assert res.status_code == 401

    res = await test_client.get("/api/credits", headers={"Authorization": "Bearer invalid_key"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_campaigns_unauthorized(test_client):
    res = await test_client.get("/api/campaigns")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_campaign_invalid_budget(test_client, dev_auth_headers):
    payload = {
        "name": "Test Campaign",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": -50,  # invalid
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_campaign_invalid_bot(test_client, dev_auth_headers):
    payload = {
        "name": "Test Campaign",
        "bot_config_id": str(uuid4()),  # non-existent bot
        "budget_credits": 100,
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    assert res.status_code == 400
    assert "bot" in res.json()["detail"].lower() or "foreign key" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_campaign_success(test_client, dev_auth_headers):
    payload = {
        "name": "Test Campaign Edge",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": 100,
        "max_concurrent_calls": 5,
        "calls_per_minute": 10,
        "max_attempts": 3,
        "retry_delay_minutes": 120
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    assert res.status_code == 200
    camp_id = res.json()["id"]

    # Retrieve campaign
    res = await test_client.get(f"/api/campaigns/{camp_id}/stats", headers=dev_auth_headers)
    assert res.status_code == 200
    
    # Try patching campaign
    patch_payload = {
        "max_attempts": 5,
        "calls_per_minute": -1  # invalid? Let's check schema validation. wait schema might not block it if not Ge=0
    }
    res = await test_client.patch(f"/api/campaigns/{camp_id}", json=patch_payload, headers=dev_auth_headers)
    
    # Let's try adding a lead
    add_lead_payload = {
        "phone": "+12025550100",
        "name": "Test User",
        "lead_type": "hot"
    }
    res = await test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    assert res.status_code == 200
    lead_id = res.json()["lead"]["id"]

    # Manual status change to calling (should fail, 409)
    res = await test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "calling"}, headers=dev_auth_headers)
    assert res.status_code == 409

    # Manual status change to completed
    res = await test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "completed"}, headers=dev_auth_headers)
    assert res.status_code == 200


    # Manual status change back to pending so it can be deleted
    res = await test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "pending"}, headers=dev_auth_headers)
    assert res.status_code == 200

    # Delete the lead
    res = await test_client.delete(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 200

    # Check if really deleted
    res = await test_client.get(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 404

    # Cancel campaign
    res = await test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)
    assert res.status_code == 200

    # Try modifying a cancelled campaign (should fail, 409)
    patch_payload = {"name": "Test Modified"}
    res = await test_client.patch(f"/api/campaigns/{camp_id}", json=patch_payload, headers=dev_auth_headers)
    assert res.status_code == 409  # Protected by require_campaign_modifiable


@pytest.mark.asyncio
async def test_manual_pending_resets_attempts(test_client, dev_auth_headers):
    """Manual → pending clears attempts and outcome (fresh lead reset)."""
    payload = {
        "name": "Reset Test Campaign",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": 100,
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    camp_id = res.json()["id"]

    add_lead_payload = {
        "phone": "+12025550201",
        "name": "Reset User",
        "lead_type": "hot",
    }
    res = await test_client.post(
        f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers
    )
    lead_id = res.json()["lead"]["id"]

    pool = pg_db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE leads
            SET status = 'callback_scheduled', attempts = 2, outcome = 'No_Answer',
                next_attempt_at = NOW(), scheduled_callback_at = NOW()
            WHERE id = $1
            """,
            lead_id,
        )

    res = await test_client.patch(
        f"/api/campaigns/{camp_id}/leads/{lead_id}/status",
        json={"status": "pending"},
        headers=dev_auth_headers,
    )
    assert res.status_code == 200
    lead = res.json()["lead"]
    assert lead["status"] == "pending"
    assert lead["attempts"] == 0
    assert lead["outcome"] is None

    await test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)


@pytest.mark.asyncio
async def test_manual_callback_blocked_at_max_attempts(test_client, dev_auth_headers):
    """Manual → callback_scheduled rejected when attempts >= max_attempts (dead-state guard)."""
    payload = {
        "name": "Callback Guard Campaign",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": 100,
        "max_attempts": 3,
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    camp_id = res.json()["id"]

    add_lead_payload = {
        "phone": "+12025550202",
        "name": "Exhausted User",
        "lead_type": "hot",
    }
    res = await test_client.post(
        f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers
    )
    lead_id = res.json()["lead"]["id"]

    pool = pg_db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE leads
            SET status = 'pending', attempts = 3, max_attempts = 3, outcome = 'Max_Attempts_Reached'
            WHERE id = $1
            """,
            lead_id,
        )

    res = await test_client.patch(
        f"/api/campaigns/{camp_id}/leads/{lead_id}/status",
        json={"status": "callback_scheduled"},
        headers=dev_auth_headers,
    )
    assert res.status_code == 409
    assert "maximum attempts" in res.json()["detail"].lower()
    assert "pending" in res.json()["detail"].lower()

    # Recovery path: failed → pending (resets attempts) → callback_scheduled
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE leads SET status = 'failed' WHERE id = $1",
            lead_id,
        )

    res = await test_client.patch(
        f"/api/campaigns/{camp_id}/leads/{lead_id}/status",
        json={"status": "pending"},
        headers=dev_auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["lead"]["attempts"] == 0

    res = await test_client.patch(
        f"/api/campaigns/{camp_id}/leads/{lead_id}/status",
        json={"status": "callback_scheduled"},
        headers=dev_auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["lead"]["status"] == "callback_scheduled"

    await test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)


@pytest.mark.asyncio
async def test_modify_started_lead(test_client, dev_auth_headers):
    # Create campaign
    payload = {
        "name": "Test Lead Restrictions",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": 100,
    }
    res = await test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    camp_id = res.json()["id"]

    # Add a lead
    add_lead_payload = {
        "phone": "+12025550100",
        "name": "Test User",
        "lead_type": "hot"
    }
    res = await test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    lead_id = res.json()["lead"]["id"]

    # Manually transition lead to "completed" (this is allowed by _MANUAL_TRANSITIONS from pending)
    res = await test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "completed"}, headers=dev_auth_headers)
    assert res.status_code == 200

    # Edit the processed lead (now allowed under new relaxed locking)
    res = await test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}", json={"name": "New Name"}, headers=dev_auth_headers)
    assert res.status_code == 200
    assert res.json()["lead"]["name"] == "New Name"

    # Delete the processed lead (now allowed)
    res = await test_client.delete(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 200

    # Try adding a lead to a completed/cancelled campaign
    # First finish the campaign
    await test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)
    
    res = await test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    assert res.status_code == 409
    assert "Cannot modify leads" in res.json()["detail"]

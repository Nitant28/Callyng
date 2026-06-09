"""Edge case tests for the client API."""

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from server import app
from db import postgres as pg_db


@pytest.fixture
def test_client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def dev_auth_headers(pool):
    """Gets the auth header for the dev tenant."""
    # Rely on the seed script having created the dev tenant
    client = await pg_db.get_client_by_token(pool, "aakashvani_dev_key_change_me")
    if client:
        return {"Authorization": "Bearer aakashvani_dev_key_change_me"}
    
    # If not found, skip or create it (assume seeded for this test)
    pytest.skip("Dev tenant not seeded.")


@pytest.mark.asyncio
async def test_credits_unauthorized(test_client):
    res = test_client.get("/api/credits")
    assert res.status_code == 401

    res = test_client.get("/api/credits", headers={"Authorization": "Bearer invalid_key"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_campaigns_unauthorized(test_client):
    res = test_client.get("/api/campaigns")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_campaign_invalid_budget(test_client, dev_auth_headers):
    payload = {
        "name": "Test Campaign",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": -50,  # invalid
    }
    res = test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_campaign_invalid_bot(test_client, dev_auth_headers):
    payload = {
        "name": "Test Campaign",
        "bot_config_id": str(uuid4()),  # non-existent bot
        "budget_credits": 100,
    }
    res = test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
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
    res = test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    assert res.status_code == 200
    camp_id = res.json()["id"]

    # Retrieve campaign
    res = test_client.get(f"/api/campaigns/{camp_id}/stats", headers=dev_auth_headers)
    assert res.status_code == 200
    
    # Try patching campaign
    patch_payload = {
        "max_attempts": 5,
        "calls_per_minute": -1  # invalid? Let's check schema validation. wait schema might not block it if not Ge=0
    }
    res = test_client.patch(f"/api/campaigns/{camp_id}", json=patch_payload, headers=dev_auth_headers)
    
    # Let's try adding a lead
    add_lead_payload = {
        "phone": "+12025550100",
        "name": "Test User",
        "lead_type": "hot"
    }
    res = test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    assert res.status_code == 200
    lead_id = res.json()["lead"]["id"]

    # Manual status change to calling (should fail, 409)
    res = test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "calling"}, headers=dev_auth_headers)
    assert res.status_code == 409

    # Manual status change to dnc
    res = test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "dnc"}, headers=dev_auth_headers)
    assert res.status_code == 200

    # Delete the lead
    res = test_client.delete(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 200

    # Check if really deleted
    res = test_client.get(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 404

    # Cancel campaign
    res = test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)
    assert res.status_code == 200

    # Try modifying a cancelled campaign (should fail, 409)
    patch_payload = {"name": "Test Modified"}
    res = test_client.patch(f"/api/campaigns/{camp_id}", json=patch_payload, headers=dev_auth_headers)
    assert res.status_code == 409  # Protected by require_campaign_modifiable


@pytest.mark.asyncio
async def test_modify_started_lead(test_client, dev_auth_headers):
    # Create campaign
    payload = {
        "name": "Test Lead Restrictions",
        "bot_config_id": "00000000-0000-4000-8000-000000000002",
        "budget_credits": 100,
    }
    res = test_client.post("/api/campaigns", json=payload, headers=dev_auth_headers)
    camp_id = res.json()["id"]

    # Add a lead
    add_lead_payload = {
        "phone": "+12025550100",
        "name": "Test User",
        "lead_type": "hot"
    }
    res = test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    lead_id = res.json()["lead"]["id"]

    # Manually transition lead to "completed" (this is allowed by _MANUAL_TRANSITIONS from pending)
    res = test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}/status", json={"status": "completed"}, headers=dev_auth_headers)
    assert res.status_code == 200

    # Try editing the completed lead
    res = test_client.patch(f"/api/campaigns/{camp_id}/leads/{lead_id}", json={"name": "New Name"}, headers=dev_auth_headers)
    assert res.status_code == 409
    assert "already been processed" in res.json()["detail"]

    # Try deleting the completed lead
    res = test_client.delete(f"/api/campaigns/{camp_id}/leads/{lead_id}", headers=dev_auth_headers)
    assert res.status_code == 409
    assert "already been processed" in res.json()["detail"]

    # Try adding a lead to a completed campaign
    # First finish the campaign
    test_client.patch(f"/api/campaigns/{camp_id}/cancel", headers=dev_auth_headers)
    
    res = test_client.post(f"/api/campaigns/{camp_id}/leads", json=add_lead_payload, headers=dev_auth_headers)
    assert res.status_code == 409
    assert "Cannot modify leads" in res.json()["detail"]

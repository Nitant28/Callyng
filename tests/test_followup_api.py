"""Integration tests for manual follow-up API routes."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from db import postgres as pg_db

DEV_HEADERS = {"Authorization": "Bearer aakashvani_dev_key_change_me"}
CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
CAMPAIGN_ID = UUID("00000000-0000-4000-8000-000000000003")


@pytest_asyncio.fixture(scope="session")
async def dev_auth_headers():
    pool = pg_db.get_pool()
    if pool is None:
        pytest.skip("PostgreSQL not available")
    client = await pg_db.get_client_by_token(pool, "aakashvani_dev_key_change_me")
    if not client:
        pytest.skip("Dev tenant not seeded.")
    return DEV_HEADERS


async def _create_test_lead() -> UUID:
    pool = pg_db.get_pool()
    lead_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO leads (
                id, client_id, campaign_id, phone, name, status, lead_type, metadata
            ) VALUES ($1, $2, $3, $4, $5, 'completed', 'warm', $6::jsonb)
            """,
            lead_id,
            CLIENT_ID,
            CAMPAIGN_ID,
            "+919359210080",
            "Follow-up Test Lead",
            '{"email": "getin2grave@gmail.com", "lead_city": "Pune"}',
        )
    return lead_id


async def _delete_test_lead(lead_id: UUID) -> None:
    pool = pg_db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM follow_up_events WHERE lead_id = $1", lead_id)
        await conn.execute("DELETE FROM leads WHERE id = $1", lead_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_manual_follow_up_requires_auth(test_client):
    lead_id = await _create_test_lead()
    try:
        res = await test_client.post(f"/api/leads/{lead_id}/follow-up", json={})
        assert res.status_code == 401
    finally:
        await _delete_test_lead(lead_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_manual_follow_up_success(test_client, dev_auth_headers):
    lead_id = await _create_test_lead()
    try:
        with patch(
            "integrations.n8n.service.N8nService.send_lead_qualified",
            new_callable=AsyncMock,
        ) as mock_send:
            from integrations.n8n.service import N8nSendResult

            mock_send.return_value = N8nSendResult(ok=True, status_code=200)
            res = await test_client.post(
                f"/api/leads/{lead_id}/follow-up",
                json={},
                headers=dev_auth_headers,
            )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        # No approved first-contact template is configured for the test client and the
        # lead has never messaged us, so free-form WhatsApp is not permitted yet.
        assert body["whatsapp"] == "blocked"
        assert body["first_contact"]["mode"] == "blocked"
        assert body["first_contact"]["can_send"] is False
        assert body["email"] == "queued"
        mock_send.assert_awaited_once()
        payload = mock_send.await_args.args[0]
        assert payload["flow_type"] == "INITIAL_FOLLOWUP"
        assert payload["interested"] is True
        assert payload["lead"]["phone"] == "+919359210080"
        assert payload["fallback"]["whatsapp"]["message"]
        assert payload["fallback"]["email"]["subject"]
        assert payload["fallback"]["email"]["body"]
    finally:
        await _delete_test_lead(lead_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_manual_follow_up_deduplicates(test_client, dev_auth_headers):
    lead_id = await _create_test_lead()
    try:
        with patch(
            "integrations.n8n.service.N8nService.send_lead_qualified",
            new_callable=AsyncMock,
        ) as mock_send:
            from integrations.n8n.service import N8nSendResult

            mock_send.return_value = N8nSendResult(ok=True, status_code=200)
            first = await test_client.post(
                f"/api/leads/{lead_id}/follow-up",
                json={},
                headers=dev_auth_headers,
            )
            second = await test_client.post(
                f"/api/leads/{lead_id}/follow-up",
                json={},
                headers=dev_auth_headers,
            )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json().get("deduplicated") is True
        assert mock_send.await_count == 1
    finally:
        await _delete_test_lead(lead_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_follow_up_history(test_client, dev_auth_headers):
    lead_id = await _create_test_lead()
    try:
        with patch(
            "integrations.n8n.service.N8nService.send_lead_qualified",
            new_callable=AsyncMock,
        ) as mock_send:
            from integrations.n8n.service import N8nSendResult

            mock_send.return_value = N8nSendResult(ok=True, status_code=200)
            await test_client.post(
                f"/api/leads/{lead_id}/follow-up",
                json={},
                headers=dev_auth_headers,
            )
        res = await test_client.get(
            f"/api/leads/{lead_id}/follow-ups",
            headers=dev_auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any(e.get("source") == "manual" for e in data["events"])
    finally:
        await _delete_test_lead(lead_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_internal_lead_context_by_phone(test_client):
    admin_key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not admin_key:
        pytest.skip("ADMIN_API_KEY not configured")
    pool = pg_db.get_pool()
    if pool is None:
        pytest.skip("PostgreSQL not available")

    lead_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO leads (id, client_id, campaign_id, phone, name, status, metadata)
            VALUES ($1, $2, $3, $4, $5, 'completed', $6::jsonb)
            """,
            lead_id,
            CLIENT_ID,
            CAMPAIGN_ID,
            "+919359210080",
            "Context Lookup",
            '{"email": "getin2grave@gmail.com"}',
        )
    try:
        res = await test_client.get(
            "/internal/leads/context",
            params={"phone": "9359210080", "flow_type": "CONTINUE_CHAT", "inbound_message": "Hi"},
            headers={"X-Admin-Key": admin_key},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["payload"]["flow_type"] == "CONTINUE_CHAT"
        assert body["payload"]["lead"]["phone"] == "+919359210080"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM leads WHERE id = $1", lead_id)

"""Admin webhook config CRUD + campaign routing."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from db import postgres as pg_db

ADMIN_KEY = (os.getenv("ADMIN_API_KEY") or "dev-admin-key-123").strip()
ADMIN_HEADERS = {"X-Admin-Key": ADMIN_KEY}
CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
CAMPAIGN_ID = UUID("00000000-0000-4000-8000-000000000003")
WEBHOOK_URL = "https://n8n.example.com/webhook/test-aakashvani"


def _require_pool():
    try:
        return pg_db.get_pool()
    except RuntimeError:
        pytest.skip("PostgreSQL not available")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_webhook_upsert_list_test_delete(test_client):
    if not ADMIN_KEY:
        pytest.skip("ADMIN_API_KEY not configured")
    pool = _require_pool()

    # Upsert
    res = await test_client.post(
        "/internal/webhook-configs",
        headers=ADMIN_HEADERS,
        json={
            "client_id": str(CLIENT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "event": "lead_qualified",
            "url": WEBHOOK_URL,
            "secret": "test-secret",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    webhook_id = body["id"]
    assert body["webhook"]["url"] == WEBHOOK_URL
    assert body["webhook"]["campaign_id"] == str(CAMPAIGN_ID)

    # List includes names + events
    listed = await test_client.get(
        f"/internal/clients/{CLIENT_ID}/webhooks",
        headers=ADMIN_HEADERS,
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert "lead_qualified" in listed_body["events"]
    match = next((w for w in listed_body["webhooks"] if w["id"] == webhook_id), None)
    assert match is not None
    assert match["url"] == WEBHOOK_URL
    assert match.get("campaign_name")

    # Routing resolves this URL
    from integrations.n8n.routing import resolve_campaign_webhook

    dest = await resolve_campaign_webhook(
        pool,
        client_id=CLIENT_ID,
        campaign_id=CAMPAIGN_ID,
        event="lead_qualified",
    )
    assert dest.ok is True
    assert dest.webhook_url == WEBHOOK_URL

    # Test endpoint hits configured URL
    with patch(
        "integrations.n8n.service.N8nService.send_test_event",
        new_callable=AsyncMock,
    ) as mock_test:
        from integrations.n8n.service import N8nSendResult

        mock_test.return_value = N8nSendResult(ok=True, status_code=200)
        tested = await test_client.post(
            f"/internal/webhook-configs/{webhook_id}/test",
            headers=ADMIN_HEADERS,
        )
        assert tested.status_code == 200, tested.text
        mock_test.assert_awaited_once()

    # Delete
    deleted = await test_client.delete(
        f"/internal/webhook-configs/{webhook_id}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    dest_after = await resolve_campaign_webhook(
        pool,
        client_id=CLIENT_ID,
        campaign_id=CAMPAIGN_ID,
        event="lead_qualified",
    )
    # May still resolve if another lead_qualified row exists for this campaign;
    # the deleted id must be gone from list.
    listed2 = await test_client.get(
        f"/internal/clients/{CLIENT_ID}/webhooks",
        headers=ADMIN_HEADERS,
    )
    ids = {w["id"] for w in listed2.json()["webhooks"]}
    assert webhook_id not in ids

    # Re-seed production URL used by live Dev Draft campaign for other tests
    await pg_db.upsert_webhook_config(
        pool,
        CLIENT_ID,
        CAMPAIGN_ID,
        "lead_qualified",
        "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792",
        None,
    )
    _ = dest_after


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_webhook_upsert_rejects_bad_event(test_client):
    if not ADMIN_KEY:
        pytest.skip("ADMIN_API_KEY not configured")
    res = await test_client.post(
        "/internal/webhook-configs",
        headers=ADMIN_HEADERS,
        json={
            "client_id": str(CLIENT_ID),
            "campaign_id": str(CAMPAIGN_ID),
            "event": "not_a_real_event",
            "url": WEBHOOK_URL,
        },
    )
    assert res.status_code == 422


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
@pytest.mark.asyncio
async def test_webhook_delete_missing(test_client):
    if not ADMIN_KEY:
        pytest.skip("ADMIN_API_KEY not configured")
    res = await test_client.delete(
        f"/internal/webhook-configs/{uuid4()}",
        headers=ADMIN_HEADERS,
    )
    assert res.status_code == 404

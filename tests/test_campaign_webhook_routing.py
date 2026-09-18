"""Campaign webhook routing uses physical webhook_configs.url/secret columns."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from integrations.n8n.routing import resolve_campaign_webhook


CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
CAMPAIGN_ID = UUID("00000000-0000-4000-8000-000000000003")


@pytest.mark.asyncio
async def test_resolve_campaign_webhook_uses_url_column(monkeypatch):
    class _FakePool:
        async def fetchrow(self, query, *args):
            assert "webhook_url" not in query
            assert " FROM webhook_configs" in query.replace("\n", " ")
            assert "url" in query
            assert "secret" in query
            assert args == (CLIENT_ID, CAMPAIGN_ID, "lead_qualified")
            return {
                "id": uuid4(),
                "url": "https://n8n.example.com/webhook/test",
                "secret": "s3cret",
                "active": True,
                "event": "lead_qualified",
            }

    dest = await resolve_campaign_webhook(
        _FakePool(),
        client_id=CLIENT_ID,
        campaign_id=CAMPAIGN_ID,
        event="lead_qualified",
    )
    assert dest.ok is True
    assert dest.webhook_url == "https://n8n.example.com/webhook/test"
    assert dest.webhook_secret == "s3cret"
    assert dest.source == "campaign_webhook"


@pytest.mark.asyncio
async def test_resolve_campaign_webhook_missing_row():
    class _FakePool:
        async def fetchrow(self, query, *args):
            return None

    dest = await resolve_campaign_webhook(
        _FakePool(),
        client_id=CLIENT_ID,
        campaign_id=CAMPAIGN_ID,
        event="lead_qualified",
    )
    assert dest.ok is False
    assert dest.error == "no_webhook_configured_for_campaign_event"

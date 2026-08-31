"""Tests for remote n8n integration (no live WhatsApp, no n8n login)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from integrations.n8n.config import N8nConfig
from integrations.n8n.payload import PAYLOAD_FIELD_SOURCES, build_connectivity_test_payload, build_lead_qualified_payload, build_test_payload
from integrations.n8n.service import N8nService


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("N8N_BASE_URL", "https://n8n.bhuvisx.com")
    monkeypatch.setenv("N8N_LEAD_WEBHOOK_URL", "https://n8n.bhuvisx.com/webhook/abc")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "secret123")
    monkeypatch.setenv("N8N_TIMEOUT_SECONDS", "20")
    cfg = N8nConfig.from_env()
    assert cfg.base_url == "https://n8n.bhuvisx.com"
    assert cfg.lead_webhook_url.endswith("/webhook/abc")
    assert cfg.webhook_secret == "secret123"
    assert cfg.timeout_seconds == 20
    assert cfg.is_configured is True


def test_config_not_configured_when_url_missing(monkeypatch):
    monkeypatch.delenv("N8N_LEAD_WEBHOOK_URL", raising=False)
    cfg = N8nConfig.from_env()
    assert cfg.is_configured is False


def test_build_lead_qualified_payload_mega_workflow_contract():
    client_id = uuid4()
    lead_id = uuid4()
    campaign_id = uuid4()
    bot_id = uuid4()
    payload = build_lead_qualified_payload(
        client_id=client_id,
        lead={
            "id": lead_id,
            "name": "Rahul Sharma",
            "phone": "9876543210",
            "lead_type": "warm",
            "metadata": {"email": "rahul@example.com", "city": "Pune"},
        },
        session_call_id="sess_abc123",
        duration_seconds=95,
        extraction={"intent_status": "Interested", "summary": "Wants brochure"},
        campaign={"id": campaign_id, "name": "March Outreach"},
        outcome="Interested",
        bot_config_id=bot_id,
        billed_minutes=2,
        credits_charged=4.5,
        route="sts",
        recording_url="recordings/abc.mp3",
    )
    # Event envelope
    assert payload["event"] == "lead_qualified"
    assert payload["event_id"] == f"sess_abc123:{lead_id}"
    assert payload["client_id"] == str(client_id)
    assert payload["client"]["id"] == str(client_id)
    assert payload["follow_up"]["idempotency_key"].startswith("n8n_")
    # Lead Context fields
    assert payload["lead"]["phone"] == "+919876543210"
    assert payload["lead"]["email"] == "rahul@example.com"
    assert payload["lead"]["metadata"]["city"] == "Pune"
    assert payload["lead"]["lead_type"] == "warm"
    # Legacy Mega_Workflow fields preserved
    assert payload["call"]["session_call_id"] == "sess_abc123"
    assert payload["call"]["duration_seconds"] == 95
    assert payload["call"]["billed_minutes"] == 2
    assert payload["extraction"]["intent_status"] == "Interested"
    assert payload["campaign"]["name"] == "March Outreach"
    # Structured extensions
    assert payload["call"]["id"] == "sess_abc123"
    assert payload["call"]["duration"] == 95
    assert payload["qualification"]["status"] == "interested"
    assert payload["agent"]["id"] == str(bot_id)
    assert payload["follow_up"]["channel"] == "whatsapp"
    assert payload["metadata"]["campaign_id"] == str(campaign_id)
    assert "aakashvani" in payload
    assert payload["extraction"]["intent_status"] == payload["extraction"]["intent_status"]
    assert "send_url" in payload["aakashvani"]


def test_extraction_aliases_intent_and_bhk():
    payload = build_lead_qualified_payload(
        client_id=uuid4(),
        lead={"id": uuid4(), "name": "A", "phone": "9999999999", "metadata": {}},
        session_call_id="s1",
        duration_seconds=1,
        extraction={"intent_status": "Interested", "bhk_preference": "2 BHK", "location_preference": "Pune"},
        campaign={"id": uuid4(), "name": "C"},
        outcome="Interested",
    )
    ext = payload["extraction"]
    assert ext["intent_status"] == "Interested"
    assert ext["intent_status"] == "Interested"
    assert ext["bhk_preference"] == "2 BHK"
    assert ext["bhk_preference"] == "2 BHK"
    assert ext["location_preference"] == "Pune"
    assert ext["location_preference"] == "Pune"


def test_record_url_uses_public_base(monkeypatch):
    monkeypatch.setenv("AAKASHVANI_PUBLIC_URL", "https://api.example.com")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    from integrations.n8n.payload import build_lead_qualified_payload as build

    payload = build(
        client_id=uuid4(),
        lead={"id": uuid4(), "name": "A", "phone": "9876543210", "metadata": {}},
        session_call_id="s1",
        duration_seconds=10,
        extraction={"intent_status": "Interested"},
        campaign={"id": uuid4(), "name": "C"},
    )
    assert payload["aakashvani"]["record_url"].startswith("https://api.example.com/internal/messages/record?token=")
    assert payload["aakashvani"]["context_url"].startswith("https://api.example.com/internal/leads/context")
    assert "Hi" in payload["fallback"]["whatsapp"]["message"]
    assert payload["fallback"]["email"]["subject"]
    assert payload["fallback"]["email"]["body"]


def test_build_connectivity_test_payload():
    payload = build_connectivity_test_payload()
    assert payload["event"] == "connectivity_test"
    assert payload["test"] is True
    assert payload["source"] == "aakashvani_admin"


def test_build_test_payload():
    payload = build_test_payload()
    assert payload["event"] == "lead_qualified"
    assert payload["lead"]["name"] == "Test Lead"
    assert payload["metadata"]["test"] is True
    assert "event_id" in payload


def test_payload_field_sources_documented():
    assert "lead.phone" in PAYLOAD_FIELD_SOURCES
    assert "extraction" in PAYLOAD_FIELD_SOURCES
    assert "qualification.status" in PAYLOAD_FIELD_SOURCES


@pytest.mark.asyncio
async def test_service_skips_when_not_configured():
    service = N8nService(N8nConfig(base_url="", lead_webhook_url="", webhook_secret=None, timeout_seconds=15))
    result = await service.send_lead_qualified({"event": "lead_qualified"})
    assert result.skipped is True
    assert result.ok is False


@pytest.mark.asyncio
async def test_service_posts_with_webhook_secret_header():
    cfg = N8nConfig(
        base_url="https://n8n.bhuvisx.com",
        lead_webhook_url="https://n8n.bhuvisx.com/webhook/test-id",
        webhook_secret="my-secret",
        timeout_seconds=15,
    )
    service = N8nService(cfg)
    payload = build_test_payload()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='{"ok":true}')

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_cm)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("integrations.n8n.service.aiohttp.ClientSession", return_value=mock_session):
        result = await service.send_lead_qualified(payload)

    assert result.ok is True
    assert result.status_code == 200
    call_kwargs = mock_session.post.call_args
    assert call_kwargs[0][0] == cfg.lead_webhook_url
    headers = call_kwargs[1]["headers"]
    assert headers["X-Aakashvani-Webhook-Secret"] == "my-secret"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_fire_event_webhook_uses_n8n_service_for_lead_qualified(monkeypatch):
    client_id = uuid4()
    lead_id = uuid4()
    campaign_id = uuid4()

    monkeypatch.setenv("N8N_LEAD_WEBHOOK_URL", "https://n8n.bhuvisx.com/webhook/test")

    with patch(
        "integrations.n8n.service.N8nService.send_lead_qualified",
        new_callable=AsyncMock,
    ) as mock_send:
        from integrations.n8n.service import N8nSendResult

        mock_send.return_value = N8nSendResult(ok=True, status_code=200)
        with patch("db.postgres.get_webhook_config_for_event", new=AsyncMock(return_value=None)):
            from n8n_webhook import fire_event_webhook

            await fire_event_webhook(
                None,
                client_id,
                "lead_qualified",
                session_call_id="call_1",
                lead={"id": lead_id, "name": "A", "phone": "+91111", "metadata": {}},
                campaign={"id": campaign_id, "name": "C1"},
                extraction={"intent_status": "Interested", "summary": "Interested in demo"},
                duration_seconds=30,
                billed_minutes=1,
                credits_charged=1.0,
                route="sts",
                outcome="Interested",
            )

    assert mock_send.await_count == 1
    payload = mock_send.await_args.args[0]
    assert payload["event"] == "lead_qualified"
    assert payload["extraction"]["intent_status"] == "Interested"
    assert payload["lead"]["phone"] == "+91111"


@pytest.mark.asyncio
async def test_generic_client_webhook_does_not_skip_mega_followup(monkeypatch):
    client_id = uuid4()
    lead_id = uuid4()
    monkeypatch.setenv("N8N_LEAD_WEBHOOK_URL", "https://n8n.bhuvisx.com/webhook/mega")

    with patch(
        "integrations.n8n.service.N8nService.send_lead_qualified",
        new_callable=AsyncMock,
    ) as mock_send:
        from integrations.n8n.service import N8nSendResult

        mock_send.return_value = N8nSendResult(ok=True, status_code=200)
        with patch(
            "db.postgres.get_webhook_config_for_event",
            new=AsyncMock(return_value={"url": "https://crm.example.com/hook", "secret": "s"}),
        ), patch("n8n_webhook._post_signed", new_callable=AsyncMock) as mock_generic:
            from n8n_webhook import fire_event_webhook

            await fire_event_webhook(
                None,
                client_id,
                "lead_qualified",
                session_call_id="call_2",
                lead={"id": lead_id, "name": "B", "phone": "+919999", "metadata": {}},
                campaign={"id": uuid4(), "name": "C2"},
                extraction={"intent_status": "Interested"},
                duration_seconds=10,
                billed_minutes=1,
                credits_charged=1.0,
                route="sts",
                outcome="Interested",
            )

    mock_generic.assert_awaited_once()
    assert mock_send.await_count == 1


def test_production_does_not_use_ngrok_for_record_url(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("NGROK_URL", "https://stale.ngrok-free.dev")
    monkeypatch.delenv("AAKASHVANI_PUBLIC_URL", raising=False)
    from integrations.n8n.payload import public_backend_base_url

    assert public_backend_base_url() is None

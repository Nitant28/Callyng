"""Tests for follow-up service, n8n settings, and manual follow-up API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from integrations.n8n.url_validation import validate_n8n_webhook_url


def test_validate_n8n_webhook_url_accepts_https():
    ok, err = validate_n8n_webhook_url("https://n8n.bhuvisx.com/webhook/abc")
    assert ok is True
    assert err is None


def test_validate_n8n_webhook_url_rejects_http():
    ok, err = validate_n8n_webhook_url("http://n8n.bhuvisx.com/webhook/abc")
    assert ok is False
    assert "HTTPS" in (err or "")


def test_validate_n8n_webhook_url_rejects_localhost():
    ok, err = validate_n8n_webhook_url("https://localhost/webhook/x")
    assert ok is False


def test_payload_includes_flow_type_and_interested():
    from integrations.n8n.payload import build_lead_qualified_payload

    payload = build_lead_qualified_payload(
        client_id=uuid4(),
        lead={"id": uuid4(), "name": "A", "phone": "9359210080", "metadata": {"email": "getin2grave@gmail.com"}},
        session_call_id="call_x",
        duration_seconds=30,
        extraction={"intent_status": "Interested", "summary": "Test"},
        campaign={"id": uuid4(), "name": "Camp"},
        outcome="Interested",
    )
    assert payload["flow_type"] == "INITIAL_FOLLOWUP"
    assert payload["interested"] is True
    assert payload["event_type"] == "INTERESTED_LEAD"
    assert payload["lead"]["phone"] == "+919359210080"
    assert payload["lead"]["email"] == "getin2grave@gmail.com"


@pytest.mark.asyncio
async def test_trigger_follow_up_deduplicates_manual_click():
    from followups.service import trigger_follow_up

    client_id = uuid4()
    lead_id = uuid4()
    campaign_id = uuid4()

    pool = MagicMock()
    lead = {
        "id": lead_id,
        "campaign_id": campaign_id,
        "phone": "+919359210080",
        "name": "Test",
        "metadata": {"email": "getin2grave@gmail.com"},
        "outcome": "Interested",
    }
    campaign = {"id": campaign_id, "name": "C1"}

    with patch("followups.service.pg_db.get_lead", new=AsyncMock(return_value=lead)), patch(
        "followups.service.pg_db.get_campaign", new=AsyncMock(return_value=campaign)
    ), patch("followups.service.pg_db.get_client", new=AsyncMock(return_value={"name": "Client"})), patch(
        "followups.service.repo.recent_for_lead",
        new=AsyncMock(return_value={"status": "queued", "id": uuid4()}),
    ), patch("followups.service.N8nService.send_lead_qualified", new=AsyncMock()) as mock_send:
        result = await trigger_follow_up(pool, client_id=client_id, lead_id=lead_id, source="manual")
        assert result["ok"] is True
        assert result["deduplicated"] is True
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_n8n_config_resolve_prefers_database(monkeypatch):
    from integrations.n8n.config import N8nConfig

    monkeypatch.delenv("N8N_LEAD_WEBHOOK_URL", raising=False)
    pool = MagicMock()
    with patch(
        "followups.repository.get_setting",
        new=AsyncMock(return_value="https://n8n.bhuvisx.com/webhook/db-override"),
    ):
        cfg = await N8nConfig.resolve(pool)
    assert cfg.lead_webhook_url.endswith("/webhook/db-override")
    assert cfg.is_configured is True


@pytest.mark.asyncio
async def test_fire_event_webhook_deduplicates_auto_follow_up(monkeypatch):
    client_id = uuid4()
    lead_id = uuid4()
    campaign_id = uuid4()

    monkeypatch.setenv("N8N_LEAD_WEBHOOK_URL", "https://n8n.bhuvisx.com/webhook/test")

    existing = {"status": "queued", "idempotency_key": f"auto:call_1:{lead_id}"}
    with patch("db.postgres.get_webhook_config_for_event", new=AsyncMock(return_value=None)), patch(
        "followups.repository.get_by_idempotency", new=AsyncMock(return_value=existing)
    ), patch("integrations.n8n.service.N8nService.send_lead_qualified", new=AsyncMock()) as mock_send:
        from n8n_webhook import fire_event_webhook

        await fire_event_webhook(
            MagicMock(),
            client_id,
            "lead_qualified",
            session_call_id="call_1",
            lead={"id": lead_id, "name": "A", "phone": "+919359210080", "metadata": {}},
            campaign={"id": campaign_id, "name": "C1"},
            extraction={"intent_status": "Interested"},
            duration_seconds=30,
            billed_minutes=1,
            credits_charged=1.0,
            route="sts",
            outcome="Interested",
        )
        mock_send.assert_not_called()

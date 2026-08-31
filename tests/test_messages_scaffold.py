"""Tests for the extended Messages module — providers, send, follow-ups."""

from __future__ import annotations

import pytest

from messages.credentials import decrypt_credentials, encrypt_credentials, decrypt_secret_map, encrypt_secret_map, public_integration_view
from messages.providers.factory import get_provider, provider_catalog, PROVIDER_KEYS
from messages.providers.base import ProviderSendResult


def test_credentials_roundtrip():
    blob = encrypt_credentials("super-secret-token")
    assert blob and "super-secret-token" not in blob
    assert decrypt_credentials(blob) == "super-secret-token"


def test_secret_map_roundtrip():
    secrets = {"access_token": "tok123", "app_secret": "sec456"}
    blob = encrypt_secret_map(secrets)
    assert blob
    recovered = decrypt_secret_map(blob)
    assert recovered["access_token"] == "tok123"
    assert recovered["app_secret"] == "sec456"


def test_public_view_strips_secrets():
    view = public_integration_view({
        "id": "00000000-0000-4000-8000-000000000099",
        "client_id": "00000000-0000-4000-8000-000000000001",
        "provider": "meta_cloud",
        "display_name": "Test",
        "phone_number_id": "pn",
        "business_account_id": "ba",
        "status": "active",
        "enabled": True,
        "connection_status": "connected",
        "last_tested_at": None,
        "last_error": None,
        "credentials_encrypted": "some_blob",
        "webhook_verify_token": "verify",
        "configuration": '{"base_url": "https://x.com", "access_token": "LEAK"}',
        "created_at": None,
        "updated_at": None,
    })
    assert view["credentials_configured"] is True
    assert "credentials_encrypted" not in view
    assert "access_token" not in str(view.get("configuration", {}))
    assert view["enabled"] is True
    assert view["connection_status"] == "connected"


def test_provider_catalog_keys():
    catalog = provider_catalog()
    keys = [p["key"] for p in catalog]
    assert "stub" in keys
    assert "meta_cloud" in keys
    assert "finbite" in keys
    assert "wapi" in keys
    assert "custom" in keys
    assert "aakashvani_managed" in keys


def test_get_provider_returns_correct_types():
    assert get_provider("stub").name == "stub"
    assert get_provider("meta_cloud").name == "meta_cloud"
    assert get_provider("custom").name == "custom"
    assert get_provider("finbite").name == "finbite"
    assert get_provider("wapi").name == "wapi"
    assert get_provider("unknown").name == "stub"


@pytest.mark.asyncio
async def test_stub_refuses_send():
    p = get_provider("stub")
    result = await p.send_text({}, to_phone="+919999999999", text="hi")
    assert result.ok is False

    ok, msg = await p.test_connection({})
    assert ok is False


@pytest.mark.asyncio
async def test_stub_simulated_send():
    p = get_provider("stub")
    result = await p.send_text({"allow_simulated_send": True}, to_phone="+919999999999", text="hi")
    assert result.ok is True
    assert result.provider_message_id and result.provider_message_id.startswith("stub_")


@pytest.mark.asyncio
async def test_pending_provider_refuses():
    for name in ("finbite", "wapi", "aakashvani_managed"):
        p = get_provider(name)
        ok, msg = await p.test_connection({})
        assert ok is False
        assert "documentation" in msg.lower()
        result = await p.send_text({}, to_phone="+91999", text="hi")
        assert result.ok is False


@pytest.mark.asyncio
async def test_meta_refuses_without_credentials():
    p = get_provider("meta_cloud")
    ok, msg = await p.test_connection({})
    assert ok is False
    assert "phone_number_id" in msg.lower() or "access_token" in msg.lower()
    result = await p.send_text({}, to_phone="+91999", text="hi")
    assert result.ok is False


def test_meta_parse_webhook_incoming():
    p = get_provider("meta_cloud")
    body = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid.abc",
                        "from": "919999999999",
                        "type": "text",
                        "text": {"body": "Hello"},
                    }],
                }
            }]
        }]
    }
    events = p.parse_webhook({}, body)
    assert len(events) == 1
    assert events[0].event_type == "message"
    assert events[0].provider_message_id == "wamid.abc"
    assert events[0].text == "Hello"
    assert events[0].direction == "incoming"


def test_meta_parse_webhook_status():
    p = get_provider("meta_cloud")
    body = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": "wamid.xyz",
                        "status": "delivered",
                        "recipient_id": "919999999999",
                    }],
                }
            }]
        }]
    }
    events = p.parse_webhook({}, body)
    assert len(events) == 1
    assert events[0].event_type == "status"
    assert events[0].status == "delivered"


@pytest.mark.asyncio
async def test_custom_refuses_without_config():
    p = get_provider("custom")
    ok, msg = await p.test_connection({})
    assert ok is False
    result = await p.send_text({}, to_phone="+91999", text="hi")
    assert result.ok is False

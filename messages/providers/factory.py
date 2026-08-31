"""Provider factory + admin field schemas.

FinBite/Wapi/managed adapters exist as named slots but refuse live HTTP
until their API documentation is provided. Meta uses official Graph API
paths only when credentials are present. Custom uses Aakashvani's own
generic HTTP contract (not a third-party BSP spec).
"""

from __future__ import annotations

from typing import Any

from messages.providers.base import WhatsAppProvider
from messages.providers.custom import CustomWhatsAppProvider
from messages.providers.meta import MetaCloudProvider
from messages.providers.pending import PendingDocsProvider
from messages.providers.stub import StubWhatsAppProvider

PROVIDER_KEYS = (
    "stub",
    "meta_cloud",
    "finbite",
    "wapi",
    "aakashvani_managed",
    "custom",
    "other",
)

_FIELD_COMMON_NAME = {
    "key": "display_name",
    "label": "Display name",
    "secret": False,
}

PROVIDER_FIELD_SCHEMAS: dict[str, dict[str, Any]] = {
    "stub": {
        "label": "Stub (dev only)",
        "live": False,
        "note": "Never sends real WhatsApp. Used for local tests.",
        "fields": [_FIELD_COMMON_NAME],
    },
    "meta_cloud": {
        "label": "Meta Cloud API",
        "live": True,
        "note": "Official Graph API. Requires a real access token; none is shipped in this repo.",
        "fields": [
            _FIELD_COMMON_NAME,
            {"key": "phone_number_id", "label": "Phone number ID", "secret": False},
            {"key": "business_account_id", "label": "Business account ID", "secret": False},
            {"key": "webhook_verify_token", "label": "Webhook verify token", "secret": True},
            {"key": "access_token", "label": "Access token", "secret": True},
            {"key": "app_secret", "label": "App secret (webhook signatures)", "secret": True},
        ],
    },
    "finbite": {
        "label": "FinBite",
        "live": False,
        "note": "Adapter reserved. Do not invent endpoints until FinBite API documentation is available.",
        "fields": [_FIELD_COMMON_NAME],
    },
    "wapi": {
        "label": "Wapi",
        "live": False,
        "note": "Adapter reserved. Do not invent endpoints until Wapi API documentation is available.",
        "fields": [_FIELD_COMMON_NAME],
    },
    "aakashvani_managed": {
        "label": "Aakashvani managed",
        "live": False,
        "note": "Reserved for a BhuvisX/Aakashvani-operated BSP. Not live.",
        "fields": [_FIELD_COMMON_NAME],
    },
    "custom": {
        "label": "Custom HTTP",
        "live": True,
        "note": "Aakashvani generic contract: POST {base_url}/messages with Bearer API key.",
        "fields": [
            _FIELD_COMMON_NAME,
            {"key": "base_url", "label": "Base URL", "secret": False},
            {"key": "sender_id", "label": "Sender ID", "secret": False},
            {"key": "webhook_verify_token", "label": "Webhook verify token", "secret": True},
            {"key": "api_key", "label": "API key", "secret": True},
        ],
    },
    "other": {
        "label": "Other (legacy)",
        "live": False,
        "note": "Legacy alias. Prefer finbite, wapi, custom, or aakashvani_managed.",
        "fields": [_FIELD_COMMON_NAME],
    },
}


def get_provider(provider_name: str) -> WhatsAppProvider:
    name = (provider_name or "stub").strip().lower()
    if name == "stub":
        return StubWhatsAppProvider()
    if name == "meta_cloud":
        return MetaCloudProvider()
    if name == "custom":
        return CustomWhatsAppProvider()
    if name in ("finbite", "wapi", "aakashvani_managed", "other"):
        return PendingDocsProvider(name)
    return StubWhatsAppProvider()


def provider_catalog() -> list[dict[str, Any]]:
    return [{"key": k, **PROVIDER_FIELD_SCHEMAS[k]} for k in PROVIDER_KEYS]

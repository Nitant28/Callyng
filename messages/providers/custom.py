"""Aakashvani-defined generic HTTP provider (not a third-party BSP spec).

Contract:
  POST {base_url}/messages
  Authorization: Bearer {api_key}
  JSON: {to, type, text?, template_name?, language?, components?, sender_id?}

  Inbound webhook body (normalized):
  { "aakashvani_event": true, "events": [ {event_type, provider_message_id, ...} ] }
"""

from __future__ import annotations

from typing import Any

import aiohttp

from messages.providers.base import ProviderSendResult, ProviderWebhookEvent, WhatsAppProvider


class CustomWhatsAppProvider(WhatsAppProvider):
    name = "custom"

    async def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        base = (config.get("base_url") or "").rstrip("/")
        key = (config.get("api_key") or "").strip()
        if not base or not key:
            return False, "Custom provider requires base_url and api_key."
        return True, "Custom provider configuration is present (no vendor health endpoint defined)."

    async def send_text(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        text: str,
    ) -> ProviderSendResult:
        return await self._post(
            config,
            {
                "to": to_phone,
                "type": "text",
                "text": text,
                "sender_id": config.get("sender_id"),
            },
        )

    async def send_template(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        template_name: str,
        language: str | None,
        components: dict[str, Any] | list | None,
    ) -> ProviderSendResult:
        return await self._post(
            config,
            {
                "to": to_phone,
                "type": "template",
                "template_name": template_name,
                "language": language,
                "components": components,
                "sender_id": config.get("sender_id"),
            },
        )

    async def _post(self, config: dict[str, Any], payload: dict[str, Any]) -> ProviderSendResult:
        base = (config.get("base_url") or "").rstrip("/")
        key = (config.get("api_key") or "").strip()
        if not base or not key:
            return ProviderSendResult(ok=False, error="Custom send skipped: base_url / api_key not configured.")
        url = f"{base}/messages"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    raw = await resp.json(content_type=None)
                    if resp.status >= 400:
                        return ProviderSendResult(ok=False, error=str(raw)[:500], raw=raw if isinstance(raw, dict) else {})
                    mid = raw.get("id") or raw.get("message_id") if isinstance(raw, dict) else None
                    return ProviderSendResult(ok=True, provider_message_id=mid, raw=raw if isinstance(raw, dict) else {})
        except Exception as exc:
            return ProviderSendResult(ok=False, error=str(exc))

    def parse_webhook(self, headers: dict[str, str], body: dict[str, Any] | list | None) -> list[ProviderWebhookEvent]:
        if not isinstance(body, dict) or not body.get("aakashvani_event"):
            return []
        out: list[ProviderWebhookEvent] = []
        for item in body.get("events") or []:
            if not isinstance(item, dict):
                continue
            out.append(
                ProviderWebhookEvent(
                    event_type=item.get("event_type") or "message",
                    provider_message_id=item.get("provider_message_id"),
                    customer_phone=item.get("customer_phone"),
                    direction=item.get("direction") or "incoming",
                    message_type=item.get("message_type") or "text",
                    text=item.get("text"),
                    status=item.get("status") or "received",
                    raw=item,
                )
            )
        return out

    def verify_webhook(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
        raw_body: bytes,
        query: dict[str, str],
    ) -> bool:
        expected = (config.get("webhook_verify_token") or "").strip()
        token = (
            headers.get("x-aakashvani-webhook-token")
            or query.get("verify_token")
            or query.get("hub.verify_token")
            or ""
        ).strip()
        if query.get("hub.mode") == "subscribe" or query.get("mode") == "subscribe":
            return bool(expected and token and expected == token)
        return bool(expected and token and expected == token)

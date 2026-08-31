"""Stub provider — development only. Never a production WhatsApp path."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from messages.providers.base import ProviderSendResult, ProviderWebhookEvent, WhatsAppProvider


class StubWhatsAppProvider(WhatsAppProvider):
    name = "stub"

    async def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        if config.get("allow_simulated_send"):
            return True, "Stub simulated connection OK (not a real WhatsApp network)."
        return False, (
            "Stub provider cannot connect to WhatsApp. "
            "Select Meta Cloud or another live provider after credentials exist."
        )

    async def send_text(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        text: str,
    ) -> ProviderSendResult:
        if config.get("allow_simulated_send"):
            return ProviderSendResult(
                ok=True,
                provider_message_id=f"stub_{uuid4().hex[:16]}",
                raw={"simulated": True, "to": to_phone, "text": text},
            )
        return ProviderSendResult(
            ok=False,
            error="Stub provider refuses send_text — not a live WhatsApp network.",
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
        if config.get("allow_simulated_send"):
            return ProviderSendResult(
                ok=True,
                provider_message_id=f"stub_{uuid4().hex[:16]}",
                raw={"simulated": True, "to": to_phone, "template": template_name},
            )
        return ProviderSendResult(
            ok=False,
            error="Stub provider refuses send_template — not a live WhatsApp network.",
        )

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
            or query.get("hub.verify_token")
            or query.get("verify_token")
            or ""
        ).strip()
        if not expected:
            return bool(config.get("allow_simulated_send"))
        return bool(token and expected == token)

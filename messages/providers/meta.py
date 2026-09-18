"""Meta Cloud API adapter — official Graph WhatsApp endpoints only.

Does not ship credentials. HTTP is skipped when access_token is missing.
Webhook parse follows Meta's documented Cloud API webhook envelope.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import aiohttp

from messages.providers.base import ProviderSendResult, ProviderWebhookEvent, WhatsAppProvider

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class MetaCloudProvider(WhatsAppProvider):
    name = "meta_cloud"

    async def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        token = (config.get("access_token") or "").strip()
        phone_id = (config.get("phone_number_id") or "").strip()
        if not token or not phone_id:
            return False, "Meta Cloud requires phone_number_id and access_token. None are stored in this repo."
        url = f"{GRAPH_BASE}/{phone_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params={"access_token": token}) as resp:
                    if resp.status < 400:
                        return True, "Meta Cloud phone number ID is reachable."
                    body = (await resp.text())[:300]
                    return False, f"Meta Cloud HTTP {resp.status}: {body}"
        except Exception as exc:
            return False, f"Meta Cloud request failed: {exc}"

    async def send_text(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        text: str,
    ) -> ProviderSendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {"body": text},
        }
        return await self._post_messages(config, payload)

    async def send_template(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        template_name: str,
        language: str | None,
        components: dict[str, Any] | list | None,
    ) -> ProviderSendResult:
        from followups.template_ref import TemplateRefError, meta_template_payload

        try:
            payload = meta_template_payload(
                to_phone=to_phone,
                template_name=template_name,
                language_code=language or "en_US",
                components=components,
            )
        except TemplateRefError as exc:
            return ProviderSendResult(ok=False, error=exc.code)
        return await self._post_messages(config, payload)

    async def _post_messages(self, config: dict[str, Any], payload: dict[str, Any]) -> ProviderSendResult:
        token = (config.get("access_token") or "").strip()
        phone_id = (config.get("phone_number_id") or "").strip()
        if not token or not phone_id:
            return ProviderSendResult(
                ok=False,
                error="Meta Cloud send skipped: access_token / phone_number_id not configured.",
            )
        url = f"{GRAPH_BASE}/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    raw = await resp.json(content_type=None)
                    if resp.status >= 400:
                        err = raw.get("error", {}) if isinstance(raw, dict) else {}
                        return ProviderSendResult(
                            ok=False,
                            error=str(err.get("message") or raw)[:500],
                            raw=raw if isinstance(raw, dict) else {"body": raw},
                        )
                    msg_id = None
                    if isinstance(raw, dict):
                        messages = raw.get("messages") or []
                        if messages:
                            msg_id = messages[0].get("id")
                    return ProviderSendResult(ok=True, provider_message_id=msg_id, raw=raw if isinstance(raw, dict) else {})
        except Exception as exc:
            return ProviderSendResult(ok=False, error=str(exc))

    def verify_webhook(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
        raw_body: bytes,
        query: dict[str, str],
    ) -> bool:
        expected = (config.get("webhook_verify_token") or "").strip()
        if query.get("hub.mode") == "subscribe" or query.get("mode") == "subscribe":
            token = (query.get("hub.verify_token") or query.get("verify_token") or "").strip()
            return bool(expected and token and expected == token)

        app_secret = (config.get("app_secret") or "").strip()
        if not app_secret:
            # Fail closed: POST events require a configured app secret.
            return False

        sig = (headers.get("x-hub-signature-256") or "").strip()
        if not sig.startswith("sha256="):
            return False
        digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, f"sha256={digest}")

    def parse_webhook(self, headers: dict[str, str], body: dict[str, Any] | list | None) -> list[ProviderWebhookEvent]:
        if not isinstance(body, dict):
            return []
        events: list[ProviderWebhookEvent] = []
        for entry in body.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                value = (change or {}).get("value") or {}
                meta = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                phone_number_id = meta.get("phone_number_id")
                for msg in value.get("messages") or []:
                    text = None
                    msg_type = msg.get("type") or "text"
                    if msg_type == "text":
                        text = (msg.get("text") or {}).get("body")
                    elif msg_type == "button":
                        btn = msg.get("button") or {}
                        text = btn.get("text") or btn.get("payload")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive") or {}
                        itype = interactive.get("type")
                        block = interactive.get(itype) if itype else None
                        if isinstance(block, dict):
                            text = block.get("title") or block.get("id") or block.get("text")
                    events.append(
                        ProviderWebhookEvent(
                            event_type="message",
                            provider_message_id=msg.get("id"),
                            customer_phone=msg.get("from"),
                            direction="incoming",
                            message_type=msg_type,
                            text=text,
                            status="received",
                            raw={**msg, "_phone_number_id": phone_number_id},
                        )
                    )
                for st in value.get("statuses") or []:
                    events.append(
                        ProviderWebhookEvent(
                            event_type="status",
                            provider_message_id=st.get("id"),
                            customer_phone=st.get("recipient_id"),
                            direction="outgoing",
                            message_type="status",
                            status=st.get("status"),
                            raw=st,
                        )
                    )
        return events
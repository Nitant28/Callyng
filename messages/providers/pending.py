"""Named BSP slots that refuse live I/O until official API docs exist."""

from __future__ import annotations

from typing import Any

from messages.providers.base import ProviderSendResult, ProviderWebhookEvent, WhatsAppProvider

_LABELS = {
    "finbite": "FinBite",
    "wapi": "Wapi",
    "aakashvani_managed": "Aakashvani managed provider",
    "other": "Other provider",
}


class PendingDocsProvider(WhatsAppProvider):
    def __init__(self, name: str):
        self.name = name
        self._label = _LABELS.get(name, name)

    def _blocked(self, action: str) -> str:
        return (
            f"{self._label} {action} is not implemented. "
            "Provide the vendor API documentation (auth, send, templates, webhooks) "
            "before enabling live traffic."
        )

    async def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        return False, self._blocked("connection test")

    async def send_text(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        text: str,
    ) -> ProviderSendResult:
        return ProviderSendResult(ok=False, error=self._blocked("send_text"))

    async def send_template(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        template_name: str,
        language: str | None,
        components: dict[str, Any] | list | None,
    ) -> ProviderSendResult:
        return ProviderSendResult(ok=False, error=self._blocked("send_template"))

    def parse_webhook(self, headers: dict[str, str], body: dict[str, Any] | list | None) -> list[ProviderWebhookEvent]:
        return []

    def verify_webhook(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
        raw_body: bytes,
        query: dict[str, str],
    ) -> bool:
        expected = (config.get("webhook_verify_token") or "").strip()
        token = (query.get("hub.verify_token") or query.get("verify_token") or "").strip()
        return bool(expected and token and expected == token)

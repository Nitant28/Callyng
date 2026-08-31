"""Messages / WhatsApp module — provider abstraction (no invented live APIs)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderSendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderWebhookEvent:
    """Normalized inbound event — concrete providers map documented payloads here."""

    event_type: str  # message | status | unknown
    provider_message_id: str | None = None
    customer_phone: str | None = None
    direction: str | None = None
    message_type: str | None = None
    text: str | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class WhatsAppProvider(ABC):
    """Interface for WhatsApp BSPs. Do not call provider HTTP APIs from React."""

    name: str = "base"

    @abstractmethod
    async def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    async def send_text(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        text: str,
    ) -> ProviderSendResult:
        raise NotImplementedError

    @abstractmethod
    async def send_template(
        self,
        config: dict[str, Any],
        *,
        to_phone: str,
        template_name: str,
        language: str | None,
        components: dict[str, Any] | list | None,
    ) -> ProviderSendResult:
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, headers: dict[str, str], body: dict[str, Any] | list | None) -> list[ProviderWebhookEvent]:
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
        raw_body: bytes,
        query: dict[str, str],
    ) -> bool:
        raise NotImplementedError

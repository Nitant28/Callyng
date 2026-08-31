"""HTTPS client for remote n8n (production Mega_Workflow webhook)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

from integrations.n8n.config import N8nConfig


@dataclass
class N8nSendResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None
    skipped: bool = False
    response_preview: str | None = None


class N8nService:
    """POST normalized events to the remote n8n production webhook.

    Does not install, login to, or manage n8n — webhook-only integration.
    """

    def __init__(self, config: N8nConfig | None = None, *, pool=None):
        self._pool = pool
        self.config = config or N8nConfig.from_env()

    async def _resolved_config(self, *, client_id=None) -> N8nConfig:
        if self._pool is not None:
            resolved = await N8nConfig.resolve(self._pool, client_id=client_id)
            if resolved.lead_webhook_url:
                return resolved
        if self.config.lead_webhook_url:
            return self.config
        return self.config

    def is_configured(self) -> bool:
        return self.config.is_configured

    async def send_lead_qualified(self, payload: dict[str, Any]) -> N8nSendResult:
        return await self._post(payload, event_label="lead_qualified")

    async def send_test_event(self, payload: dict[str, Any] | None = None) -> N8nSendResult:
        from integrations.n8n.payload import build_connectivity_test_payload

        body = payload or build_connectivity_test_payload()
        return await self._post(body, event_label="connectivity_test")

    async def _post(self, payload: dict[str, Any], *, event_label: str, client_id=None) -> N8nSendResult:
        cfg = await self._resolved_config(client_id=client_id)
        url = cfg.lead_webhook_url
        if not url:
            logger.debug("n8n skipped ({}): N8N_LEAD_WEBHOOK_URL not set", event_label)
            return N8nSendResult(ok=False, skipped=True, error="N8N_LEAD_WEBHOOK_URL not configured")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if cfg.webhook_secret:
            headers["X-Aakashvani-Webhook-Secret"] = cfg.webhook_secret

        event_id = payload.get("event_id") or payload.get("event")
        logger.info(
            "n8n POST {} → {} (timeout {}s, event_id={})",
            event_label,
            self._safe_url(url),
            cfg.timeout_seconds,
            event_id,
        )

        timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
        last_error: str | None = None

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        preview = (await resp.text())[:500]
                        if resp.status >= 400:
                            last_error = f"HTTP {resp.status}: {preview}"
                            logger.warning(
                                "n8n HTTP {} (attempt {}): {}",
                                resp.status,
                                attempt + 1,
                                preview[:200],
                            )
                            if resp.status < 500:
                                return N8nSendResult(
                                    ok=False,
                                    status_code=resp.status,
                                    error=last_error,
                                    response_preview=preview,
                                )
                        else:
                            logger.info("n8n HTTP {} ok (event_id={})", resp.status, event_id)
                            return N8nSendResult(
                                ok=True,
                                status_code=resp.status,
                                response_preview=preview,
                            )
            except asyncio.TimeoutError:
                last_error = f"timeout after {cfg.timeout_seconds}s"
                logger.warning("n8n timeout (attempt {}): {}", attempt + 1, last_error)
            except aiohttp.ClientError as exc:
                last_error = str(exc)
                logger.warning("n8n connection error (attempt {}): {}", attempt + 1, exc)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("n8n unexpected error (attempt {}): {}", attempt + 1, exc)

            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

        return N8nSendResult(ok=False, error=last_error or "request failed")

    @staticmethod
    def _safe_url(url: str) -> str:
        """Log URL without query secrets."""
        return url.split("?")[0]

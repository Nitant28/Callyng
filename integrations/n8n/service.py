"""HTTPS client for remote n8n (production Mega_Workflow webhook)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import aiohttp
from loguru import logger

from integrations.n8n.config import N8nConfig


def _payload_client_id(payload: dict[str, Any] | None) -> UUID | None:
    """Extract tenant id from a lead_qualified payload. Never invent one."""
    if not payload:
        return None
    raw = payload.get("client_id")
    if raw is None:
        client = payload.get("client")
        if isinstance(client, dict):
            raw = client.get("id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


@dataclass
class N8nSendResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None
    skipped: bool = False
    response_preview: str | None = None
    retryable: bool = False
    error_category: str | None = None


class N8nService:
    """POST normalized events to the remote n8n production webhook.

    Does not install, login to, or manage n8n — webhook-only integration.
    """

    def __init__(self, config: N8nConfig | None = None, *, pool=None):
        self._pool = pool
        self.config = config or N8nConfig.from_env()

    async def _resolved_config(self, *, client_id=None) -> N8nConfig:
        # Caller must supply the campaign-resolved URL. Never fall back to the
        # retired global N8N_LEAD_WEBHOOK_URL / DB setting for outbound sends.
        return self.config

    def is_configured(self) -> bool:
        return self.config.is_configured

    @classmethod
    def for_resolved_url(cls, webhook_url: str, *, pool=None, url_source: str | None = None):
        env = N8nConfig.from_env()
        return cls(
            N8nConfig(
                base_url=env.base_url,
                lead_webhook_url=webhook_url,
                webhook_secret=env.webhook_secret,
                timeout_seconds=env.timeout_seconds,
                url_source=url_source,
            ),
            pool=pool,
        )

    async def send_lead_qualified(self, payload: dict[str, Any]) -> N8nSendResult:
        return await self._post(
            payload,
            event_label="lead_qualified",
            client_id=_payload_client_id(payload),
        )

    async def send_test_event(self, payload: dict[str, Any] | None = None) -> N8nSendResult:
        from integrations.n8n.payload import build_connectivity_test_payload

        body = payload or build_connectivity_test_payload()
        return await self._post(body, event_label="connectivity_test")

    async def _post(self, payload: dict[str, Any], *, event_label: str, client_id=None) -> N8nSendResult:
        from followups.idempotency import classify_http_failure

        cfg = await self._resolved_config(client_id=client_id)
        url = cfg.lead_webhook_url
        if not url:
            logger.debug("n8n skipped ({}): N8N_LEAD_WEBHOOK_URL not set", event_label)
            return N8nSendResult(
                ok=False,
                skipped=True,
                error="N8N_LEAD_WEBHOOK_URL not configured",
                retryable=False,
                error_category="permanent",
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Serialize once so HMAC matches the exact request body.
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        if cfg.webhook_secret:
            headers["X-Aakashvani-Webhook-Secret"] = cfg.webhook_secret
            try:
                from n8n_webhook import sign_payload

                headers["X-Aakashvani-Signature"] = sign_payload(payload, cfg.webhook_secret)
            except Exception:
                pass

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
        last_status: int | None = None

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, data=body, headers=headers) as resp:
                        preview = (await resp.text())[:500]
                        last_status = resp.status
                        if resp.status >= 400:
                            last_error = f"HTTP {resp.status}: {preview}"
                            logger.warning(
                                "n8n HTTP {} (attempt {}): {}",
                                resp.status,
                                attempt + 1,
                                preview[:200],
                            )
                            category, retryable = classify_http_failure(resp.status, last_error)
                            if not retryable:
                                return N8nSendResult(
                                    ok=False,
                                    status_code=resp.status,
                                    error=last_error,
                                    response_preview=preview,
                                    retryable=False,
                                    error_category=category,
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
                last_status = None
                logger.warning("n8n timeout (attempt {}): {}", attempt + 1, last_error)
            except aiohttp.ClientError as exc:
                last_error = str(exc)
                last_status = None
                logger.warning("n8n connection error (attempt {}): {}", attempt + 1, exc)
            except Exception as exc:
                last_error = str(exc)
                last_status = None
                logger.warning("n8n unexpected error (attempt {}): {}", attempt + 1, exc)

            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

        category, retryable = classify_http_failure(last_status, last_error)
        return N8nSendResult(
            ok=False,
            status_code=last_status,
            error=last_error or "request failed",
            retryable=retryable,
            error_category=category,
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        """Log URL without query secrets."""
        return url.split("?")[0]

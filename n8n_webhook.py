"""Outbound POST to an n8n workflow webhook after a call completes."""

from __future__ import annotations

import os
from typing import Any

import aiohttp
from loguru import logger

_DEFAULT_TIMEOUT_S = 30


async def send_call_completed_webhook(payload: dict[str, Any]) -> None:
    """
    POST ``payload`` as JSON to ``N8N_WEBHOOK_URL`` if set.

    Optional ``N8N_WEBHOOK_SECRET`` is sent as ``X-Webhook-Secret`` for simple
    verification in n8n. Does not log the full URL (path may contain secrets).
    """
    url = (os.getenv("N8N_WEBHOOK_URL") or "").strip()
    if not url:
        logger.debug("n8n webhook skipped: N8N_WEBHOOK_URL not set")
        return

    headers: dict[str, str] = {"Content-Type": "application/json"}
    secret = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
    if secret:
        headers["X-Webhook-Secret"] = secret

    timeout_s = _DEFAULT_TIMEOUT_S
    try:
        timeout_s = max(5, int(os.getenv("N8N_WEBHOOK_TIMEOUT_S", str(_DEFAULT_TIMEOUT_S))))
    except ValueError:
        pass

    logger.info("n8n webhook: sending POST (timeout {}s)", timeout_s)
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body_preview = (await resp.text())[:500]
                if resp.status >= 400:
                    logger.warning(
                        "n8n webhook: HTTP {} — {}",
                        resp.status,
                        body_preview,
                    )
                else:
                    logger.info("n8n webhook: HTTP {} ok", resp.status)
    except Exception as exc:
        logger.warning("n8n webhook: request failed: {}", exc)

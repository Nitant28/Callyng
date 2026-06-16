"""Outbound POST to n8n workflow webhooks (Phase 0 env URL + Phase 2 per-event configs)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any
from uuid import UUID

import aiohttp
from loguru import logger

_DEFAULT_TIMEOUT_S = 30


def sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def outcome_to_event(outcome: str, event_map: dict[str, str] | None = None) -> str | None:
    if event_map and outcome in event_map:
        return event_map[outcome]
    mapping = {
        "Interested": "lead_qualified",
        "Not_Interested": "lead_not_interested",
        "Callback_Requested": "lead_callback",
    }
    if outcome in mapping:
        return mapping[outcome]
    if outcome in ("Busy", "Unknown", "Wrong_Requirement", "failed"):
        return "lead_failed"
    return None


async def _post_signed(
    url: str,
    payload: dict[str, Any],
    secret: str | None,
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> None:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if secret:
        headers["X-Aakashvani-Signature"] = sign_payload(payload, secret)

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


async def send_call_completed_webhook(payload: dict[str, Any]) -> None:
    """
    POST ``payload`` to ``N8N_WEBHOOK_URL`` if set (Phase 0 fallback).
    """
    url = (os.getenv("N8N_WEBHOOK_URL") or "").strip()
    if not url:
        logger.debug("n8n webhook skipped: N8N_WEBHOOK_URL not set")
        return

    secret = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip() or None
    timeout_s = _DEFAULT_TIMEOUT_S
    try:
        timeout_s = max(5, int(os.getenv("N8N_WEBHOOK_TIMEOUT_S", str(_DEFAULT_TIMEOUT_S))))
    except ValueError:
        pass
    await _post_signed(url, payload, secret, timeout_s=timeout_s)


async def fire_event_webhook(
    pool,
    client_id: UUID,
    event: str,
    *,
    session_call_id: str,
    lead: dict,
    campaign: dict,
    extraction: dict,
    duration_seconds: int,
    billed_minutes: int,
    credits_charged: float,
    route: str | None,
) -> None:
    from db import postgres as pg_db

    cfg = await pg_db.get_webhook_config_for_event(pool, client_id, event)
    meta = lead.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}

    payload = {
        "event": event,
        "call": {
            "session_call_id": session_call_id,
            "duration_seconds": duration_seconds,
            "billed_minutes": billed_minutes,
            "credits_charged": credits_charged,
            "route": route,
            "recording_url": None,
        },
        "lead": {
            "phone": lead.get("phone"),
            "name": lead.get("name"),
            "lead_type": lead.get("lead_type"),
            "metadata": meta,
        },
        "extraction": extraction,
        "campaign": {
            "id": str(campaign.get("id")),
            "name": campaign.get("name"),
        },
    }

    if cfg:
        await _post_signed(
            cfg["url"],
            payload,
            cfg.get("secret"),
        )
        return

    # Phase 0 fallback
    payload["event"] = "call_completed"
    await send_call_completed_webhook(payload)


async def fire_campaign_completed_webhook(
    pool,
    client_id: UUID,
    campaign: dict,
) -> None:
    from db import postgres as pg_db

    event = "campaign_completed"
    cfg = await pg_db.get_webhook_config_for_event(pool, client_id, event)
    if not cfg:
        logger.debug("n8n webhook skipped: no config for campaign_completed")
        return

    payload = {
        "event": event,
        "campaign": {
            "id": str(campaign.get("id")),
            "name": campaign.get("name"),
            "status": campaign.get("status"),
            "budget_used_credits": float(campaign.get("budget_used_credits") or 0),
            "total_leads": int(campaign.get("total_leads") or 0),
            "completed_leads": int(campaign.get("completed_leads") or 0),
            "failed_leads": int(campaign.get("failed_leads") or 0),
        },
    }

    await _post_signed(
        cfg["url"],
        payload,
        cfg.get("secret"),
    )

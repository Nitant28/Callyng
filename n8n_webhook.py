"""Outbound POST to n8n workflow webhooks (Phase 0 env URL + Phase 2 per-event configs)."""

from __future__ import annotations

import asyncio
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
    from followups.interested import canonicalize_intent, is_interested_outcome, is_negative_intent

    oc = canonicalize_intent(outcome)
    if event_map:
        for k, v in event_map.items():
            if canonicalize_intent(k) == oc:
                return v

    if is_negative_intent(oc):
        return "lead_not_interested"
    if is_interested_outcome(oc):
        return "lead_qualified"

    mapping = {
        "callback requested": "lead_callback",
        "early disconnect": "lead_callback",
        "busy": "lead_failed",
        "unknown": "lead_failed",
        "wrong requirement": "lead_failed",
        "failed": "lead_failed",
    }
    return mapping.get(oc)


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
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    body_preview = (await resp.text())[:500]
                    if resp.status >= 400:
                        logger.warning(
                            "n8n webhook: HTTP {} — {} (attempt {})",
                            resp.status,
                            body_preview,
                            attempt + 1,
                        )
                        if resp.status < 500:
                            return
                    else:
                        logger.info("n8n webhook: HTTP {} ok", resp.status)
                        return
        except Exception as exc:
            logger.warning("n8n webhook: request failed (attempt {}): {}", attempt + 1, exc)
            
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)


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
    billed_minutes: float,
    credits_charged: float,
    route: str | None,
    recording_url: str | None = None,
    bot_config_id: UUID | None = None,
    outcome: str | None = None,
) -> None:
    from db import postgres as pg_db

    cfg = await pg_db.get_webhook_config_for_event(pool, client_id, event)
    if cfg:
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
                "recording_url": recording_url,
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
        await _post_signed(
            cfg["url"],
            payload,
            cfg.get("secret"),
        )
        # Generic Admin → Webhooks is a CRM fan-out. Interested follow-up
        # still goes to Mega_Workflow below; other events stop here.
        if event != "lead_qualified":
            return

    if event == "lead_qualified":
        from integrations.n8n.config import N8nConfig
        from integrations.n8n.payload import build_lead_qualified_payload
        from integrations.n8n.service import N8nService
        from followups import repository as followups_repo
        from followups.service import record_auto_n8n_send

        try:
            n8n_cfg = await N8nConfig.resolve(pool, client_id=client_id)
            service = N8nService(n8n_cfg, pool=pool)
        except Exception as exc:
            logger.exception("n8n follow-up setup failed; call settlement continues: {}", exc)
            service = None
        if service is not None and service.is_configured():
            try:
                client_row = None
                if pool is not None:
                    try:
                        client_row = await pg_db.get_client(pool, client_id)
                    except Exception as exc:
                        logger.warning("n8n payload: could not load client {}: {}", client_id, exc)

                lead_id = lead.get("id")
                idem = f"auto:{session_call_id}:{lead_id}" if lead_id else None
                if pool and idem:
                    existing = await followups_repo.get_by_idempotency(pool, client_id, idem)
                    if existing and existing.get("status") in ("queued", "sent", "accepted"):
                        logger.info(
                            "n8n auto follow-up deduplicated lead={} call={}",
                            lead_id,
                            session_call_id,
                        )
                        return

                payload = build_lead_qualified_payload(
                    client_id=client_id,
                    lead=lead,
                    session_call_id=session_call_id,
                    duration_seconds=duration_seconds,
                    extraction=extraction,
                    campaign=campaign,
                    outcome=outcome,
                    bot_config_id=bot_config_id,
                    billed_minutes=billed_minutes,
                    credits_charged=credits_charged,
                    route=route,
                    recording_url=recording_url,
                    client=client_row,
                )
                payload["flow_type"] = "INITIAL_FOLLOWUP"
                payload["interested"] = True
                payload["source"] = "auto"

                from followups.enrichment import enrich_lead_payload

                payload = await enrich_lead_payload(pool, payload, client_id=client_id)

                result = await service.send_lead_qualified(payload)
                if not result.skipped and pool:
                    await record_auto_n8n_send(
                        pool,
                        client_id=client_id,
                        lead=lead,
                        campaign=campaign,
                        session_call_id=session_call_id,
                        ok=result.ok,
                        error=result.error,
                    )
                if not result.skipped:
                    return
            except Exception:
                logger.exception("n8n follow-up dispatch failed; call settlement continues")
                return
        # fall through to legacy URL only if Mega_Workflow is not configured

    # Phase 0 fallback (legacy N8N_WEBHOOK_URL)
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
            "recording_url": recording_url,
        },
        "lead": {
            "id": str(lead.get("id")) if lead.get("id") else None,
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

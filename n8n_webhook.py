"""Outbound POST to campaign-scoped webhook configs (HMAC-signed when secret set)."""

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


def outcome_to_event(
    outcome: str,
    event_map: dict[str, str] | None = None,
    *,
    follow_up_target: str | None = None,
) -> str | None:
    """Map a normalized outcome to a webhook event.

    ``follow_up_target`` gates ``lead_qualified`` (campaign config). Other events
    (not interested / callback / failed) still resolve from the outcome itself.
    """
    from followups.interested import canonicalize_intent, evaluate_qualification, is_negative_intent

    oc = canonicalize_intent(outcome)
    event: str | None = None
    if event_map:
        for k, v in event_map.items():
            if canonicalize_intent(k) == oc:
                event = v
                break

    if event is None:
        decision = evaluate_qualification(outcome, follow_up_target)
        if decision["eligible"]:
            event = "lead_qualified"
        elif is_negative_intent(oc):
            event = "lead_not_interested"
        else:
            mapping = {
                "callback requested": "lead_callback",
                "early disconnect": "lead_callback",
                "busy": "lead_failed",
                "unknown": "lead_failed",
                "wrong requirement": "lead_failed",
                "failed": "lead_failed",
            }
            event = mapping.get(oc)

    # Explicit lead_qualified (including script event_map) still respects target.
    if event == "lead_qualified" and not evaluate_qualification(outcome, follow_up_target)["eligible"]:
        return None
    return event


async def _post_signed(
    url: str,
    payload: dict[str, Any],
    secret: str | None,
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> None:
    # Sign the exact bytes we transmit so receivers can verify.
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if secret:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Aakashvani-Signature"] = f"sha256={digest}"

    logger.info("n8n webhook: sending POST (timeout {}s)", timeout_s)
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=body, headers=headers) as resp:
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
    """Legacy env-only helper. Not used for campaign event routing."""
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


def _campaign_id(campaign: dict | None) -> UUID | None:
    if not campaign or not campaign.get("id"):
        return None
    try:
        return UUID(str(campaign["id"]))
    except (TypeError, ValueError):
        return None


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
    """Dispatch exactly one campaign+event webhook. No global/client fallback."""
    from db import postgres as pg_db
    from integrations.n8n.routing import resolve_campaign_webhook

    camp_id = _campaign_id(campaign)
    if camp_id is None:
        logger.info(
            "webhook NO SEND: missing campaign_id for event={} client={}",
            event,
            client_id,
        )
        return

    dest = await resolve_campaign_webhook(
        pool,
        client_id=client_id,
        campaign_id=camp_id,
        event=event,
        campaign=campaign,
    )
    if not dest.ok:
        logger.info(
            "webhook NO SEND: {} (client={} campaign={} event={})",
            dest.error or "no_webhook_configured_for_campaign_event",
            client_id,
            camp_id,
            event,
        )
        return

    if event == "lead_qualified":
        from followups.service import record_auto_n8n_send
        from followups import repository as followups_repo
        from followups.enrichment import enrich_lead_payload
        from integrations.n8n.payload import build_lead_qualified_payload
        from integrations.n8n.routing import n8n_config_for
        from integrations.n8n.service import N8nService

        try:
            lead_id = lead.get("id")
            idem = f"auto:{session_call_id}:{lead_id}" if lead_id else None
            if pool and idem and lead_id:
                claim = await followups_repo.claim_dispatch(
                    pool,
                    client_id=client_id,
                    campaign_id=camp_id,
                    lead_id=UUID(str(lead_id)),
                    channel="whatsapp",
                    source="auto",
                    idempotency_key=idem,
                    session_call_id=session_call_id,
                    message_preview="auto follow-up after interested call",
                )
                if not claim.claimed:
                    logger.info(
                        "n8n auto follow-up {} lead={} call={} status={}",
                        claim.reason,
                        lead_id,
                        session_call_id,
                        (claim.event or {}).get("status"),
                    )
                    return

            client_row = None
            if pool is not None:
                try:
                    client_row = await pg_db.get_client(pool, client_id)
                except Exception as exc:
                    logger.warning("n8n payload: could not load client {}: {}", client_id, exc)

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
                workflow=dest.as_payload(),
            )
            payload["flow_type"] = "INITIAL_FOLLOWUP"
            payload["interested"] = True
            payload["source"] = "auto"
            payload = await enrich_lead_payload(pool, payload, client_id=client_id)

            from followups.eligibility import any_channel_eligible, evaluate_channel_eligibility

            eligibility = evaluate_channel_eligibility(
                client_id=client_id,
                campaign_id=camp_id,
                lead_id=lead.get("id"),
                outcome=outcome or lead.get("outcome"),
                follow_up_target=(campaign or {}).get("follow_up_target"),
                lead=lead,
                first_contact=payload.get("first_contact"),
                whatsapp_integration=payload.get("whatsapp"),
                qualification=(extraction or {}).get("qualification")
                if isinstance(extraction, dict)
                else None,
                require_qualified=True,
            )
            payload["channel_eligibility"] = eligibility

            # Same canonical WhatsApp delivery as manual follow-up.
            from followups.delivery import deliver_whatsapp_follow_up

            wa_elig = (eligibility.get("channels") or {}).get("whatsapp") or {}
            if wa_elig.get("eligible") and pool is not None and lead_id:
                wa_delivery = await deliver_whatsapp_follow_up(
                    pool,
                    client_id=client_id,
                    lead=lead,
                    campaign=campaign,
                    first_contact=payload.get("first_contact") or {},
                    idempotency_key=f"{idem}:wa",
                )
                if wa_delivery.get("mode") == "backend" and wa_delivery.get("ok"):
                    payload["whatsapp_delivery"] = "backend"
                    payload["whatsapp_already_sent"] = True
                    payload["provider_message_id"] = wa_delivery.get("provider_message_id")
                elif wa_delivery.get("deferred_to_n8n"):
                    payload["whatsapp_delivery"] = "n8n"
                    if wa_delivery.get("template_name"):
                        payload["template_name"] = wa_delivery["template_name"]
                        payload["template_language"] = wa_delivery.get("language_code")
                        payload["language_code"] = wa_delivery.get("language_code")
                        fc = dict(payload.get("first_contact") or {})
                        fc["template_name"] = wa_delivery["template_name"]
                        fc["language_code"] = wa_delivery.get("language_code")
                        payload["first_contact"] = fc
                else:
                    payload["whatsapp_delivery"] = "failed"
                    payload["whatsapp_error"] = wa_delivery.get("error")

            # Campaign webhook is already resolved. Local channel ineligibility must
            # remain visible on the payload, but must not silently drop dispatch —
            # n8n may still own email/Sheets/WhatsApp bridge delivery.
            if not any_channel_eligible(eligibility):
                logger.info(
                    "webhook dispatch with no local eligible channel "
                    "(client={} campaign={} lead={}); n8n receives stamped eligibility",
                    client_id,
                    camp_id,
                    lead.get("id"),
                )

            # If backend already sent WhatsApp and email is not eligible, skip n8n.
            em_elig = (eligibility.get("channels") or {}).get("email") or {}
            skip_n8n = bool(payload.get("whatsapp_already_sent")) and not em_elig.get("eligible")
            if skip_n8n:
                if pool:
                    await record_auto_n8n_send(
                        pool,
                        client_id=client_id,
                        lead=lead,
                        campaign=campaign,
                        session_call_id=session_call_id,
                        ok=True,
                        error=None,
                        eligibility=eligibility,
                        payload=payload,
                    )
                return

            service = N8nService(n8n_config_for(dest), pool=pool)
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
                    eligibility=eligibility,
                    payload=payload,
                    error_category=result.error_category,
                    retryable=result.retryable,
                )
        except Exception:
            logger.exception("campaign webhook lead_qualified dispatch failed; settlement continues")
        return

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
        "client_id": str(client_id),
    }
    await _post_signed(dest.webhook_url, payload, dest.webhook_secret)


async def fire_campaign_completed_webhook(
    pool,
    client_id: UUID,
    campaign: dict,
) -> None:
    from integrations.n8n.routing import resolve_campaign_webhook

    event = "campaign_completed"
    camp_id = _campaign_id(campaign)
    if camp_id is None:
        logger.info("webhook NO SEND: campaign_completed missing campaign_id")
        return

    dest = await resolve_campaign_webhook(
        pool,
        client_id=client_id,
        campaign_id=camp_id,
        event=event,
        campaign=campaign,
    )
    if not dest.ok:
        logger.info(
            "webhook NO SEND: {} (campaign={} event=campaign_completed)",
            dest.error,
            camp_id,
        )
        return

    payload = {
        "event": event,
        "client_id": str(client_id),
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
        dest.webhook_url,
        payload,
        dest.webhook_secret,
    )

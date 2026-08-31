"""Trigger and record lead follow-ups. Backend builds the payload; n8n sends."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from loguru import logger

from db import postgres as pg_db
from followups import repository as repo
from followups.context import LeadContext
from followups.enrichment import enrich_lead_payload
from integrations.n8n.config import N8nConfig
from integrations.n8n.payload import build_lead_qualified_payload
from integrations.n8n.service import N8nService
from lead_upload.normaliser import normalise_phone


PREVIEW_CHARS = 160


def _meta(lead: dict) -> dict:
    raw = lead.get("metadata") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _preview(payload: dict, source: str) -> str:
    """Store the deterministic copy we would send, not a generic label."""
    fallback = (payload.get("fallback") or {}).get("whatsapp") or {}
    message = str(fallback.get("message") or "").strip()
    if not message:
        return f"follow-up via n8n ({source})"
    return message[:PREVIEW_CHARS]


async def trigger_follow_up(
    pool,
    *,
    client_id: UUID,
    lead_id: UUID,
    source: str = "manual",
    session_call_id: str | None = None,
    require_interested: bool = False,
) -> dict:
    lead = await pg_db.get_lead(pool, lead_id, client_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found"}

    campaign_id = lead.get("campaign_id")
    campaign = None
    if campaign_id:
        campaign = await pg_db.get_campaign(pool, UUID(str(campaign_id)), client_id)
    if not campaign:
        return {"ok": False, "error": "campaign_not_found"}

    if require_interested:
        from followups.interested import is_interested_outcome

        if not is_interested_outcome(lead.get("outcome")):
            return {"ok": False, "error": "lead_not_interested", "skipped": True}

    phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
    if not phone:
        return {"ok": False, "error": "missing_phone"}

    if source == "manual":
        recent = await repo.recent_for_lead(pool, client_id, lead_id, within_seconds=90)
        if recent and recent.get("status") in ("queued", "sent", "accepted"):
            return {
                "ok": True,
                "deduplicated": True,
                "whatsapp": "already_sent",
                "email": "already_sent",
                "event": recent,
            }

    import time

    if source == "manual" and not session_call_id:
        sid = f"manual_{lead_id}_{int(time.time() // 30)}"
    else:
        sid = session_call_id or f"manual_{lead_id}"
    idem = f"{source}:{sid}:{lead_id}"
    existing = await repo.get_by_idempotency(pool, client_id, idem)
    if existing:
        return {"ok": True, "deduplicated": True, "event": existing}

    client_row = await pg_db.get_client(pool, client_id)
    extraction = {}
    if lead.get("extraction_json"):
        extraction = lead["extraction_json"] if isinstance(lead["extraction_json"], dict) else {}
    elif isinstance(lead.get("extraction"), dict):
        extraction = lead["extraction"]
    meta = _meta(lead)

    payload = build_lead_qualified_payload(
        client_id=client_id,
        lead=lead,
        session_call_id=sid,
        duration_seconds=int(lead.get("last_call_duration_seconds") or 0),
        extraction=extraction or {
            "intent_status": lead.get("outcome") or "Interested",
            "summary": meta.get("summary") or "",
        },
        campaign=campaign,
        outcome=lead.get("outcome") or "Interested",
        client=client_row,
    )
    payload["flow_type"] = "INITIAL_FOLLOWUP"
    payload["interested"] = True
    payload["source"] = source
    payload = await enrich_lead_payload(pool, payload, client_id=client_id)

    first_contact = payload.get("first_contact") or {}
    email = payload.get("lead", {}).get("email")
    channels = {"whatsapp": "queued" if phone else "skipped", "email": "queued" if email else "unavailable"}
    if phone and first_contact.get("can_send") is False:
        channels["whatsapp"] = "blocked"

    n8n_cfg = await N8nConfig.resolve(pool)
    service = N8nService(n8n_cfg, pool=pool)
    if not service.is_configured():
        event = await repo.insert_event(
            pool,
            client_id=client_id,
            campaign_id=UUID(str(campaign_id)) if campaign_id else None,
            lead_id=lead_id,
            channel="n8n",
            direction="outgoing",
            status="failed",
            source=source,
            message_preview=None,
            idempotency_key=idem,
            session_call_id=sid,
            error="n8n_not_configured",
        )
        return {"ok": False, "error": "n8n_not_configured", "event": event, **channels}

    result = await service.send_lead_qualified(payload)
    status = "queued" if result.ok else "failed"
    event = await repo.insert_event(
        pool,
        client_id=client_id,
        campaign_id=UUID(str(campaign_id)) if campaign_id else None,
        lead_id=lead_id,
        channel="n8n",
        direction="outgoing",
        status=status,
        source=source,
        message_preview=_preview(payload, source),
        idempotency_key=idem,
        session_call_id=sid,
        error=None if result.ok else (result.error or "n8n_request_failed"),
    )
    if not result.ok:
        logger.warning("follow-up n8n failed lead={} err={}", lead_id, result.error)
        return {
            "ok": False,
            "error": result.error or "n8n_request_failed",
            "event": event,
            "whatsapp": "failed",
            "email": "failed" if email else "unavailable",
            "first_contact": first_contact,
        }

    await _record_client_inbox(
        pool,
        client_id=client_id,
        lead=lead,
        campaign=campaign,
        payload=payload,
        idempotency_key=f"{idem}:inbox",
    )

    logger.info("follow-up queued lead={} source={} event_id={}", lead_id, source, payload.get("event_id"))
    return {
        "ok": True,
        "deduplicated": False,
        "whatsapp": channels["whatsapp"],
        "email": channels["email"],
        "event": event,
        "event_id": payload.get("event_id"),
        "first_contact": first_contact,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


async def record_auto_n8n_send(
    pool,
    *,
    client_id: UUID,
    lead: dict,
    campaign: dict,
    session_call_id: str,
    ok: bool,
    error: str | None = None,
) -> None:
    lead_id = lead.get("id")
    if not lead_id:
        return
    idem = f"auto:{session_call_id}:{lead_id}"
    await repo.insert_event(
        pool,
        client_id=client_id,
        campaign_id=UUID(str(campaign["id"])) if campaign and campaign.get("id") else None,
        lead_id=UUID(str(lead_id)),
        channel="n8n",
        direction="outgoing",
        status="queued" if ok else "failed",
        source="auto",
        message_preview="auto follow-up after interested call",
        idempotency_key=idem,
        session_call_id=session_call_id,
        error=error,
    )
    if ok:
        await _record_client_inbox(
            pool,
            client_id=client_id,
            lead=lead,
            campaign=campaign,
            payload=None,
            idempotency_key=f"{idem}:inbox",
        )


async def _record_client_inbox(
    pool,
    *,
    client_id: UUID,
    lead: dict,
    campaign: dict | None,
    payload: dict | None,
    idempotency_key: str,
) -> None:
    """Write the follow-up into the client Messages inbox."""
    try:
        from messages.service import record_n8n_message

        phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
        if not phone:
            return
        fallback = ((payload or {}).get("fallback") or {}).get("whatsapp") or {}
        text = str(fallback.get("message") or "").strip() or "WhatsApp follow-up template sent"
        first = (payload or {}).get("first_contact") or {}
        campaign_id = None
        if campaign and campaign.get("id"):
            campaign_id = UUID(str(campaign["id"]))
        elif lead.get("campaign_id"):
            campaign_id = UUID(str(lead["campaign_id"]))
        lead_id = UUID(str(lead["id"])) if lead.get("id") else None
        await record_n8n_message(
            pool,
            client_id=client_id,
            to_phone=phone,
            text=text,
            template_name=first.get("template_name") or "hello_world",
            lead_id=lead_id,
            campaign_id=campaign_id,
            customer_name=lead.get("name"),
            idempotency_key=idempotency_key,
            direction="outgoing",
            status="sent",
        )
    except Exception as exc:
        logger.warning("client inbox record failed client={} err={}", client_id, exc)


async def list_history(pool, client_id: UUID, lead_id: UUID) -> list[dict]:
    return await repo.list_for_lead(pool, client_id, lead_id)

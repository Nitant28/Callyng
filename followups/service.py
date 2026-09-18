"""Trigger and record lead follow-ups.

Backend owns delivery decision. n8n HTTP 200 alone is never WhatsApp \"sent\".
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import UUID

from loguru import logger

from db import postgres as pg_db
from followups import repository as repo
from followups.delivery import deliver_whatsapp_follow_up
from followups.enrichment import enrich_lead_payload
from followups.eligibility import evaluate_channel_eligibility
from integrations.n8n.payload import build_lead_qualified_payload
from integrations.n8n.service import N8nService
from lead_upload.normaliser import normalise_phone

PREVIEW_CHARS = 160

_NO_APPROVED_INITIAL_TEMPLATE = (
    "No approved initial WhatsApp follow-up template is configured."
)

FOLLOWUP_USER_MESSAGES: dict[str, str] = {
    "template_not_configured": _NO_APPROVED_INITIAL_TEMPLATE,
    "first_contact_template_not_configured": _NO_APPROVED_INITIAL_TEMPLATE,
    "first_contact_template_not_approved": _NO_APPROVED_INITIAL_TEMPLATE,
    "first_contact_template_disabled": (
        "WhatsApp first-contact template is disabled. Enable it in Admin → WhatsApp."
    ),
    "whatsapp_opt_in_required": (
        "WhatsApp opt-in is required before the first message can be sent."
    ),
    "missing_recipient": "This lead has no valid phone number for WhatsApp.",
    "missing_phone": "This lead has no valid phone number.",
    "n8n_not_configured": "Follow-up webhook is not configured for this campaign.",
    "lead_not_found": "Lead not found.",
    "campaign_not_found": "Campaign not found for this lead.",
    "lead_not_interested": "Automatic follow-up is only sent for interested leads.",
    "provider_message_id_missing": (
        "WhatsApp provider did not return a message ID. Treat as failed."
    ),
    "meta_credentials_not_configured": (
        "Meta Cloud credentials are not configured on this client's WhatsApp integration."
    ),
}


def user_message_for(reason: str | None, *, email_queued: bool = False) -> str:
    code = (reason or "").strip()
    base = FOLLOWUP_USER_MESSAGES.get(code) or (
        code.replace("_", " ").strip() if code else "Follow-up failed"
    )
    if email_queued and (
        code.startswith("first_contact_")
        or code in ("template_not_configured", "whatsapp_opt_in_required", "missing_or_invalid_phone")
    ):
        return f"{base} Email follow-up was still queued."
    return base


def _meta(lead: dict) -> dict:
    raw = lead.get("metadata") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _preview(payload: dict, source: str) -> str:
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
        return {"ok": False, "error": "lead_not_found", "message": user_message_for("lead_not_found")}

    campaign_id = lead.get("campaign_id")
    campaign = None
    if campaign_id:
        campaign = await pg_db.get_campaign(pool, UUID(str(campaign_id)), client_id)
    if not campaign:
        return {
            "ok": False,
            "error": "campaign_not_found",
            "message": user_message_for("campaign_not_found"),
        }

    if require_interested:
        from followups.interested import is_interested_outcome

        if not is_interested_outcome(lead.get("outcome")):
            return {
                "ok": False,
                "error": "lead_not_interested",
                "skipped": True,
                "message": user_message_for("lead_not_interested"),
            }

    phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
    if not phone:
        return {"ok": False, "error": "missing_phone", "message": user_message_for("missing_phone")}

    if source == "manual":
        recent = await repo.recent_for_lead(pool, client_id, lead_id, within_seconds=90)
        if recent and recent.get("status") in ("queued", "sent", "accepted", "provider_accepted"):
            return {
                "ok": True,
                "deduplicated": True,
                "whatsapp": "already_sent",
                "email": "already_sent",
                "event": recent,
            }

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
        extraction=extraction
        or {
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
    # Manual UI send must always attempt WhatsApp (Mega If gates + eligibility).
    if str(source or "").strip().casefold() == "manual":
        payload["force_whatsapp"] = True
        payload["interested"] = True
    payload = await enrich_lead_payload(pool, payload, client_id=client_id)

    first_contact = payload.get("first_contact") or {}
    email = payload.get("lead", {}).get("email")

    eligibility = evaluate_channel_eligibility(
        client_id=client_id,
        campaign_id=campaign_id,
        lead_id=lead_id,
        outcome=lead.get("outcome"),
        follow_up_target=(campaign or {}).get("follow_up_target"),
        lead=lead,
        first_contact=first_contact,
        whatsapp_integration=payload.get("whatsapp"),
        require_qualified=require_interested,
        source=source,
    )
    payload["channel_eligibility"] = eligibility
    wa_elig = (eligibility.get("channels") or {}).get("whatsapp") or {}
    em_elig = (eligibility.get("channels") or {}).get("email") or {}

    channels = {
        "whatsapp": "skipped",
        "email": "queued" if em_elig.get("eligible") else "unavailable",
    }

    wa_delivery = None
    if wa_elig.get("eligible"):
        wa_delivery = await deliver_whatsapp_follow_up(
            pool,
            client_id=client_id,
            lead=lead,
            campaign=campaign,
            first_contact=first_contact,
            idempotency_key=f"{idem}:wa",
            message_text=((payload.get("fallback") or {}).get("whatsapp") or {}).get("message"),
        )
        if wa_delivery.get("mode") == "backend" and wa_delivery.get("ok") and wa_delivery.get(
            "provider_message_id"
        ):
            channels["whatsapp"] = "sent"
            payload["whatsapp_delivery"] = "backend"
            payload["whatsapp_already_sent"] = True
            payload["provider_message_id"] = wa_delivery.get("provider_message_id")
        elif wa_delivery.get("deferred_to_n8n"):
            channels["whatsapp"] = "queued"
            payload["whatsapp_delivery"] = "n8n"
            if wa_delivery.get("template_name"):
                payload["template_name"] = wa_delivery["template_name"]
                payload["template_language"] = wa_delivery.get("language_code")
                payload["language_code"] = wa_delivery.get("language_code")
        else:
            channels["whatsapp"] = "failed"
            payload["whatsapp_delivery"] = "failed"
            payload["whatsapp_error"] = wa_delivery.get("error")
    else:
        channels["whatsapp"] = "blocked"
        payload["whatsapp_error"] = wa_elig.get("reason") or "whatsapp_not_eligible"

    # If WhatsApp already sent by backend and no email, skip n8n.
    skip_n8n = bool(payload.get("whatsapp_already_sent")) and not em_elig.get("eligible")

    n8n_result = None
    if not skip_n8n and (channels["whatsapp"] == "queued" or em_elig.get("eligible")):
        from integrations.n8n.routing import n8n_config_for, resolve_campaign_webhook

        dest = await resolve_campaign_webhook(
            pool,
            client_id=client_id,
            campaign_id=UUID(str(campaign_id)),
            event="lead_qualified",
            campaign=campaign,
        )
        payload["workflow"] = dest.as_payload()
        if not dest.ok:
            if channels["whatsapp"] == "queued":
                channels["whatsapp"] = "failed"
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
                    error=dest.error or "n8n_not_configured",
                )
                return {
                    "ok": False,
                    "error": "n8n_not_configured",
                    "message": user_message_for("n8n_not_configured"),
                    "event": event,
                    "whatsapp": channels["whatsapp"],
                    "email": channels["email"],
                    "first_contact": first_contact,
                }
        else:
            service = N8nService(n8n_config_for(dest), pool=pool)
            n8n_result = await service.send_lead_qualified(payload)
            if not n8n_result.ok and channels["whatsapp"] == "queued":
                channels["whatsapp"] = "failed"
            if n8n_result.ok and em_elig.get("eligible"):
                channels["email"] = "queued"

    status = "failed"
    if channels["whatsapp"] == "sent":
        status = "sent"
    elif channels["whatsapp"] == "queued" or channels["email"] == "queued":
        status = "queued"
    elif channels["whatsapp"] == "blocked" and channels["email"] == "queued":
        status = "queued"

    err = None
    if status == "failed":
        err = (
            (wa_delivery or {}).get("error")
            or payload.get("whatsapp_error")
            or (n8n_result.error if n8n_result and not n8n_result.ok else None)
            or "follow_up_failed"
        )

    event = await repo.insert_event(
        pool,
        client_id=client_id,
        campaign_id=UUID(str(campaign_id)) if campaign_id else None,
        lead_id=lead_id,
        channel="whatsapp" if channels["whatsapp"] in ("sent", "queued", "failed", "blocked") else "n8n",
        direction="outgoing",
        status=status,
        source=source,
        message_preview=_preview(payload, source),
        idempotency_key=idem,
        session_call_id=sid,
        error=err,
    )

    # Inbox: only mark sent when we have a real provider id; else queued.
    inbox_status = "sent" if channels["whatsapp"] == "sent" else (
        "queued" if channels["whatsapp"] == "queued" else "failed"
    )
    if channels["whatsapp"] in ("sent", "queued"):
        await _record_client_inbox(
            pool,
            client_id=client_id,
            lead=lead,
            campaign=campaign,
            payload=payload,
            idempotency_key=f"{idem}:inbox",
            status=inbox_status,
            provider_message_id=payload.get("provider_message_id"),
        )

    ok = status in ("sent", "queued") or channels["email"] == "queued"
    msg = None
    if channels["whatsapp"] == "blocked":
        msg = user_message_for(
            str(payload.get("whatsapp_error") or "template_not_configured"),
            email_queued=channels["email"] == "queued",
        )
    elif channels["whatsapp"] == "failed":
        msg = user_message_for(str(err or "follow_up_failed"), email_queued=channels["email"] == "queued")

    logger.info(
        "follow-up result lead={} source={} wa={} email={} status={}",
        lead_id,
        source,
        channels["whatsapp"],
        channels["email"],
        status,
    )
    return {
        "ok": ok,
        "deduplicated": False,
        "whatsapp": channels["whatsapp"],
        "email": channels["email"],
        "event": event,
        "event_id": payload.get("event_id"),
        "first_contact": first_contact,
        "provider_message_id": payload.get("provider_message_id"),
        "message": msg,
        "warning": msg if channels["whatsapp"] in ("blocked", "failed") else None,
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
    eligibility: dict | None = None,
    payload: dict | None = None,
    error_category: str | None = None,
    retryable: bool | None = None,
) -> None:
    """Persist auto post-call n8n dispatch outcome (idempotent on auto:call:lead)."""
    _ = (eligibility, payload, error_category, retryable)
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


async def _record_client_inbox(
    pool,
    *,
    client_id: UUID,
    lead: dict,
    campaign: dict | None,
    payload: dict | None,
    idempotency_key: str,
    status: str = "queued",
    provider_message_id: str | None = None,
) -> None:
    try:
        from messages.service import record_n8n_message

        phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
        if not phone:
            return
        fallback = ((payload or {}).get("fallback") or {}).get("whatsapp") or {}
        text = str(fallback.get("message") or "").strip() or "WhatsApp follow-up"
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
            template_name=first.get("template_name") or None,
            lead_id=lead_id,
            campaign_id=campaign_id,
            customer_name=lead.get("name"),
            idempotency_key=idempotency_key,
            direction="outgoing",
            status=status,
            provider_message_id=provider_message_id,
        )
    except Exception as exc:
        logger.warning("client inbox record failed client={} err={}", client_id, exc)


async def list_history(pool, client_id: UUID, lead_id: UUID) -> list[dict]:
    return await repo.list_for_lead(pool, client_id, lead_id)

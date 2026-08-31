"""Internal lead context APIs for n8n (backend = source of truth)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_pool, require_admin_or_n8n_token
from db import postgres as pg_db
from followups.enrichment import enrich_lead_payload
from integrations.n8n.payload import build_lead_qualified_payload
from lead_upload.normaliser import normalise_phone

router = APIRouter(prefix="/internal/leads", tags=["internal-leads"])


def _meta(lead: dict) -> dict:
    raw = lead.get("metadata") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


@router.get("/context")
async def lead_context_by_phone(
    phone: str = Query(..., min_length=8),
    client_id: UUID | None = None,
    flow_type: str = Query(default="CONTINUE_CHAT"),
    inbound_message: str | None = None,
    provider_message_id: str | None = None,
    phone_number_id: str | None = None,
    _admin=Depends(require_admin_or_n8n_token),
    pool=Depends(get_pool),
):
    """Return canonical lead context for n8n inbound WhatsApp / lookup nodes."""
    normalized = normalise_phone(phone)
    if not normalized:
        raise HTTPException(400, "invalid_phone")

    if client_id is None and phone_number_id:
        from messages import repository as msg_repo

        integ = await msg_repo.get_integration_by_phone_number_id(pool, phone_number_id)
        if integ and integ.get("client_id"):
            client_id = UUID(str(integ["client_id"]))

    lead = await pg_db.find_lead_by_phone(pool, phone, client_id=client_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found", "phone": normalized}

    cid = UUID(str(lead["client_id"]))
    client_row = await pg_db.get_client(pool, cid)
    campaign = None
    if lead.get("campaign_id"):
        campaign = await pg_db.get_campaign(pool, UUID(str(lead["campaign_id"])), cid)
    if not campaign:
        campaign = {"id": lead.get("campaign_id"), "name": None}

    meta = _meta(lead)
    extraction = lead.get("extraction") if isinstance(lead.get("extraction"), dict) else {}
    if not extraction and isinstance(lead.get("extraction_json"), dict):
        extraction = lead["extraction_json"]
    if not extraction:
        extraction = {
            "intent_status": lead.get("outcome") or "Interested",
            "summary": meta.get("summary") or "",
            "bhk_preference": meta.get("bhk_preference"),
            "location_preference": meta.get("location_preference") or meta.get("lead_city"),
            "budget": meta.get("budget"),
        }

    session_call_id = lead.get("last_session_call_id") or f"inbound_{lead['id']}"

    conversation: list[dict] = []
    try:
        from messages import repository as msg_repo
        from messages import service as messages_service

        conv = await msg_repo.get_conversation_by_phone(pool, cid, normalized)
        if conv:
            rows = await msg_repo.list_messages(pool, cid, conv["id"], limit=20)
            conversation = [
                {
                    "direction": r.get("direction"),
                    "text": r.get("text_body"),
                    "created_at": str(r.get("created_at") or ""),
                }
                for r in rows
            ]
        if inbound_message:
            await messages_service.record_n8n_message(
                pool,
                client_id=cid,
                to_phone=normalized,
                text=inbound_message,
                lead_id=UUID(str(lead["id"])) if lead.get("id") else None,
                campaign_id=UUID(str(lead["campaign_id"])) if lead.get("campaign_id") else None,
                customer_name=lead.get("name"),
                idempotency_key=provider_message_id or f"inbound:{normalized}:{inbound_message[:80]}",
                direction="inbound",
                status="received",
                provider_message_id=provider_message_id,
            )
            conversation = conversation + [
                {"direction": "inbound", "text": inbound_message, "created_at": ""}
            ]
    except Exception:
        conversation = conversation or []

    payload = build_lead_qualified_payload(
        client_id=cid,
        lead=lead,
        session_call_id=str(session_call_id),
        duration_seconds=int(lead.get("last_call_duration_seconds") or 0),
        extraction=extraction,
        campaign=campaign,
        outcome=lead.get("outcome") or "Interested",
        client=client_row,
        conversation=conversation,
        inbound_text=inbound_message,
    )
    payload["flow_type"] = flow_type
    payload["event_type"] = "WHATSAPP_INBOUND" if flow_type == "CONTINUE_CHAT" else "INTERESTED_LEAD"
    payload["interested"] = True
    if inbound_message:
        payload["message"] = {"text": inbound_message, "direction": "inbound"}

    payload = await enrich_lead_payload(
        pool,
        payload,
        client_id=cid,
        inbound_text=inbound_message,
    )
    payload["prompt_context"] = {
        "instructions": (
            "Reply to the latest inbound WhatsApp using only the facts below. "
            "Do not invent prices, inventory, or promises. Keep the reply under 120 words. "
            "Do not mention n8n, Gemini, or internal systems."
        ),
        "latest_inbound": inbound_message,
        "lead": payload.get("lead"),
        "client": payload.get("client"),
        "campaign": payload.get("campaign"),
        "extraction": payload.get("extraction"),
        "conversation": conversation,
    }

    return {"ok": True, "lead": lead, "payload": payload, "phone": normalized}

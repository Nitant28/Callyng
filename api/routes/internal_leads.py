"""Internal lead context APIs for n8n (backend = source of truth)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_pool, require_admin_or_n8n_token
from db import postgres as pg_db
from followups.enrichment import enrich_lead_payload
from integrations.n8n.payload import build_lead_qualified_payload
from messages.inbound import resolve_inbound_tenant

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
    integration_id: UUID | None = None,
    _admin=Depends(require_admin_or_n8n_token),
    pool=Depends(get_pool),
):
    """Return canonical lead context for n8n inbound WhatsApp / lookup nodes.

    Tenant identity requires phone_number_id and/or client_id (or integration_id).
    Phone alone is never enough.
    """
    resolved = await resolve_inbound_tenant(
        pool,
        phone=phone,
        phone_number_id=phone_number_id,
        client_id=client_id,
        integration_id=integration_id,
    )
    if not resolved.ok:
        status = 400 if resolved.error in {
            "invalid_phone",
            "phone_number_id_or_client_id_required",
            "client_integration_mismatch",
            "conversation_campaign_mismatch",
            "lead_client_mismatch",
            "memory_context_incomplete",
        } else 200
        body = {
            "ok": False,
            "error": resolved.error,
            "phone": resolved.phone_e164,
            "client_id": str(resolved.client_id) if resolved.client_id else None,
            "integration_id": str(resolved.integration_id) if resolved.integration_id else None,
            "ai_allowed": False,
        }
        if status == 400:
            raise HTTPException(status, resolved.error or "inbound_resolution_failed")
        return body

    cid = resolved.client_id
    assert cid is not None
    lead = resolved.lead or {}
    campaign = resolved.campaign or {"id": lead.get("campaign_id"), "name": None}
    client_row = await pg_db.get_client(pool, cid)

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
    normalized = resolved.phone_e164 or phone

    conversation: list[dict] = []
    try:
        from messages import repository as msg_repo
        from messages import service as messages_service

        conv = resolved.conversation
        if conv:
            rows = await msg_repo.list_messages(pool, cid, UUID(str(conv["id"])), limit=20)
            conversation = [
                {
                    "direction": r.get("direction"),
                    "text": r.get("text_body"),
                    "created_at": str(r.get("created_at") or ""),
                }
                for r in rows
            ]
        if inbound_message:
            from uuid import uuid4

            from followups.idempotency import inbound_message_key

            ikey = inbound_message_key(
                client_id=cid,
                provider_message_id=provider_message_id,
            ) or f"inbound:{cid}:once:{uuid4()}"
            await messages_service.record_n8n_message(
                pool,
                client_id=cid,
                to_phone=normalized,
                text=inbound_message,
                lead_id=UUID(str(lead["id"])) if lead.get("id") else None,
                campaign_id=UUID(str(lead["campaign_id"])) if lead.get("campaign_id") else None,
                customer_name=lead.get("name"),
                idempotency_key=ikey,
                direction="incoming",
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
    payload["memory_key"] = resolved.memory_key
    if inbound_message:
        payload["message"] = {"text": inbound_message, "direction": "inbound"}

    payload = await enrich_lead_payload(
        pool,
        payload,
        client_id=cid,
        inbound_text=inbound_message,
    )
    # Never allow Gemini with phone-only memory; memory_key is mandatory.
    if not payload.get("memory_key"):
        return {
            "ok": False,
            "error": "memory_context_incomplete",
            "phone": normalized,
            "ai_allowed": False,
        }

    payload["prompt_context"] = {
        "instructions": (
            "Reply to the latest inbound WhatsApp using only the facts below. "
            "Do not invent prices, inventory, or promises. Keep the reply under 120 words. "
            "Do not mention n8n, Gemini, or internal systems."
        ),
        "memory_key": payload["memory_key"],
        "latest_inbound": inbound_message,
        "lead": payload.get("lead"),
        "client": payload.get("client"),
        "campaign": payload.get("campaign"),
        "extraction": payload.get("extraction"),
        "conversation": conversation,
    }

    return {
        "ok": True,
        "lead": lead,
        "payload": payload,
        "phone": normalized,
        "client_id": str(cid),
        "integration_id": str(resolved.integration_id) if resolved.integration_id else None,
        "memory_key": payload["memory_key"],
        "ai_allowed": True,
    }

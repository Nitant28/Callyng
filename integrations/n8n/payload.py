"""Mega_Workflow-compatible lead_qualified payload builder.

Contract: matches the existing Mega_Workflow Lead Context node expectations.
The payload is a superset of the legacy Aakashvani webhook format so existing
n8n expressions like $json.lead.phone, $json.extraction.summary, and
$json.campaign.name continue to work unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from integrations.n8n.fallbacks import fallback_inbound_whatsapp, fallback_initial_email, fallback_initial_whatsapp
from lead_upload.normaliser import normalise_phone


def _record_token() -> str | None:
    secret = (
        (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
        or (os.getenv("ADMIN_API_KEY") or "").strip()
    )
    if not secret:
        return None
    import hashlib

    return hashlib.sha256(f"record::{secret}".encode("utf-8")).hexdigest()


def public_backend_base_url() -> str | None:
    """Permanent public API host. Production must set AAKASHVANI_PUBLIC_URL.

    NGROK_URL is local-dev fallback only (never used when ENV=production).
    """
    public = (os.getenv("AAKASHVANI_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return public
    env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
    if env in ("production", "prod"):
        return None
    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    return ngrok or None


def _signed_internal_url(path: str, extra: dict[str, str] | None = None) -> str | None:
    base = public_backend_base_url()
    if not base:
        return None
    url = f"{base}{path}"
    params = dict(extra or {})
    token = _record_token()
    if token:
        params["token"] = token
    if params:
        return f"{url}?{urlencode(params)}"
    return url


def _record_url() -> str | None:
    return _signed_internal_url("/internal/messages/record")


def _context_url() -> str | None:
    return _signed_internal_url("/internal/leads/context")


def _send_url() -> str | None:
    return _signed_internal_url("/internal/messages/send")

# Documented source of every outbound field (for dry-run inspection).
PAYLOAD_FIELD_SOURCES: dict[str, str] = {
    "event": "constant: lead_qualified",
    "event_type": "INTERESTED_LEAD when interested else LEAD_QUALIFIED",
    "flow_type": "constant: INITIAL_FOLLOWUP (manual/auto) or CONTINUE_CHAT (inbound)",
    "interested": "computed from outcome / qualification.status",
    "event_id": "computed: {session_call_id}:{lead.id}",
    "client_id": "clients.id / campaign.client_id",
    "client.id": "clients.id (Mega_Workflow Lead Context)",
    "client.name": "clients.name",
    "client.industry": "clients.industry",
    "lead.id": "leads.id",
    "lead.name": "leads.name",
    "lead.phone": "leads.phone (normalised E.164, India default)",
    "lead.email": "leads.metadata.email or leads.email",
    "lead.lead_type": "leads.lead_type",
    "lead.metadata": "leads.metadata JSON",
    "lead.whatsapp_opt_in": "leads.metadata.whatsapp_opt_in (default true if absent; explicit false/opt-out = false)",
    "call.id": "call_logs.session_call_id",
    "call.session_call_id": "call_logs.session_call_id",
    "call.status": "constant: completed",
    "call.duration": "call_logs.duration_seconds",
    "call.duration_seconds": "call_logs.duration_seconds",
    "call.billed_minutes": "post_call billing calculation",
    "call.credits_charged": "post_call billing calculation",
    "call.route": "bot_configs.route",
    "call.recording_url": "call_logs.recording_url",
    "extraction": "post_call extraction JSON (intent_status, summary, …)",
    "qualification.status": "extraction.intent_status or post_call outcome",
    "qualification.score": "extraction.score | qualification_score | lead_score",
    "qualification.reason": "extraction.summary | reason | notes | outcome",
    "campaign_id": "campaigns.id (top-level for n8n send API)",
    "lead_id": "leads.id (top-level for n8n send API)",
    "campaign.id": "campaigns.id",
    "campaign.name": "campaigns.name",
    "whatsapp.integration_id": "whatsapp_integrations.id for this client (enrichment)",
    "whatsapp.phone_number_id": "whatsapp_integrations.phone_number_id for this client",
    "whatsapp.provider": "whatsapp_integrations.provider for this client",
    "memory_key": "client_id:campaign_id:lead_id (never phone)",
    "workflow.id": "resolved n8n_workflows.id",
    "workflow.name": "resolved n8n_workflows.name",
    "workflow.source": "campaign | client_default | platform_default | legacy",
    "agent.id": "bot_configs.id",
    "follow_up.channel": "constant: whatsapp",
    "follow_up.action": "constant: send",
    "follow_up.stage": "constant: 1 (first follow-up)",
    "follow_up.idempotency_key": "computed: n8n_{event_id}_wa_{stage}",
    "metadata.campaign_id": "campaigns.id",
    "metadata.campaign_name": "campaigns.name",
    "metadata.agent_id": "bot_configs.id",
}


def _lead_metadata(lead: dict[str, Any]) -> dict[str, Any]:
    meta = lead.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    return dict(meta) if isinstance(meta, dict) else {}


def _normalise_lead_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    normalised = normalise_phone(str(raw))
    return normalised or str(raw).strip() or None


def _qualification_score(extraction: dict[str, Any]) -> int | float:
    for key in ("score", "qualification_score", "lead_score"):
        val = extraction.get(key)
        if val is not None:
            try:
                return int(val) if float(val).is_integer() else float(val)
            except (TypeError, ValueError):
                continue
    return 0


def _qualification_reason(extraction: dict[str, Any], outcome: str | None) -> str | None:
    for key in ("reason", "summary", "qualification_reason", "notes"):
        val = extraction.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    if outcome:
        return outcome
    intent = extraction.get("intent_status")
    return str(intent).strip() if intent else None


def _qualification_status(extraction: dict[str, Any], outcome: str | None) -> str:
    from followups.interested import canonicalize_intent

    raw = outcome or extraction.get("intent_status") or ""
    return canonicalize_intent(raw) or "unknown"


def _memory_key(client_id: UUID, campaign_id: Any, lead_id: Any) -> str | None:
    """Tenant-safe Gemini/session key. Never phone. Null if any piece is missing."""
    if not client_id or not campaign_id or not lead_id:
        return None
    return f"{client_id}:{campaign_id}:{lead_id}"


def _whatsapp_opt_in(meta: dict[str, Any]) -> bool:
    """Payload opt-in flag: default True unless explicitly opted out / set false.

    Actual send gating still uses fail-closed ``parse_whatsapp_opt_in`` in
    eligibility / delivery — this field is the Mega payload contract only.
    """
    if "whatsapp_opt_in" in meta:
        val = meta.get("whatsapp_opt_in")
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().casefold() in ("1", "true", "yes", "y")
        return bool(val)
    if meta.get("whatsapp_opt_out") is True:
        return False
    if str(meta.get("whatsapp_opt_out") or "").strip().casefold() in ("1", "true", "yes", "y"):
        return False
    return True


def build_lead_qualified_payload(
    *,
    client_id: UUID,
    lead: dict[str, Any],
    session_call_id: str,
    duration_seconds: int,
    extraction: dict[str, Any],
    campaign: dict[str, Any],
    outcome: str | None = None,
    bot_config_id: UUID | None = None,
    billed_minutes: int = 0,
    credits_charged: float = 0,
    route: str | None = None,
    recording_url: str | None = None,
    follow_up_stage: int = 1,
    client: dict[str, Any] | None = None,
    conversation: list[dict[str, Any]] | None = None,
    inbound_text: str | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Mega_Workflow Lead Context payload. No invented business data."""
    meta = _lead_metadata(lead)
    lead_id = lead.get("id")
    email = lead.get("email") or meta.get("email")
    if email and "email" not in meta:
        meta = {**meta, "email": email}

    phone = _normalise_lead_phone(lead.get("phone"))
    extraction_out = dict(extraction or {})
    for src_key, dest_key in (
        ("bhk_preference", "bhk_preference"),
        ("location_preference", "location_preference"),
        ("budget", "budget"),
        ("lead_city", "lead_city"),
        ("city", "lead_city"),
    ):
        if not extraction_out.get(dest_key) and meta.get(src_key):
            extraction_out[dest_key] = meta.get(src_key)
    # Mega_Workflow Lead Context historically reads both snake aliases.
    _alias_pairs = (
        ("intent_status", "intent_status"),
        ("bhk_preference", "bhk_preference"),
        ("location_preference", "location_preference"),
    )
    for left, right in _alias_pairs:
        if extraction_out.get(left) and not extraction_out.get(right):
            extraction_out[right] = extraction_out[left]
        elif extraction_out.get(right) and not extraction_out.get(left):
            extraction_out[left] = extraction_out[right]
    qual_status = _qualification_status(extraction_out, outcome)
    from followups.interested import evaluate_qualification

    qual_decision = extraction_out.get("qualification")
    if not isinstance(qual_decision, dict) or "eligible" not in qual_decision:
        qual_decision = dict(
            evaluate_qualification(outcome or qual_status, campaign.get("follow_up_target"))
        )
    is_interested = bool(qual_decision.get("eligible"))
    event_id = f"{session_call_id}:{lead_id}"
    campaign_id = campaign.get("id")
    client_row = client or {}
    wa_opt_in = _whatsapp_opt_in(meta)
    fb_wa = fallback_initial_whatsapp(
        name=lead.get("name"),
        client_name=client_row.get("name"),
        extraction=extraction_out,
        metadata=meta,
    )
    fb_subj, fb_body = fallback_initial_email(
        name=lead.get("name"),
        client_name=client_row.get("name"),
        extraction=extraction_out,
        metadata=meta,
    )
    fb_inbound = fallback_inbound_whatsapp(
        name=lead.get("name"),
        client_name=client_row.get("name"),
        inbound_text=inbound_text,
        extraction=extraction_out,
        metadata=meta,
    )
    conv = conversation or []
    conv_text = "\n".join(
        f"{(m.get('direction') or 'unknown')}: {m.get('text') or m.get('text_body') or ''}"
        for m in conv
        if (m.get("text") or m.get("text_body"))
    )
    bhk = extraction_out.get("bhk_preference") or extraction_out.get("bhk_preference")
    location = (
        extraction_out.get("location_preference")
        or extraction_out.get("location_preference")
        or meta.get("lead_city")
        or meta.get("city")
    )
    budget = extraction_out.get("budget") or meta.get("budget")
    req_parts = [p for p in (bhk, location, f"budget {budget}" if budget else None) if p]
    requirements = {
        "bhk": bhk,
        "location": location,
        "budget": budget,
        "summary": extraction_out.get("summary") or extraction_out.get("summary"),
        "text": ", ".join(req_parts),
    }

    return {
        # ── Event envelope ──────────────────────────────────────────────
        "event": "lead_qualified",
        "event_type": "INTERESTED_LEAD" if is_interested else "LEAD_QUALIFIED",
        "flow_type": "INITIAL_FOLLOWUP",
        "interested": is_interested,
        "qualification": {
            "eligible": bool(qual_decision.get("eligible")),
            "canonical_outcome": qual_decision.get("canonical_outcome") or qual_status,
            "reason": qual_decision.get("reason"),
            "target": qual_decision.get("target") or campaign.get("follow_up_target"),
            "version": qual_decision.get("version"),
            "status": qual_status,
        },
        "event_id": event_id,
        "client_id": str(client_id),
        "campaign_id": str(campaign_id) if campaign_id else None,
        "lead_id": str(lead_id) if lead_id else None,
        "memory_key": _memory_key(client_id, campaign_id, lead_id),
        "workflow": {
            "id": (workflow or {}).get("id"),
            "name": (workflow or {}).get("name"),
            "source": (workflow or {}).get("source"),
        },
        # n8n must send via /internal/messages/send using this client's integration.
        "whatsapp": {
            "integration_id": None,
            "phone_number_id": None,
            "provider": None,
        },
        # ── Client (Mega_Workflow Lead Context: $json.body.client.*) ───
        "client": {
            "id": str(client_id),
            "name": client_row.get("name"),
            "industry": client_row.get("industry"),
        },
        # ── Lead (Lead Context primary input) ───────────────────────────
        "lead": {
            "id": str(lead_id) if lead_id else None,
            "phone": phone,
            "name": lead.get("name"),
            "email": email,
            "lead_type": lead.get("lead_type"),
            "lead_city": meta.get("lead_city") or meta.get("city"),
            "metadata": meta,
            "whatsapp_opt_in": wa_opt_in,
        },
        # ── Call (legacy + Lead Context aliases) ────────────────────────
        "call": {
            "id": session_call_id,
            "session_call_id": session_call_id,
            "status": "completed",
            "duration": int(duration_seconds or 0),
            "duration_seconds": int(duration_seconds or 0),
            "billed_minutes": int(billed_minutes or 0),
            "credits_charged": float(credits_charged or 0),
            "route": route,
            "recording_url": recording_url,
        },
        # ── Extraction (legacy Mega_Workflow path) ──────────────────────
        "extraction": extraction_out,
        # ── Qualification (structured view for Lead Context) ────────────
        "qualification": {
            "status": qual_status,
            "score": _qualification_score(extraction_out),
            "reason": _qualification_reason(extraction_out, outcome),
        },
        # ── Campaign (legacy + metadata) ────────────────────────────────
        "campaign": {
            "id": str(campaign.get("id")) if campaign.get("id") else None,
            "name": campaign.get("name"),
        },
        # ── Agent / bot config ──────────────────────────────────────────
        "agent": {
            "id": str(bot_config_id) if bot_config_id else None,
        },
        # ── Follow-up hint for WhatsApp branch ──────────────────────────
        "follow_up": {
            "channel": "whatsapp",
            "action": "send" if wa_opt_in and phone else "skip",
            "stage": follow_up_stage,
            "idempotency_key": f"n8n_{event_id}_wa_{follow_up_stage}",
            "skip_reason": (
                None
                if wa_opt_in and phone
                else ("missing_phone" if not phone else "whatsapp_opt_out")
            ),
        },
        # ── Flat metadata for n8n HTTP Request → /internal/messages/send
        "metadata": {
            "campaign_id": str(campaign.get("id")) if campaign.get("id") else None,
            "campaign_name": campaign.get("name"),
            "agent_id": str(bot_config_id) if bot_config_id else None,
        },
        # n8n HTTP Request uses these to persist / look up without hardcoded ngrok.
        "aakashvani": {
            "record_url": _record_url(),
            "context_url": _context_url(),
            "send_url": _send_url(),
            "public_url": public_backend_base_url(),
        },
        # Always present so Mega_Workflow can send if Gemini fails.
        "fallback": {
            "generated_by": "aakashvani-backend",
            "whatsapp": {"message": fb_wa},
            "email": {"subject": fb_subj, "body": fb_body},
            "reply": {"message": fb_inbound},
        },
        "conversation_text": conv_text,
        "conversation": conv,
        "requirements": requirements,
    }


def build_connectivity_test_payload() -> dict[str, Any]:
    """Safe admin connectivity probe — does not trigger customer follow-ups."""
    return {
        "event": "connectivity_test",
        "test": True,
        "source": "aakashvani_admin",
    }


def build_test_payload(*, client_id: UUID | None = None) -> dict[str, Any]:
    """Synthetic payload for admin connectivity tests — clearly marked."""
    from uuid import uuid4

    cid = client_id or uuid4()
    sid = f"test_{uuid4().hex[:12]}"
    lid = uuid4()
    campaign_id = uuid4()
    bot_id = uuid4()
    payload = build_lead_qualified_payload(
        client_id=cid,
        lead={
            "id": lid,
            "name": "Test Lead",
            "phone": "+919999999999",
            "lead_type": "warm",
            "metadata": {"email": "test@example.com", "source": "n8n_connectivity_test"},
        },
        session_call_id=sid,
        duration_seconds=42,
        extraction={
            "intent_status": "Interested",
            "summary": "n8n connectivity test — not a real customer",
        },
        campaign={"id": campaign_id, "name": "Test Campaign"},
        outcome="Interested",
        bot_config_id=bot_id,
        billed_minutes=1,
        credits_charged=0,
        route="sts",
        client={"name": "Test Client", "industry": "real_estate"},
    )
    payload["metadata"] = {**payload["metadata"], "test": True}
    return payload

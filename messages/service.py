"""Messages service — WhatsApp core: send, inbound persist, follow-ups."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from messages import repository as repo
from messages.credentials import (
    decrypt_secret_map,
    encrypt_secret_map,
    public_integration_view,
)
from messages.providers import get_provider, provider_catalog


def _config_from_row(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("configuration") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    secrets = decrypt_secret_map(row.get("credentials_encrypted"))
    out = {
        **cfg,
        "phone_number_id": row.get("phone_number_id") or cfg.get("phone_number_id"),
        "business_account_id": row.get("business_account_id") or cfg.get("business_account_id"),
        "webhook_verify_token": row.get("webhook_verify_token") or secrets.get("webhook_verify_token") or cfg.get("webhook_verify_token"),
        "access_token": secrets.get("access_token") or "",
        "api_key": secrets.get("api_key") or "",
        "app_secret": secrets.get("app_secret") or "",
        "base_url": cfg.get("base_url"),
        "sender_id": cfg.get("sender_id"),
        "allow_simulated_send": bool(cfg.get("allow_simulated_send")),
    }
    return out


async def list_client_conversations(
    pool,
    client_id: UUID,
    search: str | None,
    limit: int,
    offset: int,
    campaign_id: UUID | None = None,
):
    return await repo.list_conversations(
        pool, client_id, search=search, campaign_id=campaign_id, limit=limit, offset=offset
    )


async def get_client_conversation_thread(pool, client_id: UUID, conversation_id: UUID):
    conv = await repo.get_conversation(pool, client_id, conversation_id)
    if not conv:
        return None, []
    msgs = await repo.list_messages(pool, client_id, conversation_id)
    return conv, msgs


async def list_client_templates(pool, client_id: UUID):
    return await repo.list_templates(pool, client_id)


async def list_client_integrations(pool, client_id: UUID) -> list[dict]:
    rows = await repo.list_integrations(pool, client_id)
    return [public_integration_view(r) for r in rows]


async def save_integration(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    provider: str,
    display_name: str | None = None,
    phone_number_id: str | None = None,
    business_account_id: str | None = None,
    webhook_verify_token: str | None = None,
    access_token: str | None = None,
    api_key: str | None = None,
    app_secret: str | None = None,
    integration_id: UUID | None = None,
    status: str = "inactive",
    enabled: bool | None = None,
    configuration: dict | None = None,
) -> dict:
    existing = None
    if integration_id:
        existing = await repo.get_integration(pool, client_id, integration_id)
    secrets = decrypt_secret_map(existing.get("credentials_encrypted") if existing else None)
    if access_token:
        secrets["access_token"] = access_token
    if api_key:
        secrets["api_key"] = api_key
    if app_secret:
        secrets["app_secret"] = app_secret
    if webhook_verify_token:
        secrets["webhook_verify_token"] = webhook_verify_token
    cred_blob = encrypt_secret_map(secrets) if secrets else (existing.get("credentials_encrypted") if existing else None)
    row = await repo.upsert_integration(
        pool,
        client_id=client_id,
        provider=provider or "stub",
        display_name=display_name,
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        webhook_verify_token=webhook_verify_token,
        credentials_encrypted=cred_blob,
        status=status,
        enabled=enabled,
        configuration=configuration,
        integration_id=integration_id,
    )
    return public_integration_view(row)


async def test_integration_connection(pool: asyncpg.Pool, client_id: UUID, integration_id: UUID) -> dict:
    row = await repo.get_integration(pool, client_id, integration_id)
    if not row:
        return {"ok": False, "error": "integration_not_found"}
    provider = get_provider(row.get("provider") or "stub")
    config = _config_from_row(row)
    ok, message = await provider.test_connection(config)
    await repo.set_connection_status(
        pool,
        client_id,
        integration_id,
        connection_status="connected" if ok else "error",
        last_error=None if ok else message,
    )
    return {"ok": ok, "message": message, "provider": provider.name}


async def send_message(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    to_phone: str,
    text: str | None = None,
    template_name: str | None = None,
    language: str | None = None,
    components: dict | list | None = None,
    lead_id: UUID | None = None,
    campaign_id: UUID | None = None,
    customer_name: str | None = None,
    integration_id: UUID | None = None,
    idempotency_key: str | None = None,
    whatsapp_opt_in: bool | None = None,
    force_message_type: str | None = None,
) -> dict:
    from messages.eligibility import decide_send, is_successful_send_status

    # Idempotency: if this key already produced a successful send, do not call the provider again.
    if idempotency_key:
        existing = await repo.get_message_by_idempotency_key(pool, client_id, idempotency_key)
        if existing and is_successful_send_status(existing.get("status")):
            return {
                "ok": True,
                "deduplicated": True,
                "error": None,
                "provider": existing.get("provider"),
                "provider_message_id": existing.get("provider_message_id"),
                "conversation": {"id": str(existing.get("conversation_id"))} if existing.get("conversation_id") else None,
                "message": existing,
            }

    last_inbound = await repo.get_last_inbound_at(pool, client_id, to_phone)
    opt_in = True if whatsapp_opt_in is None else bool(whatsapp_opt_in)
    decision = decide_send(
        to_phone=to_phone,
        whatsapp_opt_in=opt_in,
        last_inbound_at=last_inbound,
        template_name=template_name,
        text=text,
        force_message_type=force_message_type,
    )
    if not decision.ok:
        return {
            "ok": False,
            "error": decision.reason or "send_not_allowed",
            "conversation_window_open": decision.conversation_window_open,
            "phone_e164": decision.phone_e164,
        }

    if integration_id:
        integration = await repo.get_integration(pool, client_id, integration_id)
    else:
        integration = await repo.get_enabled_integration(pool, client_id)
    if not integration:
        return {"ok": False, "error": "no_enabled_whatsapp_integration"}

    provider_name = integration.get("provider") or "stub"
    provider = get_provider(provider_name)
    config = _config_from_row(integration)
    send_phone = decision.phone_e164 or to_phone

    if decision.message_type == "template":
        result = await provider.send_template(
            config,
            to_phone=send_phone,
            template_name=template_name or "",
            language=language,
            components=components if isinstance(components, (dict, list)) else None,
        )
        message_type = "template"
        body = text or template_name
    else:
        result = await provider.send_text(config, to_phone=send_phone, text=text or "")
        message_type = "text"
        body = text

    conversation = await repo.get_or_create_conversation(
        pool,
        client_id=client_id,
        integration_id=UUID(str(integration["id"])),
        customer_phone=send_phone,
        customer_name=customer_name,
        lead_id=lead_id,
        campaign_id=campaign_id,
    )
    status = "sent" if result.ok else "failed"
    stored = await repo.insert_message_idempotent(
        pool,
        client_id=client_id,
        conversation_id=UUID(str(conversation["id"])),
        provider_message_id=result.provider_message_id,
        direction="outgoing",
        message_type=message_type,
        text_body=body,
        status=status,
        provider=provider_name,
        lead_id=lead_id,
        idempotency_key=idempotency_key,
        template_name=template_name,
        provider_metadata=result.raw or ({"error": result.error} if result.error else {}),
    )
    return {
        "ok": result.ok,
        "deduplicated": False,
        "error": result.error,
        "provider": provider_name,
        "provider_message_id": result.provider_message_id,
        "conversation_window_open": decision.conversation_window_open,
        "message_type": message_type,
        "conversation": {k: conversation[k] for k in ("id", "customer_phone", "lead_id", "campaign_id") if k in conversation},
        "message": stored,
    }


async def record_n8n_message(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    to_phone: str,
    text: str | None = None,
    template_name: str | None = None,
    lead_id: UUID | None = None,
    campaign_id: UUID | None = None,
    customer_name: str | None = None,
    idempotency_key: str | None = None,
    direction: str = "outgoing",
    status: str = "sent",
    provider_message_id: str | None = None,
    provider: str = "n8n",
) -> dict:
    """Persist a WhatsApp follow-up that n8n already sent (or inbound reply). Does not call Meta."""
    from messages.eligibility import is_successful_send_status

    if not to_phone or not str(to_phone).strip():
        return {"ok": False, "error": "missing_or_invalid_phone"}
    if direction == "outgoing" and not (text or template_name):
        return {"ok": False, "error": "text_or_template_required"}

    if idempotency_key:
        existing = await repo.get_message_by_idempotency_key(pool, client_id, idempotency_key)
        if existing and is_successful_send_status(existing.get("status")):
            return {
                "ok": True,
                "deduplicated": True,
                "provider": existing.get("provider"),
                "conversation": {"id": str(existing.get("conversation_id"))} if existing.get("conversation_id") else None,
                "message": existing,
            }

    integration = await repo.get_enabled_integration(pool, client_id)
    if not integration:
        integration = await repo.ensure_n8n_bridge_integration(pool, client_id)

    conversation = await repo.get_or_create_conversation(
        pool,
        client_id=client_id,
        integration_id=UUID(str(integration["id"])),
        customer_phone=to_phone.strip(),
        customer_name=customer_name,
        lead_id=lead_id,
        campaign_id=campaign_id,
    )
    stored = await repo.insert_message_idempotent(
        pool,
        client_id=client_id,
        conversation_id=UUID(str(conversation["id"])),
        provider_message_id=provider_message_id,
        direction="incoming" if direction == "incoming" else "outgoing",
        message_type="template" if template_name and not text else "text",
        text_body=text or template_name,
        status=status or "sent",
        provider=provider or integration.get("provider") or "n8n",
        lead_id=lead_id,
        idempotency_key=idempotency_key,
        template_name=template_name,
        provider_metadata={"source": "n8n_mega_workflow"},
    )
    return {
        "ok": True,
        "deduplicated": False,
        "provider": provider,
        "conversation": {
            k: conversation[k]
            for k in ("id", "customer_phone", "lead_id", "campaign_id")
            if k in conversation
        },
        "message": stored,
    }


async def handle_provider_webhook(
    pool: asyncpg.Pool,
    integration_id: UUID,
    *,
    headers: dict[str, str],
    query: dict[str, str],
    raw_body: bytes,
    body: dict[str, Any] | list | None,
) -> dict[str, Any]:
    row = await repo.get_integration_by_id(pool, integration_id)
    if not row:
        return {"ok": False, "error": "integration_not_found", "status_code": 404}

    client_id = UUID(str(row["client_id"]))
    provider = get_provider(row.get("provider") or "stub")
    config = _config_from_row(row)

    if query.get("hub.mode") == "subscribe" or query.get("mode") == "subscribe":
        if provider.verify_webhook(config, headers=headers, raw_body=raw_body, query=query):
            return {
                "ok": True,
                "challenge": query.get("hub.challenge") or query.get("challenge"),
                "status_code": 200,
            }
        return {"ok": False, "error": "verify_failed", "status_code": 403}

    if not provider.verify_webhook(config, headers=headers, raw_body=raw_body, query=query):
        return {
            "ok": False,
            "error": "webhook_verification_failed",
            "status_code": 403,
            "detail": "Invalid or missing webhook verification.",
        }

    events = provider.parse_webhook(headers, body)
    accepted = 0
    cancelled = 0
    for event in events:
        if event.event_type == "status" and event.provider_message_id:
            await repo.update_message_status(
                pool, client_id, event.provider_message_id, event.status or "unknown"
            )
            accepted += 1
            continue
        if not event.customer_phone:
            continue
        conv = await repo.get_or_create_conversation(
            pool,
            client_id=client_id,
            integration_id=integration_id,
            customer_phone=event.customer_phone,
        )
        stored = await repo.insert_message_idempotent(
            pool,
            client_id=client_id,
            conversation_id=UUID(str(conv["id"])),
            provider_message_id=event.provider_message_id,
            direction=event.direction or "incoming",
            message_type=event.message_type or "text",
            text_body=event.text,
            status=event.status or "received",
            provider=provider.name,
            provider_metadata=event.raw,
        )
        if stored:
            accepted += 1
        if (event.direction or "incoming") == "incoming":
            cancelled += await repo.cancel_pending_followups(
                pool,
                client_id,
                conversation_id=UUID(str(conv["id"])),
                customer_phone=event.customer_phone,
                reason="customer_replied",
            )
    return {"ok": True, "accepted": accepted, "followups_cancelled": cancelled, "status_code": 200}


async def start_followups(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    customer_phone: str,
    trigger_outcome: str | None = "Interested",
    lead_id: UUID | None = None,
    campaign_id: UUID | None = None,
    customer_name: str | None = None,
    plan_id: UUID | None = None,
) -> dict:
    if plan_id:
        plans = await repo.list_followup_plans(pool, client_id)
        plan = next((p for p in plans if str(p["id"]) == str(plan_id)), None)
    else:
        plan = await repo.get_active_followup_plan(pool, client_id, trigger_outcome)
    if not plan:
        return {"ok": False, "error": "no_active_followup_plan"}

    integration = await repo.get_enabled_integration(pool, client_id)
    conversation_id = None
    if integration:
        conv = await repo.get_or_create_conversation(
            pool,
            client_id=client_id,
            integration_id=UUID(str(integration["id"])),
            customer_phone=customer_phone,
            customer_name=customer_name,
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
        conversation_id = UUID(str(conv["id"]))

    steps = plan.get("steps") or []
    if isinstance(steps, str):
        steps = json.loads(steps)
    now = datetime.now(timezone.utc)
    jobs = []
    for i, step in enumerate(steps):
        delay = int(step.get("delay_seconds") or 0)
        jobs.append(
            {
                "client_id": client_id,
                "plan_id": UUID(str(plan["id"])),
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "conversation_id": conversation_id,
                "customer_phone": customer_phone,
                "step_index": i,
                "scheduled_at": now + timedelta(seconds=delay),
            }
        )
    count = await repo.insert_followup_jobs(pool, jobs)
    return {"ok": True, "jobs_created": count, "plan_id": str(plan["id"])}


async def process_due_followups(pool: asyncpg.Pool, limit: int = 20) -> dict:
    due = await repo.claim_due_followup_jobs(pool, limit=limit)
    sent = 0
    failed = 0
    skipped = 0
    for job in due:
        client_id = UUID(str(job["client_id"]))
        plans = await repo.list_followup_plans(pool, client_id)
        plan = next((p for p in plans if str(p["id"]) == str(job["plan_id"])), None)
        steps = (plan or {}).get("steps") or []
        if isinstance(steps, str):
            steps = json.loads(steps)
        idx = int(job.get("step_index") or 0)
        if idx >= len(steps):
            await repo.mark_followup_job(pool, UUID(str(job["id"])), client_id, "failed")
            failed += 1
            continue
        step = steps[idx]
        result = await send_message(
            pool,
            client_id=client_id,
            to_phone=job["customer_phone"],
            text=step.get("text"),
            template_name=step.get("template_name"),
            language=step.get("language"),
            components=step.get("components"),
            lead_id=UUID(str(job["lead_id"])) if job.get("lead_id") else None,
            campaign_id=UUID(str(job["campaign_id"])) if job.get("campaign_id") else None,
            idempotency_key=f"followup:{job['id']}",
        )
        msg_id = None
        if result.get("message"):
            msg_id = UUID(str(result["message"]["id"]))
        if result.get("ok"):
            await repo.mark_followup_job(pool, UUID(str(job["id"])), client_id, "sent", msg_id)
            sent += 1
        else:
            await repo.mark_followup_job(pool, UUID(str(job["id"])), client_id, "failed", msg_id)
            failed += 1
            skipped += 0
    return {"ok": True, "processed": len(due), "sent": sent, "failed": failed}


async def list_plans(pool, client_id: UUID):
    return await repo.list_followup_plans(pool, client_id)


async def save_plan(pool, **kwargs):
    return await repo.upsert_followup_plan(pool, **kwargs)

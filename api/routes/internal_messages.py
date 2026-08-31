"""Admin Messages / WhatsApp integration + send + follow-up APIs."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from api.auth import get_pool, require_admin
from messages import service as messages_service
from messages.providers import provider_catalog

router = APIRouter(prefix="/internal/messages", tags=["internal-messages"])


def _record_callback_token() -> str | None:
    secret = (
        (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
        or (os.getenv("ADMIN_API_KEY") or "").strip()
    )
    if not secret:
        return None
    return hashlib.sha256(f"record::{secret}".encode("utf-8")).hexdigest()


async def authorize_record_callback(
    request: Request,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    expected_admin = (os.getenv("ADMIN_API_KEY") or "").strip()
    if expected_admin and x_admin_key and hmac.compare_digest(x_admin_key.strip(), expected_admin):
        return

    provided = (
        (request.query_params.get("token") or "").strip()
        or (request.headers.get("X-Aakashvani-Record-Token") or "").strip()
    )
    expected_token = _record_callback_token()
    if expected_token and provided and hmac.compare_digest(provided, expected_token):
        return

    raise HTTPException(403, "Invalid or missing record callback auth")


# ── Provider catalog ───────────────────────────────────────────────────

@router.get("/providers")
async def get_providers(_admin=Depends(require_admin)):
    """Expose available provider keys + their field schemas to Admin UI. No credentials returned."""
    return {"providers": provider_catalog()}


# ── Integration CRUD ───────────────────────────────────────────────────

class UpsertIntegrationBody(BaseModel):
    client_id: UUID
    provider: str = Field(default="stub", max_length=50)
    display_name: str | None = None
    phone_number_id: str | None = None
    business_account_id: str | None = None
    webhook_verify_token: str | None = None
    access_token: str | None = Field(default=None, description="Write-only. Never returned.")
    api_key: str | None = Field(default=None, description="Write-only.")
    app_secret: str | None = Field(default=None, description="Write-only.")
    status: str = "inactive"
    enabled: bool | None = None
    configuration: dict | None = None
    integration_id: UUID | None = None


@router.get("/integrations")
async def admin_list_integrations(
    client_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    return {"integrations": await messages_service.list_client_integrations(pool, client_id)}


@router.post("/integrations")
async def admin_upsert_integration(
    body: UpsertIntegrationBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    from messages.providers.factory import PROVIDER_KEYS
    if body.provider not in PROVIDER_KEYS:
        raise HTTPException(400, f"unsupported provider; valid: {', '.join(PROVIDER_KEYS)}")
    row = await messages_service.save_integration(
        pool,
        client_id=body.client_id,
        provider=body.provider,
        display_name=body.display_name,
        phone_number_id=body.phone_number_id,
        business_account_id=body.business_account_id,
        webhook_verify_token=body.webhook_verify_token,
        access_token=body.access_token,
        api_key=body.api_key,
        app_secret=body.app_secret,
        integration_id=body.integration_id,
        status=body.status,
        enabled=body.enabled,
        configuration=body.configuration,
    )
    return {"integration": row}


@router.post("/integrations/{integration_id}/test")
async def admin_test_integration(
    integration_id: UUID,
    client_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    result = await messages_service.test_integration_connection(pool, client_id, integration_id)
    if result.get("error") == "integration_not_found":
        raise HTTPException(404, "integration not found")
    return result


# ── Send (called by n8n or admin; never React directly) ────────────────

class SendMessageBody(BaseModel):
    client_id: UUID
    to_phone: str
    text: str | None = None
    template_name: str | None = None
    language: str | None = None
    components: dict | list | None = None
    lead_id: UUID | None = None
    campaign_id: UUID | None = None
    customer_name: str | None = None
    integration_id: UUID | None = None
    idempotency_key: str | None = None
    whatsapp_opt_in: bool | None = None
    force_message_type: str | None = Field(
        default=None,
        description="Optional override: 'text' or 'template'. When omitted, window + content decide.",
    )


@router.post("/send")
async def admin_send_message(
    body: SendMessageBody,
    _auth=Depends(authorize_record_callback),
    pool=Depends(get_pool),
):
    """Send WhatsApp via the client's enabled integration provider.

    Designed for n8n → POST /internal/messages/send with admin key.
    n8n doesn't need to know the provider or credential details.
    """
    result = await messages_service.send_message(
        pool,
        client_id=body.client_id,
        to_phone=body.to_phone,
        text=body.text,
        template_name=body.template_name,
        language=body.language,
        components=body.components,
        lead_id=body.lead_id,
        campaign_id=body.campaign_id,
        customer_name=body.customer_name,
        integration_id=body.integration_id,
        idempotency_key=body.idempotency_key,
        whatsapp_opt_in=body.whatsapp_opt_in,
        force_message_type=body.force_message_type,
    )
    status_code = 200 if result.get("ok") else 502
    return result


class RecordMessageBody(BaseModel):
    client_id: UUID
    to_phone: str
    text: str | None = None
    template_name: str | None = None
    lead_id: UUID | None = None
    campaign_id: UUID | None = None
    customer_name: str | None = None
    idempotency_key: str | None = None
    direction: str = "outgoing"
    status: str = "sent"
    provider_message_id: str | None = None

    @field_validator("lead_id", "campaign_id", mode="before")
    @classmethod
    def empty_uuid(cls, v):
        if v in ("", None, "null", "undefined"):
            return None
        return v


@router.post("/record")
async def admin_record_message(
    body: RecordMessageBody,
    _auth=Depends(authorize_record_callback),
    pool=Depends(get_pool),
):
    """Persist a message n8n already sent (or an inbound reply) into Messages inbox."""
    result = await messages_service.record_n8n_message(
        pool,
        client_id=body.client_id,
        to_phone=body.to_phone,
        text=body.text,
        template_name=body.template_name,
        lead_id=body.lead_id,
        campaign_id=body.campaign_id,
        customer_name=body.customer_name,
        idempotency_key=body.idempotency_key,
        direction=body.direction,
        status=body.status,
        provider_message_id=body.provider_message_id,
    )
    status_code = 200 if result.get("ok") else 400
    return result


@router.get("/conversations")
async def admin_list_conversations(
    client_id: UUID,
    search: str | None = None,
    campaign_id: UUID | None = None,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    rows, total = await messages_service.list_client_conversations(
        pool, client_id, search=search, campaign_id=campaign_id, limit=100, offset=0
    )
    return {"conversations": rows, "total": total}


# ── Follow-up plans ──────────────────────────────────────────────────

class FollowupPlanBody(BaseModel):
    client_id: UUID
    name: str
    trigger_outcome: str = "Interested"
    steps: list = Field(
        default_factory=list,
        description="[{template_name, language, delay_seconds, text?}, ...]",
    )
    active: bool = True
    plan_id: UUID | None = None


@router.get("/followup-plans")
async def admin_list_followup_plans(
    client_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    return {"plans": await messages_service.list_plans(pool, client_id)}


@router.post("/followup-plans")
async def admin_upsert_followup_plan(
    body: FollowupPlanBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    row = await messages_service.save_plan(
        pool,
        client_id=body.client_id,
        name=body.name,
        trigger_outcome=body.trigger_outcome,
        steps=body.steps,
        active=body.active,
        plan_id=body.plan_id,
    )
    return {"plan": row}


class StartFollowupBody(BaseModel):
    client_id: UUID
    customer_phone: str
    trigger_outcome: str | None = "Interested"
    lead_id: UUID | None = None
    campaign_id: UUID | None = None
    customer_name: str | None = None
    plan_id: UUID | None = None


@router.post("/followups/start")
async def admin_start_followups(
    body: StartFollowupBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    """Start follow-up for a lead/phone. Called by n8n after lead_qualified."""
    result = await messages_service.start_followups(
        pool,
        client_id=body.client_id,
        customer_phone=body.customer_phone,
        trigger_outcome=body.trigger_outcome,
        lead_id=body.lead_id,
        campaign_id=body.campaign_id,
        customer_name=body.customer_name,
        plan_id=body.plan_id,
    )
    return result


@router.post("/followups/process")
async def admin_process_followups(
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    """Process due follow-up jobs. Call periodically (cron/timer)."""
    result = await messages_service.process_due_followups(pool)
    return result


# ── Provider webhook boundary ──────────────────────────────────────────

@router.api_route("/webhooks/{integration_id}", methods=["GET", "POST"])
async def messages_webhook(
    integration_id: UUID,
    request: Request,
    pool=Depends(get_pool),
):
    raw = await request.body()
    body = None
    if raw:
        try:
            body = await request.json()
        except Exception:
            body = None
    headers = {k.lower(): v for k, v in request.headers.items()}
    query = {k: v for k, v in request.query_params.items()}
    result = await messages_service.handle_provider_webhook(
        pool,
        integration_id,
        headers=headers,
        query=query,
        raw_body=raw,
        body=body,
    )
    status = int(result.get("status_code") or 200)
    if result.get("challenge") is not None:
        return Response(content=str(result["challenge"]), media_type="text/plain", status_code=status)
    if not result.get("ok"):
        raise HTTPException(status, result.get("error") or result.get("detail") or "webhook rejected")
    return {"ok": True, "accepted": result.get("accepted", 0), "followups_cancelled": result.get("followups_cancelled", 0)}

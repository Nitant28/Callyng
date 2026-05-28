"""Admin /internal/* routes."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_pool, require_admin
from db import postgres as pg_db

router = APIRouter(prefix="/internal", tags=["internal"])

_SCRIPT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CreateClientBody(BaseModel):
    name: str
    contact_email: str = ""
    industry: str = "other"


class CreditsBody(BaseModel):
    amount: float
    note: str = "Manual top-up"


class CreateBotConfigBody(BaseModel):
    client_id: UUID
    name: str
    route: str
    script_id: str
    telephony_number: str
    credits_per_minute: float


class CreateCampaignBody(BaseModel):
    client_id: UUID
    bot_config_id: UUID
    name: str
    budget_credits: float = Field(ge=0)
    max_concurrent_calls: int = 5
    calls_per_minute: int = 10
    max_attempts: int = 3
    retry_delay_minutes: int = 120
    max_call_minutes: int | None = None


class PatchCampaignBody(BaseModel):
    client_id: UUID
    name: str | None = None
    max_concurrent_calls: int | None = None
    calls_per_minute: int | None = None
    max_attempts: int | None = None
    retry_delay_minutes: int | None = None
    max_call_minutes: int | None = None


class WebhookConfigBody(BaseModel):
    client_id: UUID
    event: str
    url: str
    secret: str


@router.post("/clients")
async def create_client(
    body: CreateClientBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    client_id, raw_key = await pg_db.create_client(
        pool, body.name, body.contact_email, body.industry
    )
    return {
        "id": str(client_id),
        "name": body.name,
        "api_key": raw_key,
        "message": "Save api_key now — it will not be shown again.",
    }


@router.get("/clients")
async def list_clients(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    return {"clients": await pg_db.get_all_clients(pool)}


@router.patch("/clients/{client_id}/credits")
async def patch_client_credits(
    client_id: UUID,
    body: CreditsBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    if body.amount < 0:
        raise HTTPException(400, "Amount cannot be negative")
    try:
        balance = await pg_db.add_credits(pool, client_id, body.amount, body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"balance_credits": balance}


@router.post("/bot-configs")
async def create_bot_config(
    body: CreateBotConfigBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    if not _SCRIPT_ID_RE.fullmatch(body.script_id):
        raise HTTPException(422, "script_id validation failed")
    if body.route not in ("sts", "cascaded"):
        raise HTTPException(422, "route must be sts or cascaded")
    bot_id = await pg_db.create_bot_config(
        pool,
        body.client_id,
        body.name,
        body.route,
        body.script_id,
        body.telephony_number,
        body.credits_per_minute,
    )
    return {"id": str(bot_id)}


@router.get("/bot-configs")
async def list_bot_configs(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    return {"bot_configs": await pg_db.list_bot_configs(pool, None)}


@router.post("/campaigns")
async def create_campaign(
    body: CreateCampaignBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        campaign_id = await pg_db.create_campaign(
            pool,
            body.client_id,
            body.bot_config_id,
            body.name,
            body.budget_credits,
            body.max_concurrent_calls,
            body.calls_per_minute,
            body.max_attempts,
            body.retry_delay_minutes,
            body.max_call_minutes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    campaign = await pg_db.get_campaign(pool, campaign_id, body.client_id)
    row = await pool.fetchrow(
        "SELECT balance_credits FROM clients WHERE id = $1", body.client_id
    )
    return {
        "id": str(campaign_id),
        "campaign": campaign,
        "balance_credits": float(row["balance_credits"]) if row else None,
    }


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: UUID,
    body: PatchCampaignBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign(pool, campaign_id, body.client_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    await pg_db.update_campaign_settings(
        pool,
        campaign_id,
        body.client_id,
        name=body.name,
        max_concurrent_calls=body.max_concurrent_calls,
        calls_per_minute=body.calls_per_minute,
        max_attempts=body.max_attempts,
        retry_delay_minutes=body.retry_delay_minutes,
        max_call_minutes=body.max_call_minutes,
    )
    return {"campaign": await pg_db.get_campaign(pool, campaign_id, body.client_id)}


@router.post("/webhook-configs")
async def create_webhook_config(
    body: WebhookConfigBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    wh_id = await pg_db.upsert_webhook_config(
        pool, body.client_id, body.event, body.url, body.secret
    )
    return {"id": str(wh_id)}


@router.get("/calls")
async def list_all_calls(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    limit: int = 50,
    offset: int = 0,
):
    return {"calls": await pg_db.list_call_logs(pool, None, limit=limit, offset=offset)}

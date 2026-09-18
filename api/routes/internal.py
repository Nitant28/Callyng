"""Admin /internal/* routes."""

from __future__ import annotations

import json
import os
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, Field

from api.auth import get_pool, require_admin
from api.script_config_validation import normalize_route, validate_route
from db import postgres as pg_db
from dialer.concurrent_dialer import start_dialer, stop_dialer
from recording import resolve_recording_url
from telephony import fetch_plivo_cash_credits

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
    script_config_id: UUID | None = None
    telephony_number: str
    credits_per_minute: float = Field(ge=0, le=9999.99)
    fixed_start_credits: float | None = Field(default=None, ge=0, le=999999.9999)


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

class CreateEventBody(BaseModel):
    client_id: UUID
    name: str
    description: str | None = None

    source_types: list[str] | None = None
    lead_handling: str | None = None

    primary_bot_config_id: UUID

    max_concurrent_calls: int = Field(default=5, ge=1)
    calls_per_minute: int = Field(default=10, ge=1)
    max_attempts: int = Field(default=3, ge=1)

    attempt_0_schedule_minutes: int | None = None
    attempt_1_schedule_minutes: int | None = None
    attempt_2_schedule_minutes: int | None = None

class PatchEventBody(BaseModel):
    name: str | None = None
    description: str | None = None
    source_types: list[str] | None = None
    lead_handling: str | None = None
    status: str | None = None
    primary_bot_config_id: UUID | None = None

    max_concurrent_calls: int | None = Field(default=None, ge=1)
    calls_per_minute: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)

    attempt_0_schedule_minutes: int | None = None
    attempt_1_schedule_minutes: int | None = None
    attempt_2_schedule_minutes: int | None = None


class CreateOutcomeMappingBody(BaseModel):
    outcome: str
    bot_config_id: UUID




class PatchCampaignBody(BaseModel):
    name: str | None = None
    max_concurrent_calls: int | None = None
    calls_per_minute: int | None = None
    max_attempts: int | None = None
    retry_delay_minutes: int | None = None
    max_call_minutes: int | None = None


class WebhookConfigBody(BaseModel):
    client_id: UUID
    campaign_id: UUID
    event: str
    url: str
    secret: str | None = None


class ClientStatusBody(BaseModel):
    active: bool


class PatchClientBody(BaseModel):
    name: str | None = None
    contact_email: str | None = None
    industry: str | None = None


class BotConfigPatchBody(BaseModel):
    name: str | None = None
    route: str | None = None
    script_id: str | None = None
    script_config_id: UUID | None = None
    telephony_number: str | None = None
    credits_per_minute: float | None = Field(default=None, ge=0, le=9999.99)
    fixed_start_credits: float | None = Field(default=None, ge=0, le=999999.9999)
    active: bool | None = None


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
    search: Optional[str] = Query(None),
):
    clients = await pg_db.get_all_clients(pool)
    if search:
        q = search.lower()
        clients = [c for c in clients if q in (c.get("name") or "").lower()
                   or q in (c.get("industry") or "").lower()
                   or q in (c.get("contact_email") or "").lower()]
    return {"clients": clients}


@router.get("/clients/{client_id}")
async def get_client(
    client_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    client = await pg_db.get_client(pool, client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    return {"client": client}


@router.post("/clients/{client_id}/regenerate-key")
async def regenerate_key(
    client_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    # Verify client exists
    client = await pg_db.get_client(pool, client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
        
    raw_key = await pg_db.regenerate_client_key(pool, client_id)
    return {
        "api_key": raw_key,
        "message": "Save api_key now — it will not be shown again."
    }


@router.patch("/clients/{client_id}")
async def patch_client(
    client_id: UUID,
    body: PatchClientBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    sets = []
    args = []
    idx = 1
    if body.name is not None:
        sets.append(f"name = ${idx}")
        args.append(body.name)
        idx += 1
    if body.contact_email is not None:
        sets.append(f"contact_email = ${idx}")
        args.append(body.contact_email)
        idx += 1
    if body.industry is not None:
        sets.append(f"industry = ${idx}")
        args.append(body.industry)
        idx += 1
    if sets:
        args.append(client_id)
        await pool.execute(
            f"UPDATE clients SET {', '.join(sets)} WHERE id = ${idx}", *args
        )
    return {"client": await pg_db.get_client(pool, client_id)}


@router.patch("/clients/{client_id}/status")
async def patch_client_status(
    client_id: UUID,
    body: ClientStatusBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    await pg_db.update_client_status(pool, client_id, body.active)
    return {"client": await pg_db.get_client(pool, client_id)}


@router.patch("/clients/{client_id}/credits")
async def patch_client_credits(
    client_id: UUID,
    body: CreditsBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        balance = await pg_db.add_credits(pool, client_id, body.amount, body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"balance_credits": balance}


@router.get("/clients/{client_id}/credits")
async def list_client_credits(
    client_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    txs = await pg_db.list_credit_transactions(pool, client_id)
    return {"transactions": txs}


@router.get("/clients/{client_id}/webhooks")
async def list_client_webhooks(
    client_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    client = await pg_db.get_client(pool, client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    webhooks = await pg_db.get_webhook_configs(pool, client_id, include_inactive=True)
    return {
        "webhooks": webhooks,
        "events": sorted(pg_db.WEBHOOK_EVENTS),
    }


@router.post("/bot-configs")
async def create_bot_config(
    body: CreateBotConfigBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    if not _SCRIPT_ID_RE.fullmatch(body.script_id):
        raise HTTPException(422, "script_id validation failed")
    route = normalize_route(body.route)
    try:
        validate_route(route)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    bot_id = await pg_db.create_bot_config(
        pool,
        body.client_id,
        body.name,
        route,
        body.script_id,
        body.telephony_number,
        body.credits_per_minute,
        script_config_id=body.script_config_id,
        fixed_start_credits=body.fixed_start_credits,
    )
    return {"id": str(bot_id)}


@router.get("/bot-configs")
async def list_bot_configs(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    search: Optional[str] = Query(None),
    client_id: Optional[UUID] = Query(None),
):
    bots = await pg_db.list_bot_configs(pool, client_id)
    # Hide seeded CLI sandboxes from the UI
    bots = [b for b in bots if not b.get("name", "").startswith("CLI Sandbox")]
    if search:
        q = search.lower()
        bots = [b for b in bots if q in (b.get("name") or "").lower()
                or q in (b.get("script_id") or "").lower()]
    return {"bot_configs": bots}


@router.get("/bot-configs/{bot_config_id}")
async def get_bot_config(
    bot_config_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    row = await pool.fetchrow("SELECT * FROM bot_configs WHERE id = $1", bot_config_id)
    if row is None:
        raise HTTPException(404, "Bot config not found")
    return {"bot_config": pg_db.record_to_dict(row)}


@router.patch("/bot-configs/{bot_config_id}")
async def patch_bot_config(
    bot_config_id: UUID,
    body: BotConfigPatchBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    sets = []
    args = []
    idx = 1
    if body.name is not None:
        sets.append(f"name = ${idx}")
        args.append(body.name)
        idx += 1
    if body.route is not None:
        route = normalize_route(body.route)
        try:
            validate_route(route)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        sets.append(f"route = ${idx}")
        args.append(route)
        idx += 1
    if body.script_id is not None:
        if not _SCRIPT_ID_RE.fullmatch(body.script_id):
            raise HTTPException(422, "script_id validation failed")
        sets.append(f"script_id = ${idx}")
        args.append(body.script_id)
        idx += 1
    if body.script_config_id is not None:
        sets.append(f"script_config_id = ${idx}")
        args.append(body.script_config_id)
        idx += 1
    if body.telephony_number is not None:
        sets.append(f"telephony_number = ${idx}")
        args.append(body.telephony_number)
        idx += 1
    if body.credits_per_minute is not None:
        sets.append(f"credits_per_minute = ${idx}")
        args.append(body.credits_per_minute)
        idx += 1
    if body.fixed_start_credits is not None:
        sets.append(f"fixed_start_credits = ${idx}")
        args.append(body.fixed_start_credits)
        idx += 1
    if body.active is not None:
        sets.append(f"active = ${idx}")
        args.append(body.active)
        idx += 1
    if sets:
        args.append(bot_config_id)
        await pool.execute(f"UPDATE bot_configs SET {', '.join(sets)} WHERE id = ${idx}", *args)
    row = await pool.fetchrow("SELECT * FROM bot_configs WHERE id = $1", bot_config_id)
    return {"bot_config": pg_db.record_to_dict(row) if row else None}


@router.get("/bot-configs/{bot_config_id}/outcomes")
async def get_bot_outcomes(
    bot_config_id: UUID,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    bot = await pg_db.get_bot_config(pool, bot_config_id, client_id)

    if bot is None:
        raise HTTPException(404, "Bot config not found")

    script_config_id = bot.get("script_config_id")

    if not script_config_id:
        return {"outcomes": []}

    config = await pg_db.get_script_config(
        pool,
        UUID(str(script_config_id)),
        client_id,
    )

    if config is None:
        return {"outcomes": []}

    schema = config.get("extraction_schema") or {}

    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except json.JSONDecodeError:
            return {"outcomes": []}

    outcomes = []

    for field in schema.get("fields", []):
        if field.get("key") == "intent_status":
            values = field.get("values", [])
            if isinstance(values, list):
                outcomes = values
            break

    return {"outcomes": outcomes}



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


# =========================================

@router.post("/events")
async def create_event(
    body: CreateEventBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        event = await pg_db.create_event(
            pool,
            body.client_id,
            body.name,
            body.description,
            body.source_types,
            body.lead_handling,
            body.primary_bot_config_id,
            body.max_concurrent_calls,
            body.calls_per_minute,
            body.max_attempts,
            body.attempt_0_schedule_minutes,
            body.attempt_1_schedule_minutes,
            body.attempt_2_schedule_minutes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "id": str(event["id"]),
        "event": event,
    }


@router.patch("/events/{event_id}")
async def patch_event_admin(
    event_id: UUID,
    body: PatchEventBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    event = await pg_db.get_event_admin(pool, event_id)

    if event is None:
        raise HTTPException(404, "Event not found")

    client_id = UUID(str(event["client_id"]))

    if body.primary_bot_config_id is not None:
        bot = await pg_db.get_bot_config(
            pool,
            body.primary_bot_config_id,
            client_id,
        )

        if bot is None:
            raise HTTPException(
                400,
                "Bot does not belong to this event's client",
            )

    try:
        updated = await pg_db.update_event(
            pool,
            event_id,
            client_id,
            name=body.name,
            description=body.description,
            source_types=body.source_types,
            lead_handling=body.lead_handling,
            status=body.status,
            primary_bot_config_id=body.primary_bot_config_id,
            max_concurrent_calls=body.max_concurrent_calls,
            calls_per_minute=body.calls_per_minute,
            max_attempts=body.max_attempts,
            attempt_0_schedule_minutes=body.attempt_0_schedule_minutes,
            attempt_1_schedule_minutes=body.attempt_1_schedule_minutes,
            attempt_2_schedule_minutes=body.attempt_2_schedule_minutes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if updated is None:
        raise HTTPException(404, "Event not found")

    return {
        "event": updated,
    }

@router.delete("/events/{event_id}")
async def delete_event_admin(
    event_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    event = await pg_db.get_event_admin(pool, event_id)

    if event is None:
        raise HTTPException(404, "Event not found")

    client_id = UUID(str(event["client_id"]))

    deleted = await pg_db.delete_event(
        pool,
        event_id,
        client_id,
    )

    if not deleted:
        raise HTTPException(404, "Event not found")

    return {
        "success": True,
        "event_id": str(event_id),
    }

@router.get("/events")
async def list_events_admin(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    search: Optional[str] = Query(None),
    client_id: Optional[UUID] = Query(None),
):
    if client_id:
        rows = await pool.fetch(
            """
            SELECT *
            FROM events
            WHERE client_id = $1
            ORDER BY created_at DESC
            LIMIT 200
            """,
            client_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT *
            FROM events
            ORDER BY created_at DESC
            LIMIT 200
            """
        )

    events = pg_db.records_to_dicts(rows)

    if search:
        q = search.lower()
        events = [
            event
            for event in events
            if q in (event.get("name") or "").lower()
        ]

    return {"events": events}

@router.post("/events/{event_id}/outcomes")
async def create_event_outcome_admin(
    event_id: UUID,
    body: CreateOutcomeMappingBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    event = await pool.fetchrow(
        """
        SELECT *
        FROM events
        WHERE id = $1
        """,
        event_id,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    client_id = UUID(str(event["client_id"]))

    # Make sure the selected bot belongs to this event's client.
    bot = await pg_db.get_bot_config(
        pool,
        body.bot_config_id,
        client_id,
    )

    if bot is None:
        raise HTTPException(
            400,
            "Bot does not belong to this event's client",
        )

    try:
        mapping = await pg_db.create_event_outcome_bot_mapping(
            pool,
            event_id,
            body.outcome,
            body.bot_config_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "mapping": mapping,
    }


# ===========================

@router.get("/campaigns")
async def list_campaigns_admin(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    client_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
):
    if client_id is not None:
        campaigns = await pg_db.list_campaigns(pool, client_id)
    else:
        rows = await pool.fetch(
            "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 200"
        )
        campaigns = pg_db.records_to_dicts(rows)
    # Hide seeded CLI sandboxes from the UI
    campaigns = [c for c in campaigns if not c.get("name", "").startswith("CLI Test Sandbox")]
    if search:
        q = search.lower()
        campaigns = [c for c in campaigns if q in (c.get("name") or "").lower()]
    return {"campaigns": campaigns}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    return {"campaign": camp}


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: UUID,
    body: PatchCampaignBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    await pg_db.update_campaign_settings(
        pool,
        campaign_id,
        client_id,
        name=body.name,
        max_concurrent_calls=body.max_concurrent_calls,
        calls_per_minute=body.calls_per_minute,
        max_attempts=body.max_attempts,
        retry_delay_minutes=body.retry_delay_minutes,
        max_call_minutes=body.max_call_minutes,
    )
    return {"campaign": await pg_db.get_campaign_admin(pool, campaign_id)}


@router.patch("/campaigns/{campaign_id}/stop")
async def stop_campaign_admin(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    await stop_dialer(campaign_id, client_id)
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
    await pg_db.update_campaign_status(pool, campaign_id, client_id, "paused")
    return {"status": "paused", "released_calling_leads": released}


@router.patch("/campaigns/{campaign_id}/start")
async def start_campaign_admin(
    campaign_id: UUID,
    request: Request,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    if camp["status"] not in ("draft", "paused", "pausing"):
        raise HTTPException(409, f"Cannot start a {camp['status']} campaign")
    budget = float(camp.get("budget_credits") or 0)
    used = float(camp.get("budget_used_credits") or 0)
    if budget - used < 2:
        raise HTTPException(400, "Campaign has insufficient remaining budget to start")
    client_id = UUID(str(camp["client_id"]))
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
    bumped_retry = await pg_db.bump_pending_retry_to_now(pool, campaign_id, client_id)
    counter_snapshot = await pg_db.reconcile_campaign_counters(pool, campaign_id, client_id)
    await pg_db.update_campaign_status(pool, campaign_id, client_id, "running")
    host = (os.getenv("DIALER_CALLBACK_HOST") or os.getenv("NGROK_URL") or "").strip()
    if not host:
        host = request.headers.get("host", "localhost:7860")
    await start_dialer(request.app, campaign_id, client_id, host=host)
    return {
        "status": "running",
        "campaign_id": str(campaign_id),
        "released_calling_leads": released,
        "bumped_pending_retry": bumped_retry,
        "counters": counter_snapshot,
    }


@router.patch("/campaigns/{campaign_id}/cancel")
async def cancel_campaign_admin(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    if camp["status"] in ("completed", "cancelled"):
        raise HTTPException(409, f"Campaign already {camp['status']}")
    client_id = UUID(str(camp["client_id"]))
    await stop_dialer(campaign_id, client_id)
    try:
        result = await pg_db.cancel_campaign(pool, campaign_id, client_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"campaign_id": str(campaign_id), **result}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign_admin(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    await stop_dialer(campaign_id, client_id)
    try:
        result = await pg_db.delete_campaign(pool, campaign_id, client_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.post("/campaigns/{campaign_id}/reconcile")
async def reconcile_campaign(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    counts = await pg_db.reconcile_campaign_counters(pool, campaign_id, client_id)
    return {"campaign_id": str(campaign_id), "counters": counts}


@router.post("/campaigns/{campaign_id}/release-stuck")
async def release_stuck(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
    return {"campaign_id": str(campaign_id), "released": released}


@router.get("/campaigns/{campaign_id}/leads")
async def list_campaign_leads_admin(
    campaign_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    camp = await pg_db.get_campaign_admin(pool, campaign_id)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    client_id = UUID(str(camp["client_id"]))
    leads, total = await pg_db.list_campaign_leads(
        pool, campaign_id, client_id, limit=limit, offset=offset, status=status
    )
    return {"leads": leads, "total_count": total}

@router.get("/clients/{client_id}/lead-outcomes")
async def list_lead_outcomes(
    client_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    outcomes = await pg_db.list_campaign_outcomes(pool, client_id)
    return {"outcomes": outcomes}

@router.post("/webhook-configs")
async def create_webhook_config(
    body: WebhookConfigBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    event = (body.event or "").strip()
    if event not in pg_db.WEBHOOK_EVENTS:
        raise HTTPException(
            422,
            f"Invalid event. Allowed: {', '.join(sorted(pg_db.WEBHOOK_EVENTS))}",
        )
    url = (body.url or "").strip()
    if not url.startswith(("https://", "http://")):
        raise HTTPException(422, "url must be an absolute http(s) webhook URL")

    campaign = await pg_db.get_campaign(pool, body.campaign_id, body.client_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found for this client")

    wh_id = await pg_db.upsert_webhook_config(
        pool,
        body.client_id,
        body.campaign_id,
        event,
        url,
        body.secret,
    )
    row = await pg_db.get_webhook_config_by_id(pool, wh_id)
    return {"id": str(wh_id), "webhook": row}


@router.delete("/webhook-configs/{webhook_id}")
async def delete_webhook_config(
    webhook_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    existing = await pg_db.get_webhook_config_by_id(pool, webhook_id)
    if existing is None:
        raise HTTPException(404, "Webhook config not found")
    deleted = await pg_db.delete_webhook_config(pool, webhook_id)
    if not deleted:
        raise HTTPException(404, "Webhook config not found")
    return {"ok": True, "id": str(webhook_id)}


@router.post("/webhook-configs/{webhook_id}/test")
async def test_webhook_config(
    webhook_id: UUID,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    """POST a connectivity probe to the configured campaign webhook URL."""
    from integrations.n8n.routing import SOURCE_CAMPAIGN_WEBHOOK, ResolvedWorkflow, n8n_config_for
    from integrations.n8n.service import N8nService

    row = await pg_db.get_webhook_config_by_id(pool, webhook_id)
    if row is None:
        raise HTTPException(404, "Webhook config not found")
    url = str(row.get("url") or "").strip()
    if not url:
        raise HTTPException(422, "Webhook has no URL configured")

    dest = ResolvedWorkflow(
        ok=True,
        webhook_url=url,
        source=SOURCE_CAMPAIGN_WEBHOOK,
        webhook_secret=(str(row["secret"]).strip() if row.get("secret") else None),
        event=str(row.get("event") or ""),
        workflow_id=str(row["id"]),
        workflow_name=str(row.get("campaign_name") or "") or None,
    )
    service = N8nService(n8n_config_for(dest), pool=pool)
    result = await service.send_test_event()
    status = "ok" if result.ok else "failed"
    await pg_db.mark_webhook_config_tested(pool, webhook_id, status=status)
    if not result.ok:
        raise HTTPException(
            502,
            result.error or "Webhook test failed",
        )
    return {
        "ok": True,
        "message": f"Connected to campaign webhook ({result.status_code})",
        "status_code": result.status_code,
        "url": url.split("?")[0],
        "event": row.get("event"),
        "campaign_id": str(row.get("campaign_id")) if row.get("campaign_id") else None,
    }


@router.get("/calls")
async def list_all_calls(
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    calls, total = await pg_db.list_call_logs(pool, None, limit=limit, offset=offset, search=search)
    return {"calls": calls, "total_count": total}


@router.get("/calls/{session_call_id}")
async def get_call_admin(
    session_call_id: str,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    call = await pg_db.get_call_log_by_session(pool, session_call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    return {"call": call}


@router.get("/calls/{session_call_id}/recording")
async def get_call_recording_admin(
    session_call_id: str,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    call = await pg_db.get_call_log_by_session(pool, session_call_id)
    if not call:
        raise HTTPException(404, "Call not found")
        
    recording_key = call.get("recording_url")
    if not recording_key:
        raise HTTPException(404, "No recording available for this call")

    if recording_key.startswith("local:"):
        filename = recording_key.removeprefix("local:")
        file_path = Path("./data/recordings") / filename
        if not file_path.exists():
            raise HTTPException(404, "Recording file not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    url = resolve_recording_url(recording_key, expires_in=3600)
    return {"url": url, "expires_in": 3600}


@router.get("/scripts")
async def list_scripts(_: None = Depends(require_admin)):
    scripts = []
    
    def scan_dir(route_name, path):
        if os.path.exists(path):
            for f in os.listdir(path):
                if f.endswith(".py") and not f.startswith("__"):
                    scripts.append({"route": route_name, "script_id": f[:-3]})
                    
    scan_dir("sts", "sts_scripts")
    scan_dir("cascaded", "cascade_scripts")
    return {"scripts": scripts}


@router.get("/stats")
async def get_stats(_: None = Depends(require_admin), pool=Depends(get_pool)):
    total_calls_today = await pool.fetchval("SELECT COUNT(*) FROM call_logs WHERE started_at >= CURRENT_DATE")
    active_campaigns = await pool.fetchval("SELECT COUNT(*) FROM campaigns WHERE status = 'running'")
    total_credits_used_today = await pool.fetchval("SELECT SUM(credits_charged) FROM call_logs WHERE started_at >= CURRENT_DATE")
    telephony_credits_today = await pool.fetchval(
        "SELECT SUM((call_data->>'setup_charge')::numeric) FROM call_logs WHERE started_at >= CURRENT_DATE"
    )
    bot_credits_today = await pool.fetchval(
        "SELECT SUM((call_data->>'duration_charge')::numeric) FROM call_logs WHERE started_at >= CURRENT_DATE"
    )
    return {
        "total_calls_today": total_calls_today or 0,
        "active_campaigns": active_campaigns or 0,
        "total_credits_used_today": float(total_credits_used_today or 0),
        "telephony_credits_today": float(telephony_credits_today or 0),
        "bot_credits_today": float(bot_credits_today or 0),
    }


@router.get("/health")
async def extended_health(
    request: Request,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    active_calls = await pool.fetchval("SELECT COUNT(*) FROM call_logs WHERE in_progress = TRUE")
    pool_stats = {
        "size": pool.get_size(),
        "idle": pool.get_idle_size(),
    }
    plivo_balance = None
    try:
        plivo_balance = float(await fetch_plivo_cash_credits(request.app.state.session))
    except Exception:
        pass

    return {
        "status": "ok",
        "active_calls": active_calls or 0,
        "pool": pool_stats,
        "plivo_balance": plivo_balance,
        "dialer_tasks": len(getattr(request.app.state, "dialer_tasks", {})),
    }

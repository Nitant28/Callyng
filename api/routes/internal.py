"""Admin /internal/* routes."""

from __future__ import annotations

import os
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import get_pool, require_admin
from api.script_config_validation import normalize_route, validate_route
from db import postgres as pg_db
from dialer.concurrent_dialer import start_dialer, stop_dialer
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
    credits_per_minute: float | None = None
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
    rows = await pool.fetch("SELECT * FROM webhook_configs WHERE client_id = $1", client_id)
    return {"webhooks": [dict(r) for r in rows]}


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
    if body.active is not None:
        sets.append(f"active = ${idx}")
        args.append(body.active)
        idx += 1
    if sets:
        args.append(bot_config_id)
        await pool.execute(f"UPDATE bot_configs SET {', '.join(sets)} WHERE id = ${idx}", *args)
    row = await pool.fetchrow("SELECT * FROM bot_configs WHERE id = $1", bot_config_id)
    return {"bot_config": pg_db.record_to_dict(row) if row else None}


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
    return {
        "total_calls_today": total_calls_today or 0,
        "active_campaigns": active_campaigns or 0,
        "total_credits_used_today": float(total_credits_used_today or 0)
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

"""Client /api/campaigns routes."""

from __future__ import annotations

import importlib
import re
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from typing import Optional

from api.auth import client_id_uuid, get_client_from_token, get_pool
from api.guards import require_campaign_modifiable
from compliance import is_call_allowed, next_compliant_time
from db import postgres as pg_db
from dialer.concurrent_dialer import start_dialer, stop_dialer
from lead_upload.normaliser import normalise_phone
from lead_upload.parser import parse_upload
from lead_upload.validator import validate_dataframe, extract_lead_fields

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

_SCRIPT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _load_script_module(route: str, script_id: str):
    if not _SCRIPT_ID_RE.fullmatch(script_id):
        raise HTTPException(422, "Invalid script_id")
    pkg = "sts_scripts" if route == "sts" else "cascade_scripts"
    try:
        return importlib.import_module(f"{pkg}.{script_id}")
    except ImportError as exc:
        raise HTTPException(500, f"Script not found: {script_id}") from exc


def _col_map(df: pd.DataFrame) -> dict[str, str]:
    return {(c or "").strip().lower(): c for c in df.columns}


async def _get_lead_schema(pool, bot, cid) -> dict:
    if bot.get("script_config_id"):
        cfg = await pg_db.get_script_config(pool, bot["script_config_id"], cid)
        return cfg.get("lead_schema", {"fields": []}) if cfg else {"fields": []}
    else:
        script = _load_script_module(bot["route"], bot["script_id"])
        return getattr(script, "LEAD_SCHEMA", {"fields": []})


@router.get("")
async def list_campaigns(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    search: Optional[str] = Query(None),
):
    cid = client_id_uuid(client)
    campaigns = await pg_db.list_campaigns(pool, cid)
    interested_map = await pg_db.get_campaigns_interested_counts(pool, cid)
    for camp in campaigns:
        camp_id = str(camp.get("id"))
        interested = interested_map.get(camp_id, 0)
        camp["interested_leads"] = interested
        total = int(camp.get("total_leads") or 0)
        camp["conversion_rate"] = round((interested / total) * 100, 2) if total > 0 else None
    if search:
        q = search.lower()
        campaigns = [c for c in campaigns if q in (c.get("name") or "").lower()]
    return {"campaigns": campaigns}

from pydantic import BaseModel, Field

class ClientCreateCampaignBody(BaseModel):
    name: str
    bot_config_id: UUID
    budget_credits: float = Field(ge=0)
    max_concurrent_calls: int = 5
    calls_per_minute: int = 10
    max_attempts: int = 3
    retry_delay_minutes: int = 120
    max_call_minutes: int | None = None

class ClientPatchCampaignBody(BaseModel):
    name: str | None = None
    max_concurrent_calls: int | None = None
    calls_per_minute: int | None = None
    max_attempts: int | None = None
    retry_delay_minutes: int | None = None
    max_call_minutes: int | None = None

@router.get("/{campaign_id}/outcomes")
async def list_campaign_outcomes(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    outcomes = await pg_db.list_campaign_outcomes(
        pool,
        cid,
        campaign_id,
    )

    return {
        "outcomes": outcomes
    }
    
@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
        
    camp = dict(camp)
    bot_record = await pg_db.get_bot_config(pool, UUID(str(camp["bot_config_id"])), cid)
    bot = dict(bot_record) if bot_record else None
    
    lead_schema = {"fields": []}
    if bot:
        try:
            lead_schema = await _get_lead_schema(pool, bot, cid)
        except HTTPException:
            pass
        bot["lead_schema"] = lead_schema
    camp["bot_config"] = bot

    outcome_stats = await pg_db.get_campaign_outcome_stats(pool, cid, campaign_id)
    camp.update(outcome_stats)
    
    return {"stats": camp}


@router.get("/{campaign_id}/calls")
async def list_campaign_calls(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    calls, total_count = await pg_db.list_call_logs(
        pool, cid, limit=limit, offset=offset, search=search, campaign_id=campaign_id
    )
    return {"calls": calls, "total_count": total_count}


@router.post("")
async def create_campaign(
    body: ClientCreateCampaignBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    try:
        campaign_id = await pg_db.create_campaign(
            pool,
            cid,
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

    return {"id": str(campaign_id)}


@router.patch("/{campaign_id}")
async def patch_campaign(
    campaign_id: UUID,
    body: ClientPatchCampaignBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")

    require_campaign_modifiable(camp, allow_paused=True)

    await pg_db.update_campaign_settings(
        pool,
        campaign_id,
        cid,
        name=body.name,
        max_concurrent_calls=body.max_concurrent_calls,
        calls_per_minute=body.calls_per_minute,
        max_attempts=body.max_attempts,
        retry_delay_minutes=body.retry_delay_minutes,
        max_call_minutes=body.max_call_minutes,
    )
    return {"success": True}


@router.post("/{campaign_id}/leads/upload")
async def upload_leads(
    campaign_id: UUID,
    file: UploadFile = File(...),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    campaign = await pg_db.get_campaign(pool, campaign_id, cid)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")

    require_campaign_modifiable(campaign)

    bot = await pg_db.get_bot_config(
        pool, UUID(str(campaign["bot_config_id"])), cid
    )
    if bot is None:
        raise HTTPException(404, "Bot config not found")

    lead_schema = await _get_lead_schema(pool, bot, cid)

    content = await file.read()
    import io

    try:
        df = parse_upload(io.BytesIO(content), file.filename or "upload.csv")
    except (pd.errors.EmptyDataError, pd.errors.ParserError, ValueError):
        raise HTTPException(400, "Uploaded file is empty, malformed, or missing columns")
    errors = validate_dataframe(df, lead_schema)
    if errors:
        raise HTTPException(400, {"errors": errors})

    cmap = _col_map(df)
    phone_col = cmap.get("phone")
    name_col = cmap.get("name")
    lead_type_col = cmap.get("lead_type")

    leads_to_insert: list[dict] = []
    invalid_phones = 0

    for _, row in df.iterrows():
        raw_phone = str(row[phone_col]).strip() if phone_col else ""
        phone = normalise_phone(raw_phone)
        if not phone:
            invalid_phones += 1
            continue

        allowed, reason = is_call_allowed()
        status = "pending"
        next_attempt_at = None
        if not allowed and "window" in reason:
            next_attempt_at = next_compliant_time()

        metadata: dict = {}
        for field in extract_lead_fields(lead_schema):
            key = field.get("key")
            csv_col = field.get("csv_column") or key
            ncol = (csv_col or "").strip().lower()
            if ncol in cmap and key:
                val = row[cmap[ncol]]
                if pd.notna(val) and str(val).strip():
                    metadata[key] = str(val).strip()

        lt = "cold"
        if lead_type_col:
            lt_raw = str(row[lead_type_col]).strip().lower()
            if lt_raw in ("cold", "warm", "hot"):
                lt = lt_raw

        leads_to_insert.append(
            {
                "client_id": cid,
                "campaign_id": campaign_id,
                "phone": phone,
                "name": str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else None,
                "lead_type": lt,
                "status": status,
                "max_attempts": int(campaign.get("max_attempts") or 3),
                "next_attempt_at": next_attempt_at,
                "metadata": metadata,
            }
        )

    inserted = await pg_db.bulk_insert_leads(pool, leads_to_insert)
    duplicates_skipped = len(leads_to_insert) - inserted
    if duplicates_skipped < 0:
        duplicates_skipped = 0

    return {
        "leads_uploaded": inserted,
        "invalid_phones": invalid_phones,
        "duplicates_skipped": max(0, len(leads_to_insert) - inserted - invalid_phones),
    }


from fastapi.responses import PlainTextResponse

@router.get("/{campaign_id}/leads/template", response_class=PlainTextResponse)
async def get_lead_template(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    campaign = await pg_db.get_campaign(pool, campaign_id, cid)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")

    bot = await pg_db.get_bot_config(
        pool, UUID(str(campaign["bot_config_id"])), cid
    )
    if bot is None:
        raise HTTPException(404, "Bot config not found")

    try:
        lead_schema = await _get_lead_schema(pool, bot, cid)
    except HTTPException:
        lead_schema = {"fields": []}
    
    headers = ["phone", "name"]
    for field in extract_lead_fields(lead_schema):
        csv_col = field.get("csv_column") or field.get("key")
        if csv_col and csv_col.lower() not in ("phone", "name", "lead_phone", "lead_name"):
            headers.append(csv_col)
            
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    
    return PlainTextResponse(
        content=output.getvalue(),
        headers={
            "Content-Disposition": f'attachment; filename="template_{bot["script_id"]}.csv"'
        }
    )


@router.patch("/{campaign_id}/start")
async def start_campaign(
    campaign_id: UUID,
    request: Request,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")

    if camp["status"] not in ("draft", "paused", "pausing"):
        raise HTTPException(409, f"Cannot start a {camp['status']} campaign")

    budget = float(camp.get("budget_credits") or 0)
    used = float(camp.get("budget_used_credits") or 0)
    if budget - used < 2:
        raise HTTPException(400, "Campaign has insufficient remaining budget to start")

    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, cid)
    bumped_retry = await pg_db.bump_pending_retry_to_now(pool, campaign_id, cid)
    counter_snapshot = await pg_db.reconcile_campaign_counters(
        pool, campaign_id, cid
    )
    await pg_db.update_campaign_status(pool, campaign_id, cid, "running")
    import os

    host = (os.getenv("DIALER_CALLBACK_HOST") or os.getenv("NGROK_URL") or "").strip()
    if not host:
        host = request.headers.get("host", "localhost:7860")
    await start_dialer(request.app, campaign_id, cid, host=host)
    return {
        "status": "running",
        "campaign_id": str(campaign_id),
        "released_calling_leads": released,
        "bumped_pending_retry": bumped_retry,
        "counters": counter_snapshot,
    }


@router.patch("/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    if camp["status"] in ("completed", "cancelled"):
        raise HTTPException(
            409,
            f"Campaign already {camp['status']}; cannot cancel again",
        )
    await stop_dialer(campaign_id, cid)
    try:
        result = await pg_db.cancel_campaign(pool, campaign_id, cid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "campaign_id": str(campaign_id),
        **result,
    }


@router.patch("/{campaign_id}/stop")
async def stop_campaign(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    await stop_dialer(campaign_id, cid)
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, cid)
    
    camp_updated = await pg_db.get_campaign(pool, campaign_id, cid)
    calling = int(camp_updated.get("calling_leads") or 0)
    new_status = "pausing" if calling > 0 else "paused"
    
    await pg_db.update_campaign_status(pool, campaign_id, cid, new_status)
    return {
        "status": new_status,
        "campaign_id": str(campaign_id),
        "released_calling_leads": released,
    }


@router.post("/{campaign_id}/release-stuck-calling")
async def release_stuck_calling(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    if camp["status"] not in ("running", "pausing", "paused"):
        raise HTTPException(
            409,
            f"Cannot release stuck leads for a {camp['status']} campaign",
        )
    released = await pg_db.release_stuck_calling_leads(
        pool, campaign_id, cid, ignore_wrap_grace=True
    )
    counters = await pg_db.reconcile_campaign_counters(pool, campaign_id, cid)
    return {
        "campaign_id": str(campaign_id),
        "released": released,
        "counters": counters,
    }

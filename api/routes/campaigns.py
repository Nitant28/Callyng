"""Client /api/campaigns routes."""

from __future__ import annotations

import importlib
import re
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font
from typing import Optional

from api.auth import client_id_uuid, get_client_from_token, get_pool
from api.guards import require_campaign_modifiable
from compliance import is_call_allowed, next_compliant_time
from db import postgres as pg_db
from dialer.concurrent_dialer import start_dialer, stop_dialer
from lead_upload.normaliser import normalise_phone
from lead_upload.parser import parse_upload
from lead_upload.validator import (
    validate_dataframe,
    extract_lead_fields,
    field_display_header,
    _field_header_candidates,
    _normalize_col,
)

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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    cid = client_id_uuid(client)
    campaigns = await pg_db.list_campaigns(pool, cid, limit=limit, offset=offset)
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

    filename = file.filename or "upload.xlsx"
    if not filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(400, "Only CSV and Excel (.xlsx, .csv) files are supported")

    content = await file.read()
    import io

    try:
        df = parse_upload(io.BytesIO(content), filename)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as exc:
        raise HTTPException(400, str(exc) or "Uploaded file is empty, malformed, or missing columns")
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

        # Schema is the single source of truth — only store schema fields
        metadata: dict = {}
        for field in extract_lead_fields(lead_schema):
            key = field.get("key")
            if not key:
                continue
            matched_col = None
            for cand in _field_header_candidates(field):
                ncol = _normalize_col(cand)
                if ncol in ("phone", "name", "lead_phone", "lead_name", "lead_type"):
                    continue
                if ncol in cmap:
                    matched_col = cmap[ncol]
                    break
            if matched_col is None:
                continue
            val = row[matched_col]
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


@router.get("/{campaign_id}/leads/template")
async def get_lead_template(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Download Excel template generated from the campaign Lead Schema."""
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

    headers = ["Name", "Phone"]
    example = ["Rahul Patil", "+919876543210"]
    required_notes: list[str] = ["Name", "Phone"]
    fields = extract_lead_fields(lead_schema)

    for field in fields:
        key = (field.get("key") or "").strip().lower()
        header = field_display_header(field)
        if key in ("phone", "name", "lead_phone", "lead_name", "lead_type") or header.lower() in (
            "phone", "name", "lead_phone", "lead_name", "lead_type",
        ):
            continue
        headers.append(header)
        ftype = (field.get("type") or "text").lower()
        if ftype == "number":
            example.append("3500000")
        elif ftype == "dropdown" and field.get("options"):
            example.append(str(field["options"][0]))
        else:
            example.append(field.get("placeholder") or f"Example {header}")
        if field.get("required"):
            required_notes.append(header)

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.append(example)

    # Phone column as text so +91… is preserved
    phone_idx = headers.index("Phone") + 1
    phone_letter = ws.cell(row=1, column=phone_idx).column_letter
    for cell in ws[phone_letter]:
        cell.number_format = "@"

    instr = wb.create_sheet("Instructions")
    instr.append(["Lead Import Instructions"])
    instr["A1"].font = Font(bold=True, size=14)
    instr.append([])
    instr.append(["Required fields"])
    instr["A3"].font = Font(bold=True)
    for name in required_notes:
        instr.append([name])
    instr.append([])
    instr.append(["Phone format"])
    instr["A" + str(instr.max_row)].font = Font(bold=True)
    instr.append(["Include country code, e.g. +919876543210"])
    instr.append([])
    instr.append(["Lead Type (optional column)"])
    instr["A" + str(instr.max_row)].font = Font(bold=True)
    instr.append(["Accepted values: cold, warm, hot"])
    instr.append([])
    instr.append(["Field details"])
    instr["A" + str(instr.max_row)].font = Font(bold=True)
    instr.append(["Label", "Key", "Type", "Required", "Accepted values"])
    for cell in instr[instr.max_row]:
        cell.font = Font(bold=True)
    for field in fields:
        key = (field.get("key") or "").strip().lower()
        header = field_display_header(field)
        if key in ("phone", "name", "lead_phone", "lead_name", "lead_type") or header.lower() in (
            "phone", "name", "lead_phone", "lead_name", "lead_type",
        ):
            continue
        opts = ""
        if (field.get("type") or "").lower() == "dropdown" and field.get("options"):
            opts = ", ".join(str(o) for o in field["options"])
        instr.append([
            header,
            field.get("key") or "",
            field.get("type") or "text",
            "Yes" if field.get("required") else "No",
            opts,
        ])
    instr.append([])
    instr.append(["Example row"])
    instr["A" + str(instr.max_row)].font = Font(bold=True)
    instr.append(headers)
    instr.append(example)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    script_id = bot.get("script_id") or "leads"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="template_{script_id}.xlsx"'
        },
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


@router.delete("/{campaign_id}")
async def delete_campaign_route(
    campaign_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    await stop_dialer(campaign_id, cid)
    try:
        result = await pg_db.delete_campaign(pool, campaign_id, cid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


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

"""Admin /internal/script-configs routes."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import get_pool, require_admin
from api.script_config_validation import (
    default_template,
    normalize_script_config_payload,
    validate_script_config_payload,
)
from db import postgres as pg_db
from post_call_extract import extract_post_call, normalize_post_call_extraction

router = APIRouter(prefix="/internal", tags=["internal"])


class CreateScriptConfigBody(BaseModel):
    client_id: UUID
    script_id: str
    route: str
    system_instruction_template: str
    extraction_schema: dict[str, Any]
    gemini_model: str = "models/gemini-3.1-flash-live-preview"
    gemini_voice: str = "Aoede"
    gemini_language: str = "hi-IN"
    gemini_temperature: float = 0.5
    vad_start_sensitivity: str = "HIGH"
    vad_end_sensitivity: str = "LOW"
    vad_silence_duration_ms: int = 800
    vad_prefix_padding_ms: int = 300
    bootstrap_messages_json: list[Any] = Field(default_factory=list)
    goodbye_markers: list[Any] = Field(default_factory=list)
    cascade_stt_provider: str = "sarvam"
    cascade_stt_model: str = "saarika:v2.5"
    cascade_llm_provider: str = "groq"
    cascade_llm_model: str = "llama-3.3-70b-versatile"
    cascade_tts_provider: str = "cartesia"
    cascade_tts_voice: str = "sonic-3"
    cascade_live_tools: list[Any] = Field(default_factory=list)
    lead_schema: dict[str, Any] = Field(default_factory=lambda: {"fields": []})
    normalization_rules: list[Any] = Field(default_factory=list)
    outcome_event_map: dict[str, str] = Field(default_factory=dict)
    outcome_terminal: list[str] = Field(
        default_factory=lambda: ["Interested", "Not_Interested"]
    )
    outcome_retry: list[str] = Field(
        default_factory=lambda: ["Busy", "Unknown", "Wrong_Requirement"]
    )
    outcome_callback: list[str] = Field(
        default_factory=lambda: ["Callback_Requested"]
    )
    active: bool = True


class PatchScriptConfigBody(BaseModel):
    script_id: str | None = None
    route: str | None = None
    system_instruction_template: str | None = None
    extraction_schema: dict[str, Any] | None = None
    gemini_model: str | None = None
    gemini_voice: str | None = None
    gemini_language: str | None = None
    gemini_temperature: float | None = None
    vad_start_sensitivity: str | None = None
    vad_end_sensitivity: str | None = None
    vad_silence_duration_ms: int | None = None
    vad_prefix_padding_ms: int | None = None
    bootstrap_messages_json: list[Any] | None = None
    goodbye_markers: list[Any] | None = None
    cascade_stt_provider: str | None = None
    cascade_stt_model: str | None = None
    cascade_llm_provider: str | None = None
    cascade_llm_model: str | None = None
    cascade_tts_provider: str | None = None
    cascade_tts_voice: str | None = None
    cascade_live_tools: list[Any] | None = None
    lead_schema: dict[str, Any] | None = None
    normalization_rules: list[Any] | None = None
    outcome_event_map: dict[str, str] | None = None
    outcome_terminal: list[str] | None = None
    outcome_retry: list[str] | None = None
    outcome_callback: list[str] | None = None
    active: bool | None = None


class RollbackBody(BaseModel):
    version: int = Field(ge=1)


class TestScriptConfigBody(BaseModel):
    transcript: list[dict[str, Any]]
    extraction_schema: dict[str, Any] | None = None
    normalization_rules: list[Any] | None = None


class DialTestBody(BaseModel):
    phone: str
    telephony_number: str
    lead_name: str = "Test Lead"
    metadata: dict[str, Any] = Field(default_factory=dict)


def _validation_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "already exists" in msg:
        return HTTPException(409, msg)
    if "not found" in msg:
        return HTTPException(404, msg)
    return HTTPException(422, msg)


def _merged_for_validation(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    merged.update(patch)
    return merged


@router.get("/script-configs/template")
async def get_script_config_template(
    route: str = Query(..., pattern="^(sts|cascaded)$"),
    _: None = Depends(require_admin),
):
    try:
        template = default_template(route)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"template": template, "route": route}


@router.get("/script-configs")
async def list_script_configs(
    client_id: UUID | None = Query(None),
    active_only: bool = Query(True),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    rows = await pg_db.list_script_configs(
        pool, client_id, active_only=active_only
    )
    # Hide seeded CLI sandboxes from the UI
    rows = [r for r in rows if not r.get("script_id", "").startswith("cli_sandbox")]
    return {"script_configs": rows}


@router.get("/script-configs/{script_config_id}")
async def get_script_config(
    script_config_id: UUID,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    row = await pg_db.get_script_config_admin(
        pool, script_config_id, client_id, active_only=False
    )
    if row is None:
        raise HTTPException(404, "script_config not found")
    return {"script_config": row}


@router.post("/script-configs")
async def create_script_config(
    body: CreateScriptConfigBody,
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    data = body.model_dump()
    try:
        validate_script_config_payload(data, partial=False)
        row = await pg_db.create_script_config(pool, body.client_id, data)
    except ValueError as exc:
        raise _validation_error(exc) from exc
    return {"script_config": row}


@router.patch("/script-configs/{script_config_id}")
async def patch_script_config(
    script_config_id: UUID,
    body: PatchScriptConfigBody,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    patch = normalize_script_config_payload(body.model_dump(exclude_unset=True))
    if not patch:
        raise HTTPException(422, "empty patch")

    current = await pg_db.get_script_config_admin(
        pool, script_config_id, client_id, active_only=False
    )
    if current is None:
        raise HTTPException(404, "script_config not found")

    merged = _merged_for_validation(current, patch)
    try:
        validate_script_config_payload(merged, partial=False)
        row = await pg_db.update_script_config(
            pool, script_config_id, client_id, patch
        )
    except ValueError as exc:
        raise _validation_error(exc) from exc
    return {"script_config": row}


@router.get("/script-configs/{script_config_id}/revisions")
async def get_script_config_revisions(
    script_config_id: UUID,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    current = await pg_db.get_script_config_admin(
        pool, script_config_id, client_id, active_only=False
    )
    if current is None:
        raise HTTPException(404, "script_config not found")
    revisions = await pg_db.list_script_config_revisions(
        pool, script_config_id, client_id
    )
    return {"revisions": revisions}


@router.post("/script-configs/{script_config_id}/rollback")
async def rollback_script_config(
    script_config_id: UUID,
    body: RollbackBody,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        row = await pg_db.rollback_script_config(
            pool, script_config_id, client_id, body.version
        )
    except ValueError as exc:
        raise _validation_error(exc) from exc
    return {"script_config": row, "rolled_back_from_version": body.version}


@router.post("/script-configs/{script_config_id}/test")
async def test_script_config_extraction(
    script_config_id: UUID,
    body: TestScriptConfigBody,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    if not body.transcript:
        raise HTTPException(422, "transcript must be non-empty")

    row = await pg_db.get_script_config(pool, script_config_id, client_id)
    if row is None:
        raise HTTPException(404, "script_config not found or inactive")

    schema = body.extraction_schema or row.get("extraction_schema")
    rules = body.normalization_rules
    if rules is None:
        raw_rules = row.get("normalization_rules") or []
        rules = raw_rules if raw_rules else None

    if not (os.getenv("GROQ_API_KEY") or "").strip():
        raise HTTPException(503, "GROQ_API_KEY not configured")

    try:
        validate_script_config_payload(
            {
                **row,
                "extraction_schema": schema,
                "outcome_terminal": row.get("outcome_terminal"),
                "outcome_retry": row.get("outcome_retry"),
                "outcome_callback": row.get("outcome_callback"),
            },
            partial=False,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    parsed, err, model = await extract_post_call(
        body.transcript, extraction_schema=schema
    )
    normalized = None
    if parsed is not None and err is None:
        normalized = normalize_post_call_extraction(
            parsed,
            normalization_rules=rules if rules else None,
            transcript=body.transcript,
        )

    return {
        "parsed": parsed,
        "normalized": normalized,
        "error": err,
        "model": model,
    }


@router.post("/script-configs/{script_config_id}/dial-test")
async def dial_test_script_config(
    script_config_id: UUID,
    body: DialTestBody,
    request: Request,
    client_id: UUID = Query(...),
    _: None = Depends(require_admin),
    pool=Depends(get_pool),
):
    import aiohttp
    from uuid import uuid4
    from dialer.concurrent_dialer import fire_call, _release_lead_to_pending
    
    for key in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "PLIVO_PHONE_NUMBER"):
        if not (os.getenv(key) or "").strip():
            raise HTTPException(503, f"{key} is not configured in .env")

    row = await pg_db.get_script_config(pool, script_config_id, client_id)
    if row is None:
        raise HTTPException(404, "script_config not found or inactive")
        
    route = row.get("route")
    
    bot_config = {
        "id": None,
        "client_id": client_id,
        "name": "[Ephemeral Test Bot]",
        "route": route,
        "script_id": str(row.get("script_id")),
        "script_config_id": script_config_id,
        "telephony_number": body.telephony_number,
    }

    campaign = {
        "id": None,
        "client_id": client_id,
        "bot_config_id": None,
        "name": "[Ephemeral Test Campaign]",
        "status": "running",
        "max_call_minutes": 60,
        "extraction_schema_override": None,
    }

    meta = dict(body.metadata)
    meta["real_phone"] = body.phone
    synthetic_phone = f"+cli{uuid4().hex[:12]}"
    
    lead = {
        "id": None,
        "client_id": client_id,
        "campaign_id": None,
        "phone": synthetic_phone,
        "name": f"[TEST CALL] {body.lead_name}",
        "metadata": meta,
        "status": "calling",
    }
    
    campaign_uuid = None
    
    host = (os.getenv("DIALER_CALLBACK_HOST") or os.getenv("NGROK_URL") or "").strip()
    if not host:
        host = request.headers.get("host", "localhost:7860")
        
    session_call_id = None
    try:
        async with aiohttp.ClientSession() as session:
            session_call_id = await fire_call(
                session, lead, campaign, bot_config,
                host=host, pool=pool, client_id=client_id, campaign_id=campaign_uuid, dial_phone=body.phone,
                is_test_call=True
            )
    except Exception as exc:
        if lead.get("id"):
            await _release_lead_to_pending(pool, lead, campaign_uuid, client_id)
        raise HTTPException(500, f"Dial failed: {exc}")
        
    if not session_call_id:
        if lead.get("id"):
            await _release_lead_to_pending(pool, lead, campaign_uuid, client_id)
        raise HTTPException(500, "Call was skipped (duplicate guard?)")
        
    return {"session_call_id": session_call_id, "message": "Test call dispatched successfully"}

"""Client /api/events routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import client_id_uuid, get_client_from_token, get_pool
from dialer.concurrent_dialer import start_event_dialer
from db import postgres as pg_db


router = APIRouter(prefix="/api/events", tags=["events"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class PatchOutcomeMappingBody(BaseModel):
    outcome: str | None = None
    bot_config_id: UUID | None = None

class CreateEventLeadBody(BaseModel):
    phone: str
    name: str | None = None
    email: str | None = None
    metadata: dict | None = None

class EditEventLeadBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    status: str | None = None
# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@router.get("")
async def list_events(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    cid = client_id_uuid(client)

    events, total_count = await pg_db.list_events(
        pool,
        cid,
        limit=limit,
        offset=offset,
    )

    if search:
        q = search.strip().lower()
        events = [
            event
            for event in events
            if q in (event.get("name") or "").lower()
        ]

    return {
        "events": events,
        "total_count": total_count,
    }



@router.get("/{event_id}")
async def get_event(
    event_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    return {
        "event": event,
    }


@router.patch("/{event_id}")
async def patch_event(
    event_id: UUID,
    body: PatchEventBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        updated_event = await pg_db.update_event(
            pool,
            event_id,
            cid,
            name=body.name,
            description=body.description,
            source_type=body.source_type,
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

    if updated_event is None:
        raise HTTPException(404, "Event not found")

    return {
        "event": updated_event,
    }


@router.delete("/{event_id}")
async def delete_event(
    event_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        deleted = await pg_db.delete_event(
            pool,
            event_id,
            cid,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not deleted:
        raise HTTPException(404, "Event not found")

    return {
        "success": True,
        "event_id": str(event_id),
    }


# ---------------------------------------------------------------------------
# Event outcome -> bot mappings
# ---------------------------------------------------------------------------



@router.get("/{event_id}/outcomes")
async def list_event_outcomes(
    event_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    outcomes = await pg_db.list_event_outcome_bot_mappings(
        pool,
        event_id,
    )

    return {
        "outcomes": outcomes,
    }


@router.post("/{event_id}/outcomes")
async def create_event_outcome(
    event_id: UUID,
    body: CreateOutcomeMappingBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

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


@router.patch("/{event_id}/outcomes/{mapping_id}")
async def patch_event_outcome(
    event_id: UUID,
    mapping_id: UUID,
    body: PatchOutcomeMappingBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        result = await pg_db.update_event_outcome_bot_mapping(
            pool,
            mapping_id,
            event_id,
            outcome=body.outcome,
            bot_config_id=body.bot_config_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if result is None:
        raise HTTPException(404, "Outcome mapping not found")

    return {
        "mapping": result,
    }


@router.delete("/{event_id}/outcomes/{mapping_id}")
async def delete_event_outcome(
    event_id: UUID,
    mapping_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        deleted = await pg_db.delete_event_outcome_bot_mapping(
            pool,
            mapping_id,
            event_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not deleted:
        raise HTTPException(404, "Outcome mapping not found")

    return {
        "success": True,
        "mapping_id": str(mapping_id),
    }


# ---------------------------------------------------------------------------
# Event leads
# ---------------------------------------------------------------------------
@router.post("/{event_id}/leads")
async def create_event_lead(
    event_id: UUID,
    body: CreateEventLeadBody,
    request: Request,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        lead = await pg_db.create_event_lead(
            pool,
            cid,
            event_id,
            body.phone,
            name=body.name,
            email=body.email,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    await start_event_dialer(request.app, event_id, cid)

    return {
        "lead": lead,
    }

@router.patch("/{event_id}/leads/{lead_id}")
async def update_event_lead(
    event_id: UUID,
    lead_id: UUID,
    body: EditEventLeadBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    lead = await pg_db.get_event_lead(
        pool,
        event_id,
        lead_id,
    )

    if lead is None:
        raise HTTPException(404, "Event lead not found")

    updated = await pg_db.update_event_lead(
        pool,
        lead_id,
        event_id,
        cid,
        name=body.name,
        phone=body.phone,
        status=body.status,
    )

    if not updated:
        raise HTTPException(404, "Event lead not found")

    return {
        "message": "Event lead updated successfully",
        "lead_id": str(lead_id),
    }

@router.get("/{event_id}/leads")
async def list_event_leads(
    event_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    leads, total_count = await pg_db.list_event_leads(
        pool,
        event_id,
        limit=limit,
        offset=offset,
    )

    return {
        "leads": leads,
        "total_count": total_count,
    }


@router.get("/{event_id}/leads/{lead_id}")
async def get_event_lead(
    event_id: UUID,
    lead_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    lead = await pg_db.get_event_lead(
        pool,
        event_id,
        lead_id,
    )

    if lead is None:
        raise HTTPException(404, "Lead not found")

    return {
        "lead": lead,
    }


@router.delete("/{event_id}/leads/{lead_id}")
async def delete_event_lead(
    event_id: UUID,
    lead_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    try:
        deleted = await pg_db.delete_event_lead(
            pool,
            event_id,
            lead_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not deleted:
        raise HTTPException(404, "Lead not found")

    return {
        "success": True,
        "event_id": str(event_id),
        "lead_id": str(lead_id),
    }


# ---------------------------------------------------------------------------
# Event lead counts
# ---------------------------------------------------------------------------


@router.get("/{event_id}/lead-counts")
async def event_lead_counts(
    event_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)

    event = await pg_db.get_event(
        pool,
        event_id,
        cid,
    )

    if event is None:
        raise HTTPException(404, "Event not found")

    counts = await pg_db.count_event_leads(
        pool,
        event_id,
    )

    return {
        "counts": counts,
    }
"""Client-wide /api/leads routes (cross-campaign lead sheet)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db
from followups import service as followups_service

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("")
@router.get("/")
async def list_client_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
    campaign_id: UUID | None = None,
    status: str | None = None,
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """List leads across all campaigns for the authenticated client."""
    cid = client_id_uuid(client)
    offset = (page - 1) * limit
    rows, total = await pg_db.list_client_leads(
        pool,
        cid,
        limit=limit,
        offset=offset,
        status=status,
        search=search,
        campaign_id=campaign_id,
        sort=sort,
        order=order,
    )
    pages = max(1, (total + limit - 1) // limit) if limit else 1
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }


@router.get("/stats")
async def client_lead_stats(
    campaign_id: UUID | None = None,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """KPI counters for the lead sheet stats strip."""
    cid = client_id_uuid(client)
    stats = await pg_db.get_client_lead_stats(pool, cid, campaign_id=campaign_id)
    return {"stats": stats}


class ManualFollowUpBody(BaseModel):
    session_call_id: str | None = Field(default=None, max_length=120)


@router.post("/{lead_id}/follow-up")
async def send_lead_follow_up(
    lead_id: UUID,
    body: ManualFollowUpBody | None = None,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Manual follow-up: backend builds payload and POSTs to configured n8n webhook."""
    cid = client_id_uuid(client)
    result = await followups_service.trigger_follow_up(
        pool,
        client_id=cid,
        lead_id=lead_id,
        source="manual",
        session_call_id=(body.session_call_id if body else None),
        require_interested=False,
    )
    if result.get("error") == "lead_not_found":
        raise HTTPException(404, "Lead not found")
    if result.get("error") == "campaign_not_found":
        raise HTTPException(404, "Campaign not found for lead")
    if result.get("error") == "missing_phone":
        raise HTTPException(400, "Lead has no valid phone number")
    if result.get("error") == "n8n_not_configured":
        raise HTTPException(503, "n8n webhook is not configured")
    if not result.get("ok") and not result.get("deduplicated"):
        raise HTTPException(502, result.get("error") or "Follow-up failed")
    return result


@router.get("/{lead_id}/follow-ups")
async def list_lead_follow_ups(
    lead_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Follow-up history for a lead (scoped to authenticated client)."""
    cid = client_id_uuid(client)
    lead = await pg_db.get_lead(pool, lead_id, cid)
    if not lead:
        raise HTTPException(404, "Lead not found")
    events = await followups_service.list_history(pool, cid, lead_id)
    return {"lead_id": str(lead_id), "events": events, "total": len(events)}

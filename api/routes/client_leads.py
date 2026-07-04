"""Client-wide /api/leads routes (cross-campaign lead sheet)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db

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

"""Admin follow-up retry / status endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_pool, require_admin
from followups import repository as followups_repo
from followups.service import trigger_follow_up

router = APIRouter(prefix="/internal/followups", tags=["internal-followups"])


class RetryFollowUpBody(BaseModel):
    client_id: UUID
    lead_id: UUID
    source: str = Field(default="manual_retry", max_length=40)


@router.post("/retry")
async def retry_follow_up(body: RetryFollowUpBody, _admin=Depends(require_admin), pool=Depends(get_pool)):
    result = await trigger_follow_up(
        pool,
        client_id=body.client_id,
        lead_id=body.lead_id,
        source=body.source,
        require_interested=False,
    )
    if not result.get("ok") and not result.get("deduplicated"):
        raise HTTPException(400, result.get("error") or "follow_up_failed")
    return result


@router.get("/lead/{lead_id}")
async def list_lead_followups(
    lead_id: UUID,
    client_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    rows = await followups_repo.list_for_lead(pool, client_id, lead_id)
    return {"items": rows}

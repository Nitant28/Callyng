"""Client /api/calls routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("")
async def list_calls(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    limit: int = 50,
    offset: int = 0,
):
    cid = client_id_uuid(client)
    calls, total_count = await pg_db.list_call_logs(pool, cid, limit=limit, offset=offset)
    return {"calls": calls, "total_count": total_count}


@router.get("/{session_call_id}")
async def get_call(
    session_call_id: str,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    row = await pg_db.get_call_log(pool, session_call_id, cid)
    
    # Fallback if session_call_id is actually a lead_id
    if row is None:
        try:
            lead_uuid = UUID(session_call_id)
            row = await pg_db.get_latest_call_log_for_lead(pool, lead_uuid, cid)
        except ValueError:
            pass

    if row is None:
        raise HTTPException(404, "Call not found")
        
    return {"calls": [row]}

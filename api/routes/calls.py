"""Client /api/calls routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import os
from pathlib import Path
from fastapi.responses import FileResponse

from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db
from recording import generate_presigned_url

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("")
async def list_calls(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    cid = client_id_uuid(client)
    calls, total_count = await pg_db.list_call_logs(pool, cid, limit=limit, offset=offset, search=search)
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


@router.get("/{session_call_id}/recording")
async def get_call_recording(
    session_call_id: str,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Generate a presigned URL for the call recording."""
    cid = client_id_uuid(client)
    row = await pg_db.get_call_log(pool, session_call_id, cid)
    if not row:
        raise HTTPException(404, "Call not found")

    recording_key = row.get("recording_url")
    if not recording_key:
        raise HTTPException(404, "No recording available for this call")

    storage = os.getenv("RECORDING_STORAGE", "r2").lower()
    if storage == "local" or recording_key.startswith("local:"):
        # Local dev: serve file directly
        filename = recording_key.removeprefix("local:")
        file_path = Path("./data/recordings") / filename
        if not file_path.exists():
            raise HTTPException(404, "Recording file not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    # Production: presigned R2 URL
    url = generate_presigned_url(recording_key, expires_in=3600)
    return {"url": url, "expires_in": 3600}

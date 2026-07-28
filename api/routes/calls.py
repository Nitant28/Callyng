"""Client /api/calls routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pathlib import Path
from fastapi.responses import FileResponse, StreamingResponse
import aiohttp

from loguru import logger
from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db
from recording import resolve_recording_url

router = APIRouter(prefix="/api/calls", tags=["calls"])


async def _resolve_call_log(pool, session_call_id: str, client_id: UUID) -> dict | None:
    """Look up a call log by session_call_id, falling back to latest log for a lead_id."""
    row = await pg_db.get_call_log(pool, session_call_id, client_id)
    if row is None:
        try:
            lead_uuid = UUID(session_call_id)
            row = await pg_db.get_latest_call_log_for_lead(pool, lead_uuid, client_id)
        except ValueError:
            pass
    return row


@router.get("")
async def list_calls(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    """
    List calls by recency (stack ordering for running calls is handled on the frontend).
    Default limit is 100; heavy JSONB fields are omitted from list rows.
    """
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
    row = await _resolve_call_log(pool, session_call_id, cid)
    if row is None:
        raise HTTPException(404, "Call not found")
    return dict(row)


@router.get("/{session_call_id}/recording")
async def get_call_recording(
    session_call_id: str,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Return a playable URL for the call recording."""
    cid = client_id_uuid(client)
    row = await _resolve_call_log(pool, session_call_id, cid)
    if not row:
        raise HTTPException(404, "Call not found")

    recording_key = row.get("recording_url")
    if not recording_key:
        raise HTTPException(404, "No recording available for this call")

    # Local dev: serve file directly
    if recording_key.startswith("local:"):
        filename = recording_key.removeprefix("local:")
        file_path = Path("./data/recordings") / filename
        if not file_path.exists():
            raise HTTPException(404, "Recording file not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    # Plivo-hosted or legacy R2 key — resolve_recording_url handles both
    url = resolve_recording_url(recording_key, expires_in=3600)
    return {"url": url, "expires_in": 3600}

@router.get("/{session_call_id}/recording/play")
async def play_call_recording(
    session_call_id: str,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Securely proxy the call recording audio stream."""
    cid = client_id_uuid(client)
    row = await _resolve_call_log(pool, session_call_id, cid)
    if not row:
        raise HTTPException(404, "Call not found")

    recording_key = row.get("recording_url")
    if not recording_key:
        raise HTTPException(404, "No recording available for this call")

    if recording_key.startswith("local:"):
        filename = recording_key.removeprefix("local:")
        file_path = Path("./data/recordings") / filename
        if not file_path.exists():
            raise HTTPException(404, "Recording file not found")
        return FileResponse(file_path, media_type="audio/mpeg")

    if recording_key.startswith("plivo:"):
        plivo_url = recording_key.removeprefix("plivo:")
        from telephony import _plivo_auth
        auth_id, auth_token = _plivo_auth()
        auth = aiohttp.BasicAuth(auth_id, auth_token)

        async def stream_audio():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(plivo_url, auth=auth) as resp:
                        if resp.status != 200:
                            raise HTTPException(resp.status, "Failed to fetch recording from provider")
                        async for chunk in resp.content.iter_chunked(8192):
                            yield chunk
            except aiohttp.ClientConnectorError as exc:
                logger.warning("recording stream connect failed: {}", exc)
                raise HTTPException(503, "Recording provider temporarily unreachable") from exc

        return StreamingResponse(stream_audio(), media_type="audio/mpeg")

    # Legacy R2 key
    from fastapi.responses import RedirectResponse
    url = resolve_recording_url(recording_key, expires_in=3600)
    return RedirectResponse(url)

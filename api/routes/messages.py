"""Client Messages API — tenant-scoped WhatsApp conversation views."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import client_id_uuid, get_client_from_token, get_pool
from messages import service as messages_service

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("/conversations")
async def list_conversations(
    search: str | None = None,
    campaign_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    rows, total = await messages_service.list_client_conversations(
        pool, cid, search=search, campaign_id=campaign_id, limit=limit, offset=offset
    )
    return {"conversations": rows, "total_count": total, "limit": limit, "offset": offset}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    conv, messages = await messages_service.get_client_conversation_thread(
        pool, cid, conversation_id, limit=limit, offset=offset
    )
    if not conv:
        raise HTTPException(404, "conversation not found")
    return {
        "conversation": conv,
        "messages": messages,
        "limit": limit,
        "offset": offset,
        "has_more": len(messages) >= limit,
    }


@router.get("/templates")
async def list_templates(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    cid = client_id_uuid(client)
    templates = await messages_service.list_client_templates(pool, cid)
    return {"templates": templates}


@router.get("/integrations")
async def list_integrations(
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Public integration status only — never returns credentials."""
    cid = client_id_uuid(client)
    return {"integrations": await messages_service.list_client_integrations(pool, cid)}

"""Client /api/credits route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import get_client_from_token

router = APIRouter(prefix="/api/credits", tags=["credits"])


@router.get("")
async def get_credits(client: dict = Depends(get_client_from_token)):
    return {
        "balance_credits": float(client.get("balance_credits") or 0),
        "max_concurrent_calls": int(client.get("max_concurrent_calls") or 5),
        "client_name": client.get("name", "Client"),
        "client_id": str(client.get("id") or ""),
    }

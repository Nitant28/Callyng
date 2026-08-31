"""Authentication dependencies for admin and client routes."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Annotated
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Header, HTTPException, Request

from db import postgres as pg_db

load_dotenv(override=True)


def n8n_callback_token() -> str | None:
    """Stable token n8n can pass as ?token= so Code nodes never need $env."""
    secret = (
        (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
        or (os.getenv("ADMIN_API_KEY") or "").strip()
    )
    if not secret:
        return None
    return hashlib.sha256(f"record::{secret}".encode("utf-8")).hexdigest()


async def require_admin(
    request: Request,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    expected = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(503, "ADMIN_API_KEY not configured")
    provided = (x_admin_key or request.headers.get("x-admin-key") or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(403, "Invalid or missing admin key")


async def require_admin_or_n8n_token(
    request: Request,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Admin key, or the same record token embedded in aakashvani.context_url."""
    expected_admin = (os.getenv("ADMIN_API_KEY") or "").strip()
    provided_key = (x_admin_key or request.headers.get("x-admin-key") or "").strip()
    if expected_admin and provided_key and hmac.compare_digest(provided_key, expected_admin):
        return
    token = (
        (request.query_params.get("token") or "").strip()
        or (request.headers.get("X-Aakashvani-Record-Token") or "").strip()
    )
    expected_token = n8n_callback_token()
    if expected_token and token and hmac.compare_digest(token, expected_token):
        return
    raise HTTPException(403, "Invalid or missing admin key")


def _pool_from_request(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "PostgreSQL not available")
    return pool


async def get_client_from_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "Empty Bearer token")

    admin_key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if admin_key and token == admin_key:
        raise HTTPException(403, "Admin key cannot be used on client routes")

    pool = _pool_from_request(request)
    client = await pg_db.get_client_by_token(pool, token)
    if client is None:
        raise HTTPException(401, "Invalid API key")
    return client


async def get_pool(request: Request):
    return _pool_from_request(request)


def client_id_uuid(client: dict) -> UUID:
    return UUID(str(client["id"]))

"""Persistence for follow-up events and integration settings."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from asyncpg.exceptions import UniqueViolationError

from db.postgres import record_to_dict, records_to_dicts


async def insert_event(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    campaign_id: UUID | None,
    lead_id: UUID | None,
    channel: str,
    direction: str,
    status: str,
    source: str,
    message_preview: str | None,
    idempotency_key: str | None,
    session_call_id: str | None = None,
    error: str | None = None,
) -> dict | None:
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO follow_up_events (
                client_id, campaign_id, lead_id, channel, direction, status, source,
                message_preview, idempotency_key, session_call_id, error
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING *
            """,
            client_id,
            campaign_id,
            lead_id,
            channel,
            direction,
            status,
            source,
            message_preview,
            idempotency_key,
            session_call_id,
            error,
        )
        return record_to_dict(row)
    except UniqueViolationError:
        if not idempotency_key:
            raise
        existing = await pool.fetchrow(
            """
            SELECT * FROM follow_up_events
            WHERE client_id = $1 AND idempotency_key = $2
            """,
            client_id,
            idempotency_key,
        )
        return record_to_dict(existing) if existing else None


async def get_by_idempotency(pool: asyncpg.Pool, client_id: UUID, key: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM follow_up_events
        WHERE client_id = $1 AND idempotency_key = $2
        """,
        client_id,
        key,
    )
    return record_to_dict(row) if row else None


async def recent_for_lead(
    pool: asyncpg.Pool,
    client_id: UUID,
    lead_id: UUID,
    *,
    within_seconds: int = 90,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM follow_up_events
        WHERE client_id = $1 AND lead_id = $2 AND created_at > NOW() - ($3 || ' seconds')::interval
        ORDER BY created_at DESC
        LIMIT 1
        """,
        client_id,
        lead_id,
        str(int(within_seconds)),
    )
    return record_to_dict(row) if row else None


async def list_for_lead(pool: asyncpg.Pool, client_id: UUID, lead_id: UUID, *, limit: int = 50) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM follow_up_events
        WHERE client_id = $1 AND lead_id = $2
        ORDER BY created_at DESC
        LIMIT $3
        """,
        client_id,
        lead_id,
        limit,
    )
    return records_to_dicts(rows)


class ClaimResult:
    def __init__(self, *, claimed: bool, reason: str | None = None, event: dict | None = None):
        self.claimed = claimed
        self.reason = reason
        self.event = event


async def claim_dispatch(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    campaign_id: UUID | None,
    lead_id: UUID,
    channel: str,
    source: str,
    idempotency_key: str,
    session_call_id: str | None = None,
    message_preview: str | None = None,
) -> ClaimResult:
    """Atomically claim an outbound follow-up dispatch slot."""
    existing = await get_by_idempotency(pool, client_id, idempotency_key)
    if existing:
        return ClaimResult(claimed=False, reason="already_dispatched", event=existing)
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO follow_up_events (
                client_id, campaign_id, lead_id, channel, direction, status, source,
                message_preview, idempotency_key, session_call_id, error
            ) VALUES ($1,$2,$3,$4,'outgoing','queued',$5,$6,$7,$8,NULL)
            RETURNING *
            """,
            client_id,
            campaign_id,
            lead_id,
            channel,
            source,
            message_preview,
            idempotency_key,
            session_call_id,
        )
        return ClaimResult(claimed=True, event=record_to_dict(row))
    except UniqueViolationError:
        raced = await get_by_idempotency(pool, client_id, idempotency_key)
        return ClaimResult(claimed=False, reason="already_dispatched", event=raced)


# Names used by followups.service — keep both spellings so neither path 404s at runtime.
recent_for_lead = recent_for_lead
get_by_idempotency = get_by_idempotency
list_for_lead = list_for_lead


async def get_setting(pool: asyncpg.Pool, key: str) -> str | None:
    row = await pool.fetchrow("SELECT value FROM integration_settings WHERE key = $1", key)
    return row["value"] if row else None


async def set_setting(pool: asyncpg.Pool, key: str, value: str | None) -> None:
    await pool.execute(
        """
        INSERT INTO integration_settings (key, value, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        key,
        value,
    )

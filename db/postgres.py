"""PostgreSQL connection pool and multi-tenant query helpers."""

from __future__ import annotations

import hashlib
import os
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

_pool: asyncpg.Pool | None = None


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def database_url() -> str | None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    return url or None


async def init_pool() -> asyncpg.Pool | None:
    """Create the global asyncpg pool. Returns None if DATABASE_URL is unset."""
    global _pool
    dsn = database_url()
    if not dsn:
        return None
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=5,
        max_size=20,
        command_timeout=30,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized (set DATABASE_URL?)")
    return _pool


async def get_client_by_api_key_hash(api_key_hash: str) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(
        """
        SELECT * FROM clients
        WHERE api_key_hash = $1 AND active = TRUE
        """,
        api_key_hash,
    )


async def get_campaign(campaign_id: UUID | str, client_id: UUID | str) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(
        """
        SELECT * FROM campaigns
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )


async def get_bot_config(bot_config_id: UUID | str, client_id: UUID | str) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(
        """
        SELECT * FROM bot_configs
        WHERE id = $1 AND client_id = $2
        """,
        bot_config_id,
        client_id,
    )


async def allocate_campaign_budget(
    campaign_id: UUID | str,
    client_id: UUID | str,
    budget_credits: Decimal | float,
) -> None:
    """
    Pre-allocate campaign budget from client master balance (atomic).
    Sets campaign status to 'running'.
    """
    amount = Decimal(str(budget_credits))
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT balance_credits FROM clients
                WHERE id = $1 AND active = TRUE
                FOR UPDATE
                """,
                client_id,
            )
            if row is None:
                raise ValueError(f"Client not found: {client_id}")
            balance = Decimal(str(row["balance_credits"]))
            if balance < amount:
                raise ValueError(
                    f"Insufficient balance: have {balance}, need {amount}"
                )
            await conn.execute(
                """
                UPDATE clients
                SET balance_credits = balance_credits - $1
                WHERE id = $2
                """,
                amount,
                client_id,
            )
            updated = await conn.execute(
                """
                UPDATE campaigns
                SET budget_credits = $1,
                    status = 'running'
                WHERE id = $2 AND client_id = $3
                """,
                amount,
                campaign_id,
                client_id,
            )
            if updated.split()[-1] == "0":
                raise ValueError(f"Campaign not found: {campaign_id}")


async def increment_budget_used(
    campaign_id: UUID | str,
    client_id: UUID | str,
    credits_charged: Decimal | float,
) -> None:
    amount = Decimal(str(credits_charged))
    pool = get_pool()
    await pool.execute(
        """
        UPDATE campaigns
        SET budget_used_credits = budget_used_credits + $1
        WHERE id = $2 AND client_id = $3
        """,
        amount,
        campaign_id,
        client_id,
    )


async def return_unused_budget(
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    final_status: str = "completed",
) -> Decimal:
    """
    Return unused campaign budget to client master balance.
    Returns the amount returned.
    """
    if final_status not in ("completed", "cancelled"):
        raise ValueError(f"Invalid final_status: {final_status}")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT budget_credits, budget_used_credits
                FROM campaigns
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
                campaign_id,
                client_id,
            )
            if row is None:
                raise ValueError(f"Campaign not found: {campaign_id}")

            budget = Decimal(str(row["budget_credits"]))
            used = Decimal(str(row["budget_used_credits"]))
            unused = max(budget - used, Decimal("0"))

            if unused > 0:
                await conn.execute(
                    """
                    UPDATE clients
                    SET balance_credits = balance_credits + $1
                    WHERE id = $2
                    """,
                    unused,
                    client_id,
                )

            await conn.execute(
                """
                UPDATE campaigns
                SET status = $1,
                    completed_at = NOW()
                WHERE id = $2 AND client_id = $3
                """,
                final_status,
                campaign_id,
                client_id,
            )
            return unused


async def campaign_budget_remaining(
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> Decimal:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT budget_credits - budget_used_credits AS remaining
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )
    if row is None:
        raise ValueError(f"Campaign not found: {campaign_id}")
    return Decimal(str(row["remaining"]))


def record_to_dict(record: asyncpg.Record | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return dict(record)

"""Campaign budget guard before placing a call."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from db import postgres as pg_db

MIN_REMAINING_CREDITS = pg_db.RESERVE_CREDITS_PER_LEAD


async def check_campaign_budget(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
) -> bool:
    remaining = await pg_db.campaign_budget_remaining(campaign_id, client_id)
    return remaining >= MIN_REMAINING_CREDITS

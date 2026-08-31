"""Campaign budget guard before placing a call."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg

from db import postgres as pg_db


async def check_campaign_budget(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    reserve_amount: Decimal | float | None = None,
) -> bool:
    remaining = await pg_db.campaign_budget_remaining(campaign_id, client_id)
    if reserve_amount is None:
        reserve_amount = await pg_db.campaign_reservation_credits(
            pool, campaign_id, client_id
        )
    r = Decimal(str(reserve_amount or 0))
    if r <= 0:
        return True
    return remaining >= r

"""PostgreSQL connection pool and multi-tenant query helpers."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger

_pool: asyncpg.Pool | None = None


def live_call_grace_minutes() -> int:
    """How long an ``in_progress`` call_log still counts as a live dial."""
    raw = (os.getenv("MAX_CALL_MINUTES") or "10").strip()
    try:
        max_mins = int(raw)
    except ValueError:
        max_mins = 10
    return max(max_mins + 2, 5)


def post_call_wrap_grace_minutes() -> int:
    """After hangup, keep lead non-redialable until post_call updates lead status."""
    raw = (os.getenv("POST_CALL_WRAP_GRACE_MINUTES") or "5").strip()
    try:
        mins = int(raw)
    except ValueError:
        mins = 5
    return max(mins, 1)


async def diagnose_claim_blockers(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> dict[str, Any]:
    """
    Explain why leads with status pending/callback are not claimable.
    Denorm ``pending_leads`` counts all pending rows; claim requires due time + no live log.
    """
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'pending')::int AS pending_total,
            COUNT(*) FILTER (
                WHERE status = 'pending' AND next_attempt_at <= NOW()
            )::int AS pending_due,
            COUNT(*) FILTER (
                WHERE status = 'pending' AND next_attempt_at > NOW()
            )::int AS pending_future,
            COUNT(*) FILTER (WHERE status = 'callback_scheduled')::int AS callback_total,
            COUNT(*) FILTER (
                WHERE status IN ('pending', 'callback_scheduled')
                  AND next_attempt_at <= NOW()
                  AND EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                  )
            )::int AS blocked_live_call_log,
            COUNT(*) FILTER (
                WHERE status IN ('pending', 'callback_scheduled')
                  AND next_attempt_at <= NOW()
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                  )
                  AND EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id
                      AND c.ended_at IS NOT NULL
                      AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                  )
            )::int AS blocked_wrap_up,
            COUNT(*) FILTER (
                WHERE status IN ('pending', 'callback_scheduled')
                  AND next_attempt_at <= NOW()
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id
                      AND c.ended_at IS NOT NULL
                      AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                  )
            )::int AS claimable_now,
            MIN(next_attempt_at) FILTER (
                WHERE status = 'pending' AND next_attempt_at > NOW()
            ) AS next_pending_retry_at
        FROM leads
        WHERE campaign_id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
        grace,
        wrap,
    )
    if row is None:
        return {}
    return dict(row)


async def finalize_stale_in_progress_call_logs(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    grace_minutes: int | None = None,
) -> int:
    """
    Close orphaned ``call_logs`` left ``in_progress`` after pipeline/Plivo end.
    Returns number of rows finalized.
    """
    mins = grace_minutes if grace_minutes is not None else live_call_grace_minutes()
    rows = await pool.fetch(
        """
        UPDATE call_logs SET
            in_progress = FALSE,
            ended_at = COALESCE(ended_at, NOW()),
            outcome = COALESCE(NULLIF(TRIM(outcome), ''), 'Unknown')
        WHERE campaign_id = $1 AND client_id = $2 AND in_progress = TRUE
          AND started_at < NOW() - ($3 * INTERVAL '1 minute')
        RETURNING id
        """,
        campaign_id,
        client_id,
        mins,
    )
    n = len(rows)
    if n:
        logger.warning(
            "Finalized {} stale in_progress call_log(s) for campaign {} "
            "(older than {} min)",
            n,
            campaign_id,
            mins,
        )
    return n


async def finalize_all_stale_in_progress_call_logs(
    pool: asyncpg.Pool,
    *,
    grace_minutes: int | None = None,
) -> int:
    """Close orphaned ``call_logs`` across all campaigns (maintenance sweep)."""
    mins = grace_minutes if grace_minutes is not None else live_call_grace_minutes()
    rows = await pool.fetch(
        """
        UPDATE call_logs SET
            in_progress = FALSE,
            ended_at = COALESCE(ended_at, NOW()),
            outcome = COALESCE(NULLIF(TRIM(outcome), ''), 'Unknown')
        WHERE in_progress = TRUE
          AND started_at < NOW() - ($1 * INTERVAL '1 minute')
        RETURNING id
        """,
        mins,
    )
    n = len(rows)
    if n:
        logger.warning(
            "Finalized {} stale in_progress call_log(s) globally (older than {} min)",
            n,
            mins,
        )
    return n


# Counter deltas: (from_status, to_status) -> column adjustments
_COUNTER_DELTAS: dict[tuple[str, str], dict[str, int]] = {
    ("pending", "calling"): {"calling_leads": 1, "pending_leads": -1},
    ("callback_scheduled", "calling"): {"calling_leads": 1, "callback_leads": -1},
    ("calling", "completed"): {"calling_leads": -1, "completed_leads": 1},
    ("calling", "failed"): {"calling_leads": -1, "failed_leads": 1},
    ("calling", "dnc"): {"calling_leads": -1, "dnc_leads": 1},
    ("calling", "callback_scheduled"): {"calling_leads": -1, "callback_leads": 1},
    ("calling", "pending"): {"calling_leads": -1, "pending_leads": 1},
}

_ALLOWED_COUNTER_COLS = frozenset(
    {
        "total_leads",
        "pending_leads",
        "calling_leads",
        "callback_leads",
        "completed_leads",
        "failed_leads",
        "dnc_leads",
    }
)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def database_url() -> str | None:
    import os

    url = (os.getenv("DATABASE_URL") or "").strip()
    return url or None


async def create_db_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    import os
    if _pool is not None:
        await _pool.close()
        
    min_size = int(os.getenv("DB_POOL_MIN", "5"))
    max_size = int(os.getenv("DB_POOL_MAX", "50"))
    
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
    )
    return _pool


async def init_pool() -> asyncpg.Pool | None:
    """Create the global asyncpg pool. Returns None if DATABASE_URL is unset."""
    dsn = database_url()
    if not dsn:
        return None
    global _pool
    if _pool is not None:
        return _pool
    return await create_db_pool(dsn)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized (set DATABASE_URL?)")
    return _pool


def record_to_dict(record: asyncpg.Record | None) -> dict[str, Any] | None:
    if record is None:
        return None
    out: dict[str, Any] = {}
    for key in record.keys():
        val = record[key]
        if isinstance(val, UUID):
            val = str(val)
        elif isinstance(val, Decimal):
            val = float(val)
        elif isinstance(val, datetime):
            val = val.isoformat()
        out[key] = val
    return out


def records_to_dicts(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [record_to_dict(r) for r in records if record_to_dict(r) is not None]


# ── Clients ───────────────────────────────────────────────────────────────────


async def create_client(
    pool: asyncpg.Pool,
    name: str,
    email: str,
    industry: str,
) -> tuple[UUID, str]:
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)
    row = await pool.fetchrow(
        """
        INSERT INTO clients (name, contact_email, industry, api_key_hash)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        name,
        email,
        industry,
        key_hash,
    )
    return row["id"], raw_key


async def get_client_by_token(pool: asyncpg.Pool, raw_token: str) -> dict | None:
    key_hash = hash_api_key(raw_token.strip())
    row = await pool.fetchrow(
        """
        SELECT * FROM clients
        WHERE api_key_hash = $1 AND active = TRUE
        """,
        key_hash,
    )
    return record_to_dict(row)


async def get_all_clients(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT c.*,
               (SELECT COUNT(*)::int FROM campaigns cam
                WHERE cam.client_id = c.id AND cam.status = 'running') AS active_campaigns,
               (SELECT COUNT(*)::int FROM campaigns cam WHERE cam.client_id = c.id) AS total_campaigns
        FROM clients c
        WHERE c.active = TRUE
        ORDER BY c.created_at DESC
        """
    )
    return records_to_dicts(rows)


async def add_credits(
    pool: asyncpg.Pool,
    client_id: UUID,
    amount: float,
    note: str,
) -> float:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE clients
                SET balance_credits = balance_credits + $1
                WHERE id = $2 AND active = TRUE
                RETURNING balance_credits
                """,
                Decimal(str(amount)),
                client_id,
            )
            if row is None:
                raise ValueError(f"Client not found: {client_id}")
            
            await conn.execute(
                """
                INSERT INTO credit_transactions (client_id, amount, note)
                VALUES ($1, $2, $3)
                """,
                client_id,
                Decimal(str(amount)),
                note,
            )
            return float(row["balance_credits"])


async def get_client(pool: asyncpg.Pool, client_id: UUID) -> dict | None:
    row = await pool.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
    return record_to_dict(row)


async def update_client_status(pool: asyncpg.Pool, client_id: UUID, active: bool) -> None:
    await pool.execute("UPDATE clients SET active = $1 WHERE id = $2", active, client_id)


async def list_credit_transactions(pool: asyncpg.Pool, client_id: UUID) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM credit_transactions WHERE client_id = $1 ORDER BY created_at DESC",
        client_id,
    )
    return records_to_dicts(rows)

# ── Bot configs ───────────────────────────────────────────────────────────────


async def create_bot_config(
    pool: asyncpg.Pool,
    client_id: UUID,
    name: str,
    route: str,
    script_id: str,
    telephony_number: str,
    credits_per_minute: float,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO bot_configs (
            client_id, name, route, script_id, telephony_number, credits_per_minute
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        client_id,
        name,
        route,
        script_id,
        telephony_number,
        Decimal(str(credits_per_minute)),
    )
    return row["id"]


async def get_bot_config(
    pool: asyncpg.Pool,
    bot_config_id: UUID,
    client_id: UUID,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM bot_configs
        WHERE id = $1 AND client_id = $2
        """,
        bot_config_id,
        client_id,
    )
    return record_to_dict(row)


async def list_bot_configs(
    pool: asyncpg.Pool,
    client_id: UUID | None = None,
) -> list[dict]:
    if client_id is None:
        rows = await pool.fetch(
            "SELECT * FROM bot_configs WHERE active = TRUE ORDER BY created_at DESC"
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM bot_configs
            WHERE client_id = $1 AND active = TRUE
            ORDER BY created_at DESC
            """,
            client_id,
        )
    return records_to_dicts(rows)


# ── Campaigns ─────────────────────────────────────────────────────────────────


async def create_campaign(
    pool: asyncpg.Pool,
    client_id: UUID,
    bot_config_id: UUID,
    name: str,
    budget_credits: float,
    max_concurrent_calls: int = 5,
    calls_per_minute: int = 10,
    max_attempts: int = 3,
    retry_delay_minutes: int = 120,
    max_call_minutes: int | None = None,
) -> UUID:
    bot_exists = await pool.fetchval(
        "SELECT 1 FROM bot_configs WHERE id = $1 AND client_id = $2",
        bot_config_id,
        client_id,
    )
    if not bot_exists:
        raise ValueError("Invalid bot_config_id for this client")

    row = await pool.fetchrow(
        """
        INSERT INTO campaigns (
            client_id, bot_config_id, name, budget_credits,
            max_concurrent_calls, calls_per_minute, max_attempts, retry_delay_minutes,
            max_call_minutes, status
        )
        VALUES ($1, $2, $3, 0, $4, $5, $6, $7, $8, 'draft')
        RETURNING id
        """,
        client_id,
        bot_config_id,
        name,
        max_concurrent_calls,
        calls_per_minute,
        max_attempts,
        retry_delay_minutes,
        max_call_minutes,
    )
    campaign_id = row["id"]
    if budget_credits > 0:
        await allocate_campaign_budget(campaign_id, client_id, budget_credits)
    return campaign_id


async def get_campaign(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM campaigns
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )
    return record_to_dict(row)


async def get_all_running_campaigns(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id, client_id, status FROM campaigns WHERE status = 'running'
        """
    )
    return records_to_dicts(rows)


async def get_campaign_admin(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM campaigns WHERE id = $1",
        campaign_id,
    )
    return record_to_dict(row)


async def list_campaigns(pool: asyncpg.Pool, client_id: UUID) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM campaigns
        WHERE client_id = $1
        ORDER BY created_at DESC
        """,
        client_id,
    )
    return records_to_dicts(rows)


async def update_campaign_status(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    status: str,
) -> None:
    await pool.execute(
        """
        UPDATE campaigns SET status = $1
        WHERE id = $2 AND client_id = $3
        """,
        status,
        campaign_id,
        client_id,
    )


async def update_campaign_settings(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    *,
    name: str | None = None,
    max_concurrent_calls: int | None = None,
    calls_per_minute: int | None = None,
    max_attempts: int | None = None,
    retry_delay_minutes: int | None = None,
    max_call_minutes: int | None = None,
) -> None:
    sets: list[str] = []
    args: list[Any] = []
    idx = 1
    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if max_concurrent_calls is not None:
        sets.append(f"max_concurrent_calls = ${idx}")
        args.append(max_concurrent_calls)
        idx += 1
    if calls_per_minute is not None:
        sets.append(f"calls_per_minute = ${idx}")
        args.append(calls_per_minute)
        idx += 1
    if max_attempts is not None:
        sets.append(f"max_attempts = ${idx}")
        args.append(max_attempts)
        idx += 1
    if retry_delay_minutes is not None:
        sets.append(f"retry_delay_minutes = ${idx}")
        args.append(retry_delay_minutes)
        idx += 1
    if max_call_minutes is not None:
        sets.append(f"max_call_minutes = ${idx}")
        args.append(max_call_minutes)
        idx += 1
    if not sets:
        return
    args.extend([campaign_id, client_id])
    sql = f"""
        UPDATE campaigns SET {", ".join(sets)}
        WHERE id = ${idx} AND client_id = ${idx + 1}
    """
    await pool.execute(sql, *args)


async def allocate_campaign_budget(
    campaign_id: UUID | str,
    client_id: UUID | str,
    budget_credits: Decimal | float,
) -> None:
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
                SET budget_credits = budget_credits + $1
                WHERE id = $2 AND client_id = $3
                """,
                amount,
                campaign_id,
                client_id,
            )
            if updated.split()[-1] == "0":
                raise ValueError(f"Campaign not found: {campaign_id}")


async def increment_budget_used(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    credits_charged: Decimal | float,
) -> None:
    amount = Decimal(str(credits_charged))
    await conn.execute(
        """
        UPDATE campaigns
        SET budget_used_credits = budget_used_credits + $1
        WHERE id = $2 AND client_id = $3
        """,
        amount,
        campaign_id,
        client_id,
    )


async def try_settle_campaign_budget(
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    final_status: str = "completed",
    conn: asyncpg.Connection,
) -> tuple[Decimal, bool]:
    """
    Return unused campaign credits to the client once (idempotent via budget_returned_at).
    For ``cancelled``, skips refund while ``calling_leads > 0`` (in-flight calls).
    """
    if final_status not in ("completed", "cancelled"):
        raise ValueError(f"Invalid final_status: {final_status}")

    row = await conn.fetchrow(
        """
        SELECT budget_credits, budget_used_credits, status,
               pending_leads, callback_leads, calling_leads, budget_returned_at
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        FOR UPDATE
        """,
        campaign_id,
        client_id,
    )
    if row is None:
        raise ValueError(f"Campaign not found: {campaign_id}")

    if row["budget_returned_at"] is not None:
        return Decimal("0"), False

    calling = int(row["calling_leads"] or 0)
    if final_status == "cancelled" and calling > 0:
        await conn.execute(
            """
            UPDATE campaigns SET status = 'cancelled'
            WHERE id = $1 AND client_id = $2
              AND status NOT IN ('completed', 'cancelled')
            """,
            campaign_id,
            client_id,
        )
        return Decimal("0"), False

    if final_status == "completed":
        pending = int(row["pending_leads"] or 0)
        callback = int(row["callback_leads"] or 0)
        if pending > 0 or callback > 0 or calling > 0:
            return Decimal("0"), False
        if row["status"] != "running":
            return Decimal("0"), False

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
            completed_at = COALESCE(completed_at, NOW()),
            budget_returned_at = NOW()
        WHERE id = $2 AND client_id = $3
          AND budget_returned_at IS NULL
        """,
        final_status,
        campaign_id,
        client_id,
    )
    just_completed = (final_status == "completed")
    return unused, just_completed


async def maybe_transition_pausing(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> bool:
    """Transition campaign from pausing to paused if calling_leads is 0."""
    row = await conn.fetchrow(
        """
        SELECT status, calling_leads
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        FOR UPDATE
        """,
        campaign_id,
        client_id,
    )
    if row is None:
        return False
    
    if row["status"] == "pausing" and int(row["calling_leads"] or 0) == 0:
        await conn.execute(
            """
            UPDATE campaigns SET status = 'paused'
            WHERE id = $1 AND client_id = $2
            """,
            campaign_id,
            client_id,
        )
        return True
    return False


async def maybe_auto_settle_campaign(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> tuple[Decimal, bool]:
    """Settle when running→completed or cancelled with all dial counters at zero."""
    row = await conn.fetchrow(
        """
        SELECT status, pending_leads, callback_leads, calling_leads, budget_returned_at
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        FOR UPDATE
        """,
        campaign_id,
        client_id,
    )
    if row is None or row["budget_returned_at"] is not None:
        return Decimal("0"), False
    pending = int(row["pending_leads"] or 0)
    callback = int(row["callback_leads"] or 0)
    calling = int(row["calling_leads"] or 0)
    if pending > 0 or callback > 0 or calling > 0:
        return Decimal("0"), False
    status = row["status"]
    if status == "running":
        return await try_settle_campaign_budget(
            campaign_id, client_id, final_status="completed", conn=conn
        )
    if status == "cancelled":
        return await try_settle_campaign_budget(
            campaign_id, client_id, final_status="cancelled", conn=conn
        )
    return Decimal("0"), False


async def return_unused_budget(
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    final_status: str = "completed",
    conn: asyncpg.Connection | None = None,
) -> tuple[Decimal, bool]:
    """Settle campaign budget (wrapper around try_settle_campaign_budget)."""
    if final_status not in ("completed", "cancelled"):
        raise ValueError(f"Invalid final_status: {final_status}")

    async def _run(connection: asyncpg.Connection) -> tuple[Decimal, bool]:
        return await try_settle_campaign_budget(
            campaign_id,
            client_id,
            final_status=final_status,
            conn=connection,
        )

    if conn is not None:
        return await _run(conn)

    pool = get_pool()
    async with pool.acquire() as acquired:
        async with acquired.transaction():
            return await _run(acquired)


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


async def pause_campaign_budget_exhausted(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
) -> None:
    await pool.execute(
        """
        UPDATE campaigns SET status = 'paused'
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )


# ── Leads ─────────────────────────────────────────────────────────────────────


async def bulk_insert_leads(pool: asyncpg.Pool, leads: list[dict]) -> int:
    if not leads:
        return 0
    inserted = 0
    async with pool.acquire() as conn:
        for lead in leads:
            meta = lead.get("metadata") or {}
            if isinstance(meta, dict):
                meta_json = json.dumps(meta, ensure_ascii=False)
            else:
                meta_json = meta
            lead_status = lead.get("status", "pending")
            result = await conn.execute(
                """
                INSERT INTO leads (
                    client_id, campaign_id, phone, name, lead_type,
                    status, max_attempts, next_attempt_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8::jsonb)
                ON CONFLICT (campaign_id, phone) DO NOTHING
                """,
                lead["client_id"],
                lead["campaign_id"],
                lead["phone"],
                lead.get("name"),
                lead.get("lead_type", "cold"),
                lead_status,
                lead.get("max_attempts", 3),
                meta_json,
            )
            if result.split()[-1] == "1":
                inserted += 1
                if lead_status == "dnc":
                    await conn.execute(
                        """
                        UPDATE campaigns SET
                            total_leads = total_leads + 1,
                            dnc_leads = dnc_leads + 1
                        WHERE id = $1
                        """,
                        lead["campaign_id"],
                    )
                else:
                    await increment_campaign_counters(
                        conn,
                        lead["campaign_id"],
                        from_status="__upload__",
                        to_status="pending",
                        count=1,
                    )
    return inserted


async def bump_pending_retry_to_now(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> int:
    """Make pending leads with a future retry time dialable immediately (e.g. after stop/start)."""
    result = await pool.execute(
        """
        UPDATE leads SET next_attempt_at = NOW()
        WHERE campaign_id = $1 AND client_id = $2
          AND status = 'pending'
          AND next_attempt_at > NOW()
        """,
        campaign_id,
        client_id,
    )
    return int(result.split()[-1])


async def claim_leads_for_dialer(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    slots: int,
) -> list[dict]:
    if slots <= 0:
        return []
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, phone, name, metadata, lead_type, attempts, status
                FROM leads
                WHERE campaign_id = $1
                  AND client_id = $2
                  AND status IN ('pending', 'callback_scheduled')
                  AND next_attempt_at <= NOW()
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($4 * INTERVAL '1 minute')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = leads.id
                      AND c.ended_at IS NOT NULL
                      AND c.ended_at > NOW() - ($5 * INTERVAL '1 minute')
                  )
                ORDER BY next_attempt_at ASC
                LIMIT $3
                FOR UPDATE SKIP LOCKED
                """,
                campaign_id,
                client_id,
                slots,
                live_call_grace_minutes(),
                post_call_wrap_grace_minutes(),
            )
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            await conn.execute(
                """
                UPDATE leads SET status = 'calling', last_attempted_at = NOW()
                WHERE id = ANY($1::uuid[]) AND client_id = $2
                """,
                ids,
                client_id,
            )
            for r in rows:
                await increment_campaign_counters(
                    conn,
                    campaign_id,
                    from_status=r["status"],
                    to_status="calling",
                )
            return records_to_dicts(rows)


async def release_stuck_calling_leads(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> int:
    """
    Reset leads left in ``calling`` (no live call) back to ``pending``.
    Fixes denorm counters. Returns number of leads released.
    """
    await finalize_stale_in_progress_call_logs(pool, campaign_id, client_id)
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    async with pool.acquire() as conn:
        async with conn.transaction():
            live_rows = await conn.fetch(
                """
                SELECT l.id AS lead_id,
                       EXISTS (
                         SELECT 1 FROM call_logs c
                         WHERE c.lead_id = l.id AND c.in_progress = TRUE
                           AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                       ) AS has_live_call,
                       EXISTS (
                         SELECT 1 FROM call_logs c
                         WHERE c.lead_id = l.id
                           AND c.ended_at IS NOT NULL
                           AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                       ) AS has_recent_wrap_up
                FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                """,
                campaign_id,
                client_id,
                grace,
                wrap,
            )
            rows = await conn.fetch(
                """
                SELECT l.id FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = l.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = l.id
                      AND c.ended_at IS NOT NULL
                      AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                  )
                """,
                campaign_id,
                client_id,
                grace,
                wrap,
            )
            skipped_live = sum(1 for r in live_rows if r["has_live_call"])
            skipped_wrap = sum(1 for r in live_rows if r["has_recent_wrap_up"])
            logger.info(
                "release_stuck_calling_leads campaign={} calling={} "
                "releasing={} skipping_live={} skipping_wrap_up={}",
                campaign_id,
                len(live_rows),
                len(rows),
                skipped_live,
                skipped_wrap,
            )
            if not rows:
                return 0
            ids = [r["id"] for r in rows]
            await conn.execute(
                """
                UPDATE leads
                SET status = 'pending',
                    next_attempt_at = NOW()
                WHERE id = ANY($1::uuid[]) AND client_id = $2 AND status = 'calling'
                """,
                ids,
                client_id,
            )
            for _ in rows:
                await increment_campaign_counters(
                    conn,
                    campaign_id,
                    from_status="calling",
                    to_status="pending",
                )
            return len(rows)

async def release_all_stuck_calling_leads(pool: asyncpg.Pool) -> int:
    """Run release_stuck_calling_leads for all campaigns with calling_leads > 0."""
    rows = await pool.fetch("SELECT id, client_id FROM campaigns WHERE calling_leads > 0")
    total_released = 0
    for r in rows:
        released = await release_stuck_calling_leads(pool, r["id"], r["client_id"])
        total_released += released
    return total_released


async def transition_all_pausing_to_paused(pool: asyncpg.Pool) -> int:
    """Transition any pausing campaign with calling_leads = 0 to paused."""
    rows = await pool.fetch(
        """
        UPDATE campaigns
        SET status = 'paused'
        WHERE status = 'pausing' AND calling_leads = 0
        RETURNING id
        """
    )
    return len(rows)


async def reconcile_campaign_counters(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> dict[str, int]:
    """
    Recompute denormalized campaign counters from ``leads`` rows.
    Recovery / dev only — not used on hot call path.
    """
    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_leads,
            COUNT(*) FILTER (WHERE status = 'pending')::int AS pending_leads,
            COUNT(*) FILTER (WHERE status = 'calling')::int AS calling_leads,
            COUNT(*) FILTER (WHERE status = 'callback_scheduled')::int AS callback_leads,
            COUNT(*) FILTER (WHERE status = 'completed')::int AS completed_leads,
            COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_leads,
            COUNT(*) FILTER (WHERE status = 'dnc')::int AS dnc_leads
        FROM leads
        WHERE campaign_id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )
    counts = {
        "total_leads": int(row["total_leads"] or 0),
        "pending_leads": int(row["pending_leads"] or 0),
        "calling_leads": int(row["calling_leads"] or 0),
        "callback_leads": int(row["callback_leads"] or 0),
        "completed_leads": int(row["completed_leads"] or 0),
        "failed_leads": int(row["failed_leads"] or 0),
        "dnc_leads": int(row["dnc_leads"] or 0),
    }
    await pool.execute(
        """
        UPDATE campaigns SET
            total_leads = $1,
            pending_leads = $2,
            calling_leads = $3,
            callback_leads = $4,
            completed_leads = $5,
            failed_leads = $6,
            dnc_leads = $7
        WHERE id = $8 AND client_id = $9
        """,
        counts["total_leads"],
        counts["pending_leads"],
        counts["calling_leads"],
        counts["callback_leads"],
        counts["completed_leads"],
        counts["failed_leads"],
        counts["dnc_leads"],
        campaign_id,
        client_id,
    )
    return counts


async def fetch_active_lead_for_post_call(
    conn: asyncpg.Connection,
    lead_id: UUID,
    client_id: UUID,
) -> dict | None:
    """Lock lead for post-call if still in an active dial state."""
    row = await conn.fetchrow(
        """
        SELECT status, next_attempt_at, scheduled_callback_at
        FROM leads
        WHERE id = $1 AND client_id = $2
          AND status IN ('calling', 'callback_scheduled')
        FOR UPDATE
        """,
        lead_id,
        client_id,
    )
    return record_to_dict(row) if row else None


async def update_lead_post_call(
    pool_or_conn: asyncpg.Pool | asyncpg.Connection,
    lead_id: UUID,
    client_id: UUID,
    from_status: str,
    new_status: str,
    outcome: str,
    extraction: dict,
    attempts: int,
    next_attempt_at: datetime | None,
    scheduled_callback_at: datetime | None,
) -> bool:
    """Update lead after post-call. Returns False if status changed under lock."""
    ext_json = json.dumps(extraction, ensure_ascii=False)
    sql = """
        UPDATE leads SET
            status = $1,
            outcome = $2,
            extraction = $3::jsonb,
            attempts = $4,
            next_attempt_at = COALESCE($5, next_attempt_at),
            scheduled_callback_at = $6,
            last_attempted_at = NOW()
        WHERE id = $7 AND client_id = $8 AND status = $9
    """
    args = (
        new_status,
        outcome,
        ext_json,
        attempts,
        next_attempt_at,
        scheduled_callback_at,
        lead_id,
        client_id,
        from_status,
    )
    if isinstance(pool_or_conn, asyncpg.Pool):
        result = await pool_or_conn.execute(sql, *args)
    else:
        result = await pool_or_conn.execute(sql, *args)
    return result.split()[-1] == "1"


async def terminalize_campaign_leads(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> int:
    """
    Mark non-terminal leads failed on campaign cancel.
    Leaves ``calling`` rows with live in_progress call_logs for post-call.
    """
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    r1 = await conn.execute(
        """
        UPDATE leads SET
            status = 'failed',
            outcome = 'Campaign cancelled'
        WHERE campaign_id = $1 AND client_id = $2
          AND status IN ('pending', 'callback_scheduled')
        """,
        campaign_id,
        client_id,
    )
    r2 = await conn.execute(
        """
        UPDATE leads SET
            status = 'failed',
            outcome = 'Campaign cancelled'
        WHERE campaign_id = $1 AND client_id = $2 AND status = 'calling'
          AND NOT EXISTS (
            SELECT 1 FROM call_logs c
            WHERE c.lead_id = leads.id AND c.in_progress = TRUE
              AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
          )
          AND NOT EXISTS (
            SELECT 1 FROM call_logs c
            WHERE c.lead_id = leads.id
              AND c.ended_at IS NOT NULL
              AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
          )
        """,
        campaign_id,
        client_id,
        grace,
        wrap,
    )
    n1 = int(r1.split()[-1])
    n2 = int(r2.split()[-1])
    return n1 + n2


async def cancel_campaign(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
) -> dict[str, Any]:
    """Terminalize leads, mark cancelled, return credits when no in-flight calls."""
    await finalize_stale_in_progress_call_logs(pool, campaign_id, client_id)
    await release_stuck_calling_leads(pool, campaign_id, client_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            camp = await conn.fetchrow(
                """
                SELECT status FROM campaigns
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
                campaign_id,
                client_id,
            )
            if camp is None:
                raise ValueError(f"Campaign not found: {campaign_id}")
            if camp["status"] in ("completed", "cancelled"):
                raise ValueError(f"Campaign already terminal: {camp['status']}")

            leads_terminalized = await terminalize_campaign_leads(
                conn, campaign_id, client_id
            )

            credits_returned, _ = await try_settle_campaign_budget(
                campaign_id,
                client_id,
                final_status="cancelled",
                conn=conn,
            )

    await reconcile_campaign_counters(pool, campaign_id, client_id)

    camp_after = await get_campaign(pool, campaign_id, client_id)
    calling_remaining = int(camp_after.get("calling_leads") or 0) if camp_after else 0
    return {
        "status": camp_after.get("status") if camp_after else "cancelled",
        "leads_terminalized": leads_terminalized,
        "credits_returned": float(credits_returned),
        "calling_leads_remaining": calling_remaining,
        "budget_settled": camp_after.get("budget_returned_at") is not None
        if camp_after
        else False,
    }


async def get_lead(
    pool: asyncpg.Pool,
    lead_id: UUID,
    client_id: UUID,
) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM leads WHERE id = $1 AND client_id = $2",
        lead_id,
        client_id,
    )
    return record_to_dict(row)


async def list_campaign_leads(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Return a paginated list of leads for a campaign, plus total count."""
    query = "SELECT * FROM leads WHERE campaign_id = $1 AND client_id = $2"
    count_query = "SELECT COUNT(*) FROM leads WHERE campaign_id = $1 AND client_id = $2"
    args: list[Any] = [campaign_id, client_id]
    idx = 3

    if status:
        query += f" AND status = ${idx}"
        count_query += f" AND status = ${idx}"
        args.append(status)
        idx += 1

    if search:
        search_pattern = f"%{search}%"
        query += f" AND (name ILIKE ${idx} OR phone ILIKE ${idx})"
        count_query += f" AND (name ILIKE ${idx} OR phone ILIKE ${idx})"
        args.append(search_pattern)
        idx += 1

    total_count = await pool.fetchval(count_query, *args)
    query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    args.extend([limit, offset])

    rows = await pool.fetch(query, *args)
    return records_to_dicts(rows), total_count


async def update_lead_fields(
    pool: asyncpg.Pool,
    lead_id: UUID,
    client_id: UUID,
    *,
    name: str | None = None,
    lead_type: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Update user-editable fields on a lead. Returns True if a row was updated."""
    sets: list[str] = []
    args: list[Any] = []
    idx = 1

    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if lead_type is not None:
        sets.append(f"lead_type = ${idx}")
        args.append(lead_type)
        idx += 1
    if metadata is not None:
        sets.append(f"metadata = ${idx}::jsonb")
        args.append(json.dumps(metadata, ensure_ascii=False))
        idx += 1

    if not sets:
        return False

    args.extend([lead_id, client_id])
    result = await pool.execute(
        f"UPDATE leads SET {', '.join(sets)} WHERE id = ${idx} AND client_id = ${idx + 1}",
        *args,
    )
    return result.split()[-1] != "0"


async def insert_single_lead(
    pool: asyncpg.Pool,
    lead: dict,
) -> dict:
    """Insert one lead. Returns the inserted row as a dict.

    Raises ``ValueError`` if the phone is a duplicate within the campaign.
    Counter increments are handled atomically.
    """
    meta = lead.get("metadata") or {}
    meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, dict) else meta
    lead_status = lead.get("status", "pending")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO leads (
                    client_id, campaign_id, phone, name, lead_type,
                    status, max_attempts, next_attempt_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8::jsonb)
                ON CONFLICT (campaign_id, phone) DO NOTHING
                RETURNING *
                """,
                lead["client_id"],
                lead["campaign_id"],
                lead["phone"],
                lead.get("name"),
                lead.get("lead_type", "cold"),
                lead_status,
                lead.get("max_attempts", 3),
                meta_json,
            )
            if row is None:
                raise ValueError(
                    f"Duplicate phone {lead['phone']} in this campaign"
                )

            if lead_status == "dnc":
                await conn.execute(
                    """
                    UPDATE campaigns SET
                        total_leads = total_leads + 1,
                        dnc_leads = dnc_leads + 1
                    WHERE id = $1
                    """,
                    lead["campaign_id"],
                )
            else:
                await increment_campaign_counters(
                    conn,
                    lead["campaign_id"],
                    from_status="__upload__",
                    to_status="pending",
                    count=1,
                )

    return record_to_dict(row)


async def delete_lead(
    pool: asyncpg.Pool,
    lead_id: UUID,
    campaign_id: UUID,
    client_id: UUID,
) -> bool:
    """Hard-delete a lead row. Returns True if a row was deleted.

    call_logs rows for this lead are intentionally preserved.
    Callers should run ``reconcile_campaign_counters`` after this.
    """
    result = await pool.execute(
        "DELETE FROM leads WHERE id = $1 AND campaign_id = $2 AND client_id = $3",
        lead_id,
        campaign_id,
        client_id,
    )
    return result.split()[-1] != "0"


async def update_lead_status_manual(
    pool: asyncpg.Pool,
    lead_id: UUID,
    client_id: UUID,
    new_status: str,
    *,
    next_attempt_at: datetime | None = None,
    scheduled_callback_at: datetime | None = None,
) -> bool:
    """Manually change a lead's status. Returns True if a row was updated.

    Does NOT reconcile counters — callers should run
    ``reconcile_campaign_counters`` after this.
    """
    result = await pool.execute(
        """
        UPDATE leads
        SET status = $1,
            next_attempt_at = $2,
            scheduled_callback_at = $3
        WHERE id = $4 AND client_id = $5
        """,
        new_status,
        next_attempt_at,
        scheduled_callback_at,
        lead_id,
        client_id,
    )
    return result.split()[-1] != "0"


# ── Call logs ─────────────────────────────────────────────────────────────────


async def insert_call_log_start(
    pool: asyncpg.Pool,
    session_call_id: str,
    client_id: UUID,
    campaign_id: UUID | None,
    lead_id: UUID | None,
    bot_config_id: UUID | None,
    route: str,
    started_at: datetime,
) -> UUID:
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    
    # We use an advisory lock on the lead_id to strictly prevent concurrent duplicate dials
    # (Since UUIDs are 128-bit, we take a lock on the first 64 bits)
    lock_id = None
    if lead_id:
        lock_id = int.from_bytes(lead_id.bytes[:8], 'big') - 2**63

    async with pool.acquire() as conn:
        async with conn.transaction():
            if lock_id is not None:
                await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

            if lead_id is not None:
                live = await conn.fetchval(
                    """
                    SELECT 1 FROM call_logs
                    WHERE lead_id = $1 AND in_progress = TRUE
                      AND started_at > NOW() - ($2 * INTERVAL '1 minute')
                    LIMIT 1
                    """,
                    lead_id, grace
                )
                recent_end = await conn.fetchval(
                    """
                    SELECT 1 FROM call_logs
                    WHERE lead_id = $1
                      AND ended_at IS NOT NULL
                      AND ended_at > NOW() - ($2 * INTERVAL '1 minute')
                    LIMIT 1
                    """,
                    lead_id, wrap
                )
                if live or recent_end:
                    raise Exception("Duplicate call prevented by atomic check")

            row = await conn.fetchrow(
                """
                INSERT INTO call_logs (
                    session_call_id, client_id, campaign_id, lead_id,
                    bot_config_id, route, started_at, in_progress, transcript
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, '[]'::jsonb)
                RETURNING id
                """,
                session_call_id,
                client_id,
                campaign_id,
                lead_id,
                bot_config_id,
                route,
                started_at,
            )
            return row["id"]


async def mark_call_log_not_in_progress(
    pool: asyncpg.Pool,
    session_call_id: str,
) -> bool:
    """Clear live flag as soon as the pipeline ends (before post-call extraction)."""
    row = await pool.fetchrow(
        """
        UPDATE call_logs SET
            in_progress = FALSE,
            ended_at = COALESCE(ended_at, NOW())
        WHERE session_call_id = $1 AND in_progress = TRUE
        RETURNING id
        """,
        session_call_id,
    )
    return row is not None


async def link_call_log_plivo_sid(
    pool: asyncpg.Pool,
    session_call_id: str,
    call_uuid: str,
) -> bool:
    """Persist Plivo CallUUID on the call_log row (idempotent)."""
    if not session_call_id or not call_uuid:
        return False
    row = await pool.fetchrow(
        """
        UPDATE call_logs SET call_sid = $2
        WHERE session_call_id = $1
          AND (call_sid IS NULL OR call_sid = $2)
        RETURNING id
        """,
        session_call_id,
        call_uuid,
    )
    return row is not None


async def get_call_log_by_session(
    pool: asyncpg.Pool,
    session_call_id: str,
) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM call_logs WHERE session_call_id = $1",
        session_call_id,
    )
    return record_to_dict(row)


async def get_call_log_by_call_sid(
    pool: asyncpg.Pool,
    call_sid: str,
) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM call_logs WHERE call_sid = $1 ORDER BY started_at DESC LIMIT 1",
        call_sid,
    )
    return record_to_dict(row)


def _normalize_hangup_source(payload: dict) -> str:
    raw = payload.get("HangupSource") or payload.get("hangup_source") or ""
    return str(raw).strip().lower()


def plivo_hangup_callback_enabled() -> bool:
    v = (os.getenv("PLIVO_HANGUP_CALLBACK_ENABLED") or "true").strip().lower()
    return v not in ("0", "false", "no", "off")


async def record_plivo_hangup(
    pool: asyncpg.Pool,
    *,
    session_call_id: str | None,
    call_uuid: str | None,
    payload: dict,
) -> dict | None:
    """Store Plivo hangup payload on call_logs; return row or None."""
    stored = {
        **payload,
        "hangup_source": _normalize_hangup_source(payload),
        "call_uuid": call_uuid or payload.get("CallUUID") or payload.get("call_uuid"),
    }
    blob = json.dumps(stored, ensure_ascii=False)
    if session_call_id:
        row = await pool.fetchrow(
            """
            UPDATE call_logs SET
                plivo_hangup_json = COALESCE(plivo_hangup_json, '{}'::jsonb) || $2::jsonb,
                call_sid = COALESCE(call_sid, $3)
            WHERE session_call_id = $1
            RETURNING *
            """,
            session_call_id,
            blob,
            stored.get("call_uuid"),
        )
        return record_to_dict(row)
    if call_uuid:
        row = await pool.fetchrow(
            """
            UPDATE call_logs SET
                plivo_hangup_json = COALESCE(plivo_hangup_json, '{}'::jsonb) || $2::jsonb,
                call_sid = COALESCE(call_sid, $1)
            WHERE call_sid = $1
            RETURNING *
            """,
            call_uuid,
            blob,
        )
        return record_to_dict(row)
    return None


async def apply_callee_hangup_callback(
    pool: asyncpg.Pool,
    call_log: dict,
    payload: dict,
) -> bool:
    """
    Move lead calling -> callback_scheduled when callee hung up mid-call.
    Idempotent if hangup already processed or lead no longer calling.
    """
    if not plivo_hangup_callback_enabled():
        return False
    if _normalize_hangup_source(payload) != "callee":
        return False

    lead_id = call_log.get("lead_id")
    campaign_id = call_log.get("campaign_id")
    client_id = call_log.get("client_id")
    if not lead_id or not campaign_id or not client_id:
        return False

    existing = call_log.get("plivo_hangup_json") or {}
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except json.JSONDecodeError:
            existing = {}
    if existing.get("hangup_processed_at"):
        return bool(existing.get("callback_applied"))

    session_call_id = call_log.get("session_call_id")
    retry_delay = 120
    camp = await get_campaign(pool, UUID(str(campaign_id)), UUID(str(client_id)))
    if camp:
        retry_delay = int(camp.get("retry_delay_minutes") or 120)

    async with pool.acquire() as conn:
        async with conn.transaction():
            lead_row = await conn.fetchrow(
                """
                SELECT status FROM leads
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
                UUID(str(lead_id)),
                UUID(str(client_id)),
            )
            if not lead_row or lead_row["status"] != "calling":
                await conn.execute(
                    """
                    UPDATE call_logs SET plivo_hangup_json = plivo_hangup_json || $2::jsonb
                    WHERE session_call_id = $1
                    """,
                    session_call_id,
                    json.dumps(
                        {
                            "hangup_processed_at": datetime.now(timezone.utc).isoformat(),
                            "callback_applied": False,
                        },
                        ensure_ascii=False,
                    ),
                )
                return False

            await conn.execute(
                """
                UPDATE leads SET
                    status = 'callback_scheduled',
                    next_attempt_at = NOW() + ($3::text || ' minutes')::interval,
                    scheduled_callback_at = NOW() + ($3::text || ' minutes')::interval
                WHERE id = $1 AND client_id = $2 AND status = 'calling'
                """,
                UUID(str(lead_id)),
                UUID(str(client_id)),
                str(retry_delay),
            )
            await increment_campaign_counters(
                conn,
                UUID(str(campaign_id)),
                from_status="calling",
                to_status="callback_scheduled",
            )
            await conn.execute(
                """
                UPDATE call_logs SET plivo_hangup_json = plivo_hangup_json || $2::jsonb
                WHERE session_call_id = $1
                """,
                session_call_id,
                json.dumps(
                    {
                        "hangup_processed_at": datetime.now(timezone.utc).isoformat(),
                        "callback_applied": True,
                        "retry_delay_minutes": retry_delay,
                    },
                    ensure_ascii=False,
                ),
            )
    logger.info(
        "Callee hangup -> callback_scheduled lead={} campaign={} call={} retry_min={}",
        lead_id,
        campaign_id,
        session_call_id,
        retry_delay,
    )
    return True


async def append_transcript_turn(
    pool: asyncpg.Pool,
    session_call_id: str,
    role: str,
    content: str,
    ts: datetime,
) -> None:
    turn = json.dumps(
        {"role": role, "content": content, "ts": ts.isoformat()},
        ensure_ascii=False,
    )
    await pool.execute(
        """
        UPDATE call_logs
        SET transcript = transcript || $1::jsonb
        WHERE session_call_id = $2 AND in_progress = TRUE
        """,
        f"[{turn}]",
        session_call_id,
    )


async def finalize_call_log(
    pool_or_conn: asyncpg.Pool | asyncpg.Connection,
    session_call_id: str,
    duration_seconds: int,
    outcome: str,
    extraction_json: dict,
    billed_minutes: int,
    credits_charged: float,
    usage: dict,
    *,
    transcript: list[dict] | None = None,
    extraction_model: str | None = None,
    extraction_error: str | None = None,
    qualified: bool | None = None,
) -> None:
    ext = json.dumps(extraction_json or {}, ensure_ascii=False)
    qual = qualified if qualified is not None else (outcome == "Interested")
    transcript_json = (
        json.dumps(transcript, ensure_ascii=False) if transcript is not None else None
    )
    sql = """
        UPDATE call_logs SET
            in_progress = FALSE,
            ended_at = NOW(),
            duration_seconds = $1,
            billed_minutes = $2,
            credits_charged = $3,
            outcome = $4,
            qualified = $5,
            extraction_json = $6::jsonb,
            usage_prompt_tokens = $7,
            usage_completion_tokens = $8,
            usage_total_tokens = $9,
            usage_tts_characters = $10,
            extraction_model = $11,
            extraction_error = $12
    """
    args: list[Any] = [
        duration_seconds,
        billed_minutes,
        Decimal(str(credits_charged)),
        outcome,
        qual,
        ext,
        int(usage.get("llm_prompt_tokens") or 0),
        int(usage.get("llm_completion_tokens") or 0),
        int(usage.get("llm_total_tokens") or 0),
        int(usage.get("tts_characters") or 0),
        extraction_model,
        extraction_error,
    ]
    if transcript_json is not None:
        sql += ", transcript = $13::jsonb WHERE session_call_id = $14"
        args.extend([transcript_json, session_call_id])
    else:
        sql += " WHERE session_call_id = $13"
        args.append(session_call_id)

    if isinstance(pool_or_conn, asyncpg.Pool):
        await pool_or_conn.execute(sql, *args)
    else:
        await pool_or_conn.execute(sql, *args)


async def finalize_call_log_dev(
    pool: asyncpg.Pool,
    session_call_id: str,
    client_id: UUID,
    route: str,
    started_at: datetime,
    duration_seconds: int,
    transcript: list[dict],
    usage: dict,
    extraction_json: dict | None,
    cost_inr: float | None,
) -> None:
    """Upsert-style finalize for Phase 0 parallel path (dev client, no campaign)."""
    ext = json.dumps(extraction_json or {}, ensure_ascii=False)
    trans = json.dumps(transcript, ensure_ascii=False)
    call_data = json.dumps({"cost_inr": cost_inr}, ensure_ascii=False)
    existing = await pool.fetchrow(
        "SELECT id FROM call_logs WHERE session_call_id = $1",
        session_call_id,
    )
    if existing:
        await pool.execute(
            """
            UPDATE call_logs SET
                in_progress = FALSE,
                ended_at = NOW(),
                duration_seconds = $1,
                route = $2,
                transcript = $3::jsonb,
                extraction_json = $4::jsonb,
                usage_prompt_tokens = $5,
                usage_completion_tokens = $6,
                usage_total_tokens = $7,
                usage_tts_characters = $8,
                call_data = call_data || $9::jsonb
            WHERE session_call_id = $10
            """,
            duration_seconds,
            route if route == "cascaded" else route,
            trans,
            ext,
            int(usage.get("llm_prompt_tokens") or 0),
            int(usage.get("llm_completion_tokens") or 0),
            int(usage.get("llm_total_tokens") or 0),
            int(usage.get("tts_characters") or 0),
            call_data,
            session_call_id,
        )
    else:
        pg_route = "cascaded" if route == "cascade" else route
        await pool.execute(
            """
            INSERT INTO call_logs (
                session_call_id, client_id, route, started_at, ended_at,
                duration_seconds, in_progress, transcript, extraction_json,
                usage_prompt_tokens, usage_completion_tokens,
                usage_total_tokens, usage_tts_characters, call_data
            )
            VALUES ($1, $2, $3, $4, NOW(), $5, FALSE, $6::jsonb, $7::jsonb,
                    $8, $9, $10, $11, $12::jsonb)
            """,
            session_call_id,
            client_id,
            pg_route,
            started_at,
            duration_seconds,
            trans,
            ext,
            int(usage.get("llm_prompt_tokens") or 0),
            int(usage.get("llm_completion_tokens") or 0),
            int(usage.get("llm_total_tokens") or 0),
            int(usage.get("tts_characters") or 0),
            call_data,
        )


async def get_call_log(
    pool: asyncpg.Pool,
    session_call_id: str,
    client_id: UUID,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM call_logs
        WHERE session_call_id = $1 AND client_id = $2
        """,
        session_call_id,
        client_id,
    )
    return record_to_dict(row)


async def get_latest_call_log_for_lead(
    pool: asyncpg.Pool,
    lead_id: UUID,
    client_id: UUID,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM call_logs
        WHERE lead_id = $1 AND client_id = $2
        ORDER BY created_at DESC
        LIMIT 1
        """,
        lead_id,
        client_id,
    )
    return record_to_dict(row)


async def list_call_logs(
    pool: asyncpg.Pool,
    client_id: UUID | None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    if client_id is None:
        total = await pool.fetchval("SELECT COUNT(*) FROM call_logs")
        rows = await pool.fetch(
            """
            SELECT * FROM call_logs
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    else:
        total = await pool.fetchval("SELECT COUNT(*) FROM call_logs WHERE client_id = $1", client_id)
        rows = await pool.fetch(
            """
            SELECT * FROM call_logs
            WHERE client_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            client_id,
            limit,
            offset,
        )
    return records_to_dicts(rows), total


# ── Webhooks ──────────────────────────────────────────────────────────────────


async def upsert_webhook_config(
    pool: asyncpg.Pool,
    client_id: UUID,
    event: str,
    url: str,
    secret: str,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO webhook_configs (client_id, event, url, secret)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (client_id, event) DO UPDATE SET
            url = EXCLUDED.url,
            secret = EXCLUDED.secret,
            active = TRUE
        RETURNING id
        """,
        client_id,
        event,
        url,
        secret,
    )
    return row["id"]


async def get_webhook_configs(
    pool: asyncpg.Pool,
    client_id: UUID,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM webhook_configs
        WHERE client_id = $1 AND active = TRUE
        """,
        client_id,
    )
    return records_to_dicts(rows)


async def get_webhook_config_for_event(
    pool: asyncpg.Pool,
    client_id: UUID,
    event: str,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM webhook_configs
        WHERE client_id = $1 AND event = $2 AND active = TRUE
        """,
        client_id,
        event,
    )
    return record_to_dict(row)


# ── Campaign counters ─────────────────────────────────────────────────────────


async def increment_campaign_counters(
    pool_or_conn: asyncpg.Pool | asyncpg.Connection,
    campaign_id: UUID,
    from_status: str,
    to_status: str,
    count: int = 1,
) -> None:
    if from_status == "__upload__" and to_status == "pending":
        sets = [
            "total_leads = total_leads + $1",
            "pending_leads = pending_leads + $1",
        ]
        sql = f"UPDATE campaigns SET {', '.join(sets)} WHERE id = $2"
        args: tuple[Any, ...] = (count, campaign_id)
    else:
        deltas = _COUNTER_DELTAS.get((from_status, to_status))
        if not deltas:
            return
        parts = []
        args_list: list[Any] = []
        idx = 1
        for col, delta in deltas.items():
            if col not in _ALLOWED_COUNTER_COLS:
                continue
            sign = "+" if delta > 0 else "-"
            parts.append(f"{col} = {col} {sign} ${idx}")
            args_list.append(abs(delta) * count)
            idx += 1
        if not parts:
            return
        args_list.append(campaign_id)
        sql = f"UPDATE campaigns SET {', '.join(parts)} WHERE id = ${idx}"
        args = tuple(args_list)

    if isinstance(pool_or_conn, asyncpg.Pool):
        await pool_or_conn.execute(sql, *args)
    else:
        await pool_or_conn.execute(sql, *args)


async def get_lead_status_for_update(
    conn: asyncpg.Connection,
    lead_id: UUID,
    client_id: UUID,
) -> str | None:
    return await conn.fetchval(
        "SELECT status FROM leads WHERE id = $1 AND client_id = $2",
        lead_id,
        client_id,
    )

"""PostgreSQL connection pool and multi-tenant query helpers."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger
import time

_pool: asyncpg.Pool | None = None

# Short TTL caches for dashboard poll traffic (10s staleness is fine).
_STATS_CACHE_TTL_S = 10.0
_outcome_stats_cache: dict[str, tuple[float, dict]] = {}
_interested_counts_cache: dict[str, tuple[float, dict[str, int]]] = {}

# Count assistant/user/bot turns — matches post_call_processor + frontend analytics.
_TRANSCRIPT_TURNS_EXPR = """
(SELECT COUNT(*)::int
 FROM jsonb_array_elements(COALESCE({alias}.transcript, '[]'::jsonb)) AS t(elem)
 WHERE COALESCE(elem->>'role', '') IN ('assistant', 'user', 'bot'))
"""


def resolve_lead_retry_or_failed(
    attempts: int,
    max_attempts: int,
    retry_delay_minutes: int,
    *,
    base_outcome: str = "Unknown",
    now: datetime | None = None,
) -> tuple[str, datetime | None, str]:
    """Return (status, next_attempt_at, outcome) after an inconclusive attempt.

    ``attempts`` must already include the attempt that just finished (dialer
    increments on claim).
    """
    ts = now or datetime.now(UTC)
    if attempts >= max_attempts:
        return "failed", None, "Max_Attempts_Reached"
    return "callback_scheduled", ts + timedelta(minutes=retry_delay_minutes), base_outcome


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


def orphaned_dial_minutes() -> int:
    """How long to wait before an in_progress call_log with no Plivo call_sid is orphaned."""
    raw = (os.getenv("ORPHANED_DIAL_MINUTES") or "3").strip()
    try:
        mins = int(raw)
    except ValueError:
        mins = 3
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
        WITH stale_logs AS (
            SELECT cl.id
            FROM call_logs cl
            JOIN campaigns c ON cl.campaign_id = c.id AND cl.client_id = c.client_id
            WHERE cl.campaign_id = $1 AND cl.client_id = $2 AND cl.in_progress = TRUE
              AND cl.started_at < NOW() - GREATEST(COALESCE(c.max_call_minutes, 0) + 2, $3) * INTERVAL '1 minute'
            LIMIT 500
        )
        UPDATE call_logs cl SET
            in_progress = FALSE,
            ended_at = COALESCE(cl.ended_at, NOW()),
            outcome = COALESCE(NULLIF(TRIM(cl.outcome), ''), 'Unknown')
        FROM stale_logs sl
        WHERE cl.id = sl.id
        RETURNING cl.id
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
        WITH stale_logs AS (
            SELECT cl.id
            FROM call_logs cl
            JOIN campaigns c ON cl.campaign_id = c.id AND cl.client_id = c.client_id
            WHERE cl.in_progress = TRUE
              AND cl.started_at < NOW() - GREATEST(COALESCE(c.max_call_minutes, 0) + 2, $1) * INTERVAL '1 minute'
            LIMIT 500
        )
        UPDATE call_logs cl SET
            in_progress = FALSE,
            ended_at = COALESCE(cl.ended_at, NOW()),
            outcome = COALESCE(NULLIF(TRIM(cl.outcome), ''), 'Unknown')
        FROM stale_logs sl
        WHERE cl.id = sl.id
        RETURNING cl.id
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


async def settle_budget_for_stale_call_logs(pool: asyncpg.Pool) -> int:
    """Settle budget for call_logs finalized by the stale sweep that still hold reservations."""
    rows = await pool.fetch(
        """
        SELECT cl.session_call_id, cl.campaign_id, cl.client_id, cl.call_data
        FROM call_logs cl
        WHERE cl.in_progress = FALSE
          AND cl.credits_charged IS NULL
          AND cl.ended_at IS NOT NULL
          AND cl.ended_at > NOW() - INTERVAL '7 days'
          AND cl.call_data IS NOT NULL
        """
    )
    settled = 0
    for row in rows:
        reserved = budget_reserved_from_call_data(row["call_data"])
        if reserved <= 0:
            continue
        try:
            async with pool.acquire() as conn, conn.transaction():
                result = await conn.execute(
                    """
                        UPDATE call_logs
                        SET credits_charged = 0, billed_minutes = 0
                        WHERE session_call_id = $1 AND credits_charged IS NULL
                        """,
                    row["session_call_id"],
                )
                if result.split()[-1] == "0":
                    continue
                
                await settle_call_budget(
                    conn,
                    row["campaign_id"],
                    row["client_id"],
                    Decimal(0),
                    reserved,
                )
            settled += 1
        except Exception as exc:
            logger.warning(
                "Failed to settle budget for stale call_log {}: {}",
                row["session_call_id"],
                exc,
            )
    if settled:
        logger.info("Settled budget for {} stale call_log(s)", settled)
    return settled


# Counter deltas: (from_status, to_status) -> column adjustments
_COUNTER_DELTAS: dict[tuple[str, str], dict[str, int]] = {
    ("pending", "calling"): {"calling_leads": 1, "pending_leads": -1},
    ("callback_scheduled", "calling"): {"calling_leads": 1, "callback_leads": -1},
    ("calling", "completed"): {"calling_leads": -1, "completed_leads": 1},
    ("calling", "failed"): {"calling_leads": -1, "failed_leads": 1},
    ("calling", "callback_scheduled"): {"calling_leads": -1, "callback_leads": 1},
    ("calling", "pending"): {"calling_leads": -1, "pending_leads": 1},
    ("callback_scheduled", "completed"): {"callback_leads": -1, "completed_leads": 1},
    ("callback_scheduled", "failed"): {"callback_leads": -1, "failed_leads": 1},
    ("callback_scheduled", "pending"): {"callback_leads": -1, "pending_leads": 1},
}

_ALLOWED_COUNTER_COLS = frozenset(
    {
        "total_leads",
        "pending_leads",
        "calling_leads",
        "callback_leads",
        "completed_leads",
        "failed_leads",
    }
)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def database_url() -> str | None:
    import os

    url = (os.getenv("DATABASE_URL") or "").strip()
    return url or None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON codec so JSONB columns are auto-parsed to Python objects."""
    await conn.execute("SET statement_timeout = '15s'")
    await conn.execute("SET idle_in_transaction_session_timeout = '15s'")
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_db_pool(dsn: str) -> asyncpg.Pool:
    """Creates an asyncpg connection pool."""
    import os
    min_size = int(os.getenv("DB_POOL_MIN", "5"))
    max_size = int(os.getenv("DB_POOL_MAX", "50"))
    
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=15,
        init=_init_connection,
    )
    return pool


async def init_pool() -> asyncpg.Pool | None:
    """Create the global asyncpg pool. Returns None if DATABASE_URL is unset."""
    dsn = database_url()
    if not dsn:
        return None
    global _pool
    if _pool is not None:
        return _pool
    _pool = await create_db_pool(dsn)
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


def record_to_dict(record: asyncpg.Record | None) -> dict[str, Any] | None:
    if record is None:
        return None
    out: dict[str, Any] = {}
    for key, val in record.items():
        if isinstance(val, UUID):
            val = str(val)
        elif isinstance(val, Decimal):
            val = float(val)
        elif isinstance(val, datetime):
            val = val.isoformat()
        out[key] = val
    data = out.get("call_data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
            out["call_data"] = data
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict):
        if out.get("setup_charge") is None and data.get("setup_charge") is not None:
            out["setup_charge"] = data["setup_charge"]
        if out.get("duration_charge") is None and data.get("duration_charge") is not None:
            out["duration_charge"] = data["duration_charge"]
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


async def regenerate_client_key(pool: asyncpg.Pool, client_id: UUID) -> str:
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)
    await pool.execute(
        "UPDATE clients SET api_key_hash = $1 WHERE id = $2",
        key_hash,
        client_id,
    )
    return raw_key


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
    async with pool.acquire() as conn, conn.transaction():
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
    script_config_id: UUID | None = None,
    fixed_start_credits: Decimal | float | None = None,
) -> UUID:
    columns = (
        "client_id, name, route, script_id, telephony_number, "
        "credits_per_minute, script_config_id"
    )
    values = "$1, $2, $3, $4, $5, $6, $7"
    args: list[Any] = [
        client_id,
        name,
        route,
        script_id,
        telephony_number,
        Decimal(str(credits_per_minute)),
        script_config_id,
    ]
    if fixed_start_credits is not None:
        columns += ", fixed_start_credits"
        values += ", $8"
        args.append(Decimal(str(fixed_start_credits)))
    row = await pool.fetchrow(
        f"""
        INSERT INTO bot_configs ({columns})
        VALUES ({values})
        RETURNING id
        """,
        *args,
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


async def get_script_config(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM script_configs
        WHERE id = $1 AND client_id = $2 AND active = TRUE
        """,
        script_config_id,
        client_id,
    )
    return record_to_dict(row)


async def get_script_config_admin(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
    *,
    active_only: bool = False,
) -> dict | None:
    if active_only:
        return await get_script_config(pool, script_config_id, client_id)
    row = await pool.fetchrow(
        """
        SELECT * FROM script_configs
        WHERE id = $1 AND client_id = $2
        """,
        script_config_id,
        client_id,
    )
    return record_to_dict(row)


async def list_script_configs(
    pool: asyncpg.Pool,
    client_id: UUID | None = None,
    *,
    active_only: bool = True,
) -> list[dict]:
    if client_id is not None:
        if active_only:
            rows = await pool.fetch(
                """
                SELECT * FROM script_configs
                WHERE client_id = $1 AND active = TRUE
                ORDER BY updated_at DESC
                """,
                client_id,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT * FROM script_configs
                WHERE client_id = $1
                ORDER BY updated_at DESC
                """,
                client_id,
            )
    else:
        if active_only:
            rows = await pool.fetch(
                """
                SELECT * FROM script_configs
                WHERE active = TRUE
                ORDER BY updated_at DESC
                """
            )
        else:
            rows = await pool.fetch(
                """
                SELECT * FROM script_configs
                ORDER BY updated_at DESC
                """
            )
    return records_to_dicts(rows)


def _script_config_json(value: Any) -> Any:
    return value


async def _insert_script_config_revision(
    conn: asyncpg.Connection,
    script_config_id: UUID,
    version: int,
    snapshot: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO script_config_revisions (
            script_config_id, version, config_snapshot
        )
        VALUES ($1, $2, $3::jsonb)
        """,
        script_config_id,
        version,
        _script_config_json(snapshot),
    )
    await conn.execute(
        """
        DELETE FROM script_config_revisions
        WHERE script_config_id = $1
          AND id NOT IN (
              SELECT id
              FROM script_config_revisions
              WHERE script_config_id = $1
              ORDER BY version DESC
              LIMIT 5
          )
        """,
        script_config_id,
    )


async def create_script_config(
    pool: asyncpg.Pool,
    client_id: UUID,
    data: dict[str, Any],
) -> dict:
    from api.script_config_validation import build_config_snapshot

    version = 1
    async with pool.acquire() as conn, conn.transaction():
        try:
            row = await conn.fetchrow(
                """
                    INSERT INTO script_configs (
                        client_id, script_id, route,
                        gemini_model, gemini_voice, gemini_language, gemini_temperature,
                        vad_start_sensitivity, vad_end_sensitivity,
                        vad_silence_duration_ms, vad_prefix_padding_ms,
                        system_instruction_template, bootstrap_messages_json,
                        goodbye_markers,
                        cascade_stt_provider, cascade_stt_model,
                        cascade_llm_provider, cascade_llm_model,
                        cascade_tts_provider, cascade_tts_voice, cascade_live_tools,
                        extraction_schema, lead_schema,
                        normalization_rules, outcome_event_map,
                        outcome_terminal, outcome_retry, outcome_callback,
                        active, version
                    )
                    VALUES (
                        $1, $2, $3,
                        $4, $5, $6, $7,
                        $8, $9, $10, $11,
                        $12, $13::jsonb, $14::jsonb,
                        $15, $16, $17, $18, $19, $20, $21::jsonb,
                        $22::jsonb, $23::jsonb,
                        $24::jsonb, $25::jsonb,
                        $26::jsonb, $27::jsonb, $28::jsonb,
                        $29, $30
                    )
                    RETURNING *
                    """,
                client_id,
                data["script_id"],
                data["route"],
                data.get("gemini_model", "models/gemini-3.1-flash-live-preview"),
                data.get("gemini_voice", "Aoede"),
                data.get("gemini_language", "hi-IN"),
                float(data.get("gemini_temperature", 0.5)),
                data.get("vad_start_sensitivity", "HIGH"),
                data.get("vad_end_sensitivity", "LOW"),
                int(data.get("vad_silence_duration_ms", 800)),
                int(data.get("vad_prefix_padding_ms", 300)),
                data["system_instruction_template"],
                _script_config_json(data.get("bootstrap_messages_json") or []),
                _script_config_json(data.get("goodbye_markers") or []),
                data.get("cascade_stt_provider", "sarvam"),
                data.get("cascade_stt_model", "saarika:v2.5"),
                data.get("cascade_llm_provider", "groq"),
                data.get("cascade_llm_model", "llama-3.3-70b-versatile"),
                data.get("cascade_tts_provider", "cartesia"),
                data.get("cascade_tts_voice", "sonic-3"),
                _script_config_json(data.get("cascade_live_tools") or []),
                _script_config_json(data["extraction_schema"]),
                _script_config_json(data.get("lead_schema") or {"fields": []}),
                _script_config_json(data.get("normalization_rules") or []),
                _script_config_json(data.get("outcome_event_map") or {}),
                _script_config_json(
                    data.get("outcome_terminal")
                    or ["Interested", "Not_Interested"]
                ),
                _script_config_json(
                    data.get("outcome_retry")
                    or ["Busy", "Unknown", "Wrong_Requirement"]
                ),
                _script_config_json(
                    data.get("outcome_callback") or ["Callback_Requested"]
                ),
                bool(data.get("active", True)),
                version,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ValueError(
                f"script_id {data['script_id']!r} already exists for this client"
            ) from exc

        result = record_to_dict(row)
        assert result is not None
        await _insert_script_config_revision(
            conn,
            UUID(str(result["id"])),
            version,
            build_config_snapshot(result),
        )
        return result


_SCRIPT_CONFIG_PATCHABLE = frozenset(
    {
        "script_id",
        "route",
        "gemini_model",
        "gemini_voice",
        "gemini_language",
        "gemini_temperature",
        "vad_start_sensitivity",
        "vad_end_sensitivity",
        "vad_silence_duration_ms",
        "vad_prefix_padding_ms",
        "system_instruction_template",
        "bootstrap_messages_json",
        "goodbye_markers",
        "cascade_stt_provider",
        "cascade_stt_model",
        "cascade_llm_provider",
        "cascade_llm_model",
        "cascade_tts_provider",
        "cascade_tts_voice",
        "cascade_live_tools",
        "extraction_schema",
        "lead_schema",
        "normalization_rules",
        "outcome_event_map",
        "outcome_terminal",
        "outcome_retry",
        "outcome_callback",
        "active",
    }
)

_SCRIPT_CONFIG_JSONB = frozenset(
    {
        "bootstrap_messages_json",
        "goodbye_markers",
        "cascade_live_tools",
        "extraction_schema",
        "lead_schema",
        "normalization_rules",
        "outcome_event_map",
        "outcome_terminal",
        "outcome_retry",
        "outcome_callback",
    }
)


async def update_script_config(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
    patch: dict[str, Any],
) -> dict:
    from api.script_config_validation import build_config_snapshot

    if not patch:
        raise ValueError("empty patch")

    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
                SELECT * FROM script_configs
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
            script_config_id,
            client_id,
        )
        if row is None:
            raise ValueError("script_config not found")

        current = record_to_dict(row)
        assert current is not None
        merged = dict(current)
        for key, val in patch.items():
            if key in _SCRIPT_CONFIG_PATCHABLE:
                merged[key] = val

        new_version = int(current.get("version") or 1) + 1
        sets: list[str] = ["version = $1", "updated_at = NOW()"]
        args: list[Any] = [new_version]
        idx = 2

        for key in sorted(_SCRIPT_CONFIG_PATCHABLE):
            if key not in patch:
                continue
            val = merged[key]
            if key in _SCRIPT_CONFIG_JSONB:
                sets.append(f"{key} = ${idx}::jsonb")
                args.append(_script_config_json(val))
            elif key == "gemini_temperature":
                sets.append(f"{key} = ${idx}")
                args.append(float(val))
            elif key in (
                "vad_silence_duration_ms",
                "vad_prefix_padding_ms",
            ):
                sets.append(f"{key} = ${idx}")
                args.append(int(val))
            else:
                sets.append(f"{key} = ${idx}")
                args.append(val)
            idx += 1

        args.extend([script_config_id, client_id])
        try:
            updated = await conn.fetchrow(
                f"""
                    UPDATE script_configs
                    SET {", ".join(sets)}
                    WHERE id = ${idx} AND client_id = ${idx + 1}
                    RETURNING *
                    """,
                *args,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ValueError(
                f"script_id {patch.get('script_id')!r} already exists for this client"
            ) from exc

        result = record_to_dict(updated)
        assert result is not None
        await _insert_script_config_revision(
            conn,
            script_config_id,
            new_version,
            build_config_snapshot(result),
        )
        return result


async def list_script_config_revisions(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT r.id, r.version, r.created_at
        FROM script_config_revisions r
        JOIN script_configs sc ON sc.id = r.script_config_id
        WHERE r.script_config_id = $1 AND sc.client_id = $2
        ORDER BY r.version DESC
        """,
        script_config_id,
        client_id,
    )
    return records_to_dicts(rows)


async def get_script_config_revision(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
    version: int,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT r.*
        FROM script_config_revisions r
        JOIN script_configs sc ON sc.id = r.script_config_id
        WHERE r.script_config_id = $1 AND sc.client_id = $2 AND r.version = $3
        """,
        script_config_id,
        client_id,
        version,
    )
    return record_to_dict(row)


async def rollback_script_config(
    pool: asyncpg.Pool,
    script_config_id: UUID,
    client_id: UUID,
    target_version: int,
) -> dict:
    from api.script_config_validation import build_config_snapshot

    rev = await get_script_config_revision(
        pool, script_config_id, client_id, target_version
    )
    if rev is None:
        raise ValueError(f"revision version {target_version} not found")

    snapshot = rev.get("config_snapshot")
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    if not isinstance(snapshot, dict):
        raise ValueError("revision config_snapshot is invalid")

    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
                SELECT * FROM script_configs
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
            script_config_id,
            client_id,
        )
        if row is None:
            raise ValueError("script_config not found")

        current = record_to_dict(row)
        assert current is not None
        new_version = int(current.get("version") or 1) + 1

        sets: list[str] = ["version = $1", "updated_at = NOW()"]
        args: list[Any] = [new_version]
        idx = 2

        for key in sorted(_SCRIPT_CONFIG_PATCHABLE):
            if key not in snapshot:
                continue
            val = snapshot[key]
            if key in _SCRIPT_CONFIG_JSONB:
                sets.append(f"{key} = ${idx}::jsonb")
                args.append(_script_config_json(val))
            elif key == "gemini_temperature":
                sets.append(f"{key} = ${idx}")
                args.append(float(val))
            elif key in (
                "vad_silence_duration_ms",
                "vad_prefix_padding_ms",
            ):
                sets.append(f"{key} = ${idx}")
                args.append(int(val))
            else:
                sets.append(f"{key} = ${idx}")
                args.append(val)
            idx += 1

        args.extend([script_config_id, client_id])
        updated = await conn.fetchrow(
            f"""
                UPDATE script_configs
                SET {", ".join(sets)}
                WHERE id = ${idx} AND client_id = ${idx + 1}
                RETURNING *
                """,
            *args,
        )
        result = record_to_dict(updated)
        assert result is not None
        await _insert_script_config_revision(
            conn,
            script_config_id,
            new_version,
            build_config_snapshot(result),
        )
        return result


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


async def list_campaigns(
    pool: asyncpg.Pool,
    client_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM campaigns
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        client_id,
        limit,
        offset,
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
    async with pool.acquire() as conn, conn.transaction():
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


async def adjust_budget_used(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    delta: Decimal | float,
) -> None:
    amount = Decimal(str(delta))
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


async def increment_budget_used(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    credits_charged: Decimal | float,
) -> None:
    await adjust_budget_used(conn, campaign_id, client_id, credits_charged)


async def reserve_campaign_budget(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    amount: Decimal | float,
) -> None:
    amt = Decimal(str(amount or 0))
    if amt <= 0:
        return
    await adjust_budget_used(conn, campaign_id, client_id, amt)


async def release_campaign_budget_reservation(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    amount: Decimal | float,
) -> None:
    amt = Decimal(str(amount or 0))
    if amt <= 0:
        return
    await adjust_budget_used(conn, campaign_id, client_id, -amt)


async def campaign_reservation_credits(
    pool_or_conn: asyncpg.Pool | asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> Decimal:
    """Claim-time R for this campaign's bot (setup + rate × 2 minutes)."""
    from billing import reservation_credits

    row = await pool_or_conn.fetchrow(
        """
        SELECT b.credits_per_minute, b.fixed_start_credits
        FROM campaigns c
        JOIN bot_configs b ON b.id = c.bot_config_id
        WHERE c.id = $1 AND c.client_id = $2
        """,
        campaign_id,
        client_id,
    )
    if row is None:
        raise ValueError(f"Campaign not found: {campaign_id}")
    return reservation_credits(row["fixed_start_credits"], row["credits_per_minute"])


def parse_call_data(call_data: Any) -> dict:
    if call_data is None:
        return {}
    if isinstance(call_data, str):
        try:
            call_data = json.loads(call_data)
        except json.JSONDecodeError:
            return {}
    if not isinstance(call_data, dict):
        return {}
    return call_data


def budget_reserved_from_call_data(call_data: Any) -> Decimal:
    data = parse_call_data(call_data)
    return Decimal(str(data.get("budget_reserved_credits") or 0))


def is_test_call_data(call_data: Any) -> bool:
    return bool(parse_call_data(call_data).get("is_test_call"))


def billing_rates_from_call_data(
    call_data: Any,
) -> tuple[Decimal | None, Decimal | None]:
    data = parse_call_data(call_data)
    rate_raw = data.get("credits_per_minute")
    setup_raw = data.get("fixed_start_credits")
    rate = Decimal(str(rate_raw)) if rate_raw is not None else None
    setup = Decimal(str(setup_raw)) if setup_raw is not None else None
    return rate, setup


async def settle_call_budget(
    conn: asyncpg.Connection,
    campaign_id: UUID | str,
    client_id: UUID | str,
    credits_charged: Decimal | float,
    budget_reserved_credits: Decimal | float,
) -> bool:
    """Apply charged − reserved. Returns True if budget_used exceeded budget.

    ``credits_charged`` here is the 2 dp campaign/wallet amount.
    """
    reserved = Decimal(str(budget_reserved_credits or 0))
    charged = Decimal(str(credits_charged or 0))
    delta = charged - reserved
    await adjust_budget_used(conn, campaign_id, client_id, delta)

    row = await conn.fetchrow(
        """
        SELECT budget_credits, budget_used_credits
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )
    if row is None:
        return False
    used = Decimal(str(row["budget_used_credits"]))
    cap = Decimal(str(row["budget_credits"]))
    if used <= cap:
        return False

    overflow = used - cap
    bal_row = await conn.fetchrow(
        """
        SELECT balance_credits FROM clients
        WHERE id = $1
        FOR UPDATE
        """,
        client_id,
    )
    balance = Decimal(str(bal_row["balance_credits"] if bal_row else 0))
    new_bal = max(Decimal("0"), balance - overflow)
    taken = balance - new_bal
    await conn.execute(
        "UPDATE clients SET balance_credits = $1 WHERE id = $2",
        new_bal,
        client_id,
    )
    await conn.execute(
        """
        INSERT INTO credit_transactions (client_id, amount, note)
        VALUES ($1, $2, $3)
        """,
        client_id,
        -taken,
        f"Campaign overspend {campaign_id}",
    )
    return True


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
        return Decimal(0), False

    if final_status == "cancelled":
        has_calling_leads = await conn.fetchval(
            """
            SELECT 1 FROM leads
            WHERE campaign_id = $1 AND client_id = $2
              AND status = 'calling'
            LIMIT 1
            """,
            campaign_id,
            client_id,
        )
        if has_calling_leads:
            await conn.execute(
                """
                UPDATE campaigns SET status = 'cancelled'
                WHERE id = $1 AND client_id = $2
                  AND status NOT IN ('completed', 'cancelled')
                """,
                campaign_id,
                client_id,
            )
            return Decimal(0), False

    if final_status == "completed":
        has_active_leads = await conn.fetchval(
            """
            SELECT 1 FROM leads
            WHERE campaign_id = $1 AND client_id = $2
              AND status IN ('pending', 'callback_scheduled', 'calling')
            LIMIT 1
            """,
            campaign_id,
            client_id,
        )
        if has_active_leads:
            return Decimal(0), False
        if row["status"] != "running":
            return Decimal(0), False

    budget = Decimal(str(row["budget_credits"]))
    used = Decimal(str(row["budget_used_credits"]))
    unused = max(budget - used, Decimal(0))

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
        return Decimal(0), False
    pending = int(row["pending_leads"] or 0)
    callback = int(row["callback_leads"] or 0)
    calling = int(row["calling_leads"] or 0)
    if pending > 0 or callback > 0 or calling > 0:
        return Decimal(0), False
    status = row["status"]
    if status == "running":
        return await try_settle_campaign_budget(
            campaign_id, client_id, final_status="completed", conn=conn
        )
    if status == "cancelled":
        return await try_settle_campaign_budget(
            campaign_id, client_id, final_status="cancelled", conn=conn
        )
    return Decimal(0), False


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
    async with pool.acquire() as acquired, acquired.transaction():
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
            lead_status = lead.get("status", "pending")
            result = await conn.execute(
                """
                INSERT INTO leads (
                    client_id, campaign_id, phone, name, lead_type,
                    status, max_attempts, next_attempt_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($9::timestamptz, NOW()), $8::jsonb)
                ON CONFLICT (campaign_id, phone) DO NOTHING
                """,
                lead["client_id"],
                lead["campaign_id"],
                lead["phone"],
                lead.get("name"),
                lead.get("lead_type", "cold"),
                lead_status,
                lead.get("max_attempts", 3),
                meta,
                lead.get("next_attempt_at"),
            )
            if result.split()[-1] == "1":
                inserted += 1
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
            camp = await conn.fetchrow(
                """
                SELECT c.budget_credits, c.budget_used_credits,
                       b.credits_per_minute, b.fixed_start_credits
                FROM campaigns c
                JOIN bot_configs b ON b.id = c.bot_config_id
                WHERE c.id = $1 AND c.client_id = $2
                FOR UPDATE OF c
                """,
                campaign_id,
                client_id,
            )
            if camp is None:
                raise ValueError(f"Campaign not found: {campaign_id}")

            from billing import reservation_credits

            rate = Decimal(str(camp["credits_per_minute"]))
            setup = Decimal(str(camp["fixed_start_credits"]))
            r_reserve = reservation_credits(setup, rate)

            remaining = Decimal(str(camp["budget_credits"])) - Decimal(
                str(camp["budget_used_credits"])
            )
            if r_reserve > 0:
                budget_slots = int(remaining // r_reserve)
            else:
                budget_slots = slots
            effective_slots = min(slots, budget_slots)
            if effective_slots <= 0:
                return []

            rows = await conn.fetch(
                """
                SELECT id, phone, name, metadata, lead_type, attempts, max_attempts, status
                FROM leads
                WHERE campaign_id = $1
                  AND client_id = $2
                  AND status IN ('pending', 'callback_scheduled')
                  AND attempts < max_attempts
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
                effective_slots,
                live_call_grace_minutes(),
                post_call_wrap_grace_minutes(),
            )
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            await conn.execute(
                """
                UPDATE leads SET status = 'calling', last_attempted_at = NOW(), attempts = attempts + 1
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
            await reserve_campaign_budget(
                conn, campaign_id, client_id, r_reserve * len(rows)
            )
            leads = records_to_dicts(rows)
            for lead in leads:
                lead["budget_reserved_credits"] = float(r_reserve)
                lead["credits_per_minute"] = float(rate)
                lead["fixed_start_credits"] = float(setup)
            return leads


async def release_stuck_calling_leads(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    ignore_wrap_grace: bool = False,
) -> int:
    """
    Reset leads left in ``calling`` (no live call) back to ``callback_scheduled``.
    Fixes denorm counters. Returns number of leads released.
    """
    await finalize_stale_in_progress_call_logs(pool, campaign_id, client_id)
    await finalize_orphaned_in_progress_call_logs(pool, campaign_id, client_id)
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    orphan = orphaned_dial_minutes()
    live_sid_guard_4 = """
                       AND (
                         (c.call_sid IS NOT NULL AND c.call_sid <> '')
                         OR c.started_at > NOW() - ($4 * INTERVAL '1 minute')
                       )"""
    live_sid_guard_5 = """
                       AND (
                         (c.call_sid IS NOT NULL AND c.call_sid <> '')
                         OR c.started_at > NOW() - ($5 * INTERVAL '1 minute')
                       )"""
    live_block_4 = """
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = l.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                      AND (
                        (c.call_sid IS NOT NULL AND c.call_sid <> '')
                        OR c.started_at > NOW() - ($4 * INTERVAL '1 minute')
                      )"""
    live_block_5 = """
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = l.id AND c.in_progress = TRUE
                      AND c.started_at > NOW() - ($3 * INTERVAL '1 minute')
                      AND (
                        (c.call_sid IS NOT NULL AND c.call_sid <> '')
                        OR c.started_at > NOW() - ($5 * INTERVAL '1 minute')
                      )"""
    wrap_clause = (
        ""
        if ignore_wrap_grace
        else """
                       EXISTS (
                         SELECT 1 FROM call_logs c
                         WHERE c.lead_id = l.id
                           AND c.ended_at IS NOT NULL
                           AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                       ) AS has_recent_wrap_up"""
    )
    wrap_filter = (
        ""
        if ignore_wrap_grace
        else """
                  AND NOT EXISTS (
                    SELECT 1 FROM call_logs c
                    WHERE c.lead_id = l.id
                      AND c.ended_at IS NOT NULL
                      AND c.ended_at > NOW() - ($4 * INTERVAL '1 minute')
                  )"""
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            if ignore_wrap_grace:
                live_rows = await conn.fetch(
                    f"""
                SELECT l.id AS lead_id,
                       EXISTS (
                         SELECT 1 FROM call_logs c
                         WHERE c.lead_id = l.id AND c.in_progress = TRUE
                           AND c.started_at > NOW() - ($3 * INTERVAL '1 minute'){live_sid_guard_4}
                       ) AS has_live_call,
                       FALSE AS has_recent_wrap_up
                FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                """,
                    campaign_id,
                    client_id,
                    grace,
                    orphan,
                )
            else:
                live_rows = await conn.fetch(
                    f"""
                SELECT l.id AS lead_id,
                       EXISTS (
                         SELECT 1 FROM call_logs c
                         WHERE c.lead_id = l.id AND c.in_progress = TRUE
                           AND c.started_at > NOW() - ($3 * INTERVAL '1 minute'){live_sid_guard_5}
                       ) AS has_live_call,{wrap_clause}
                FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                """,
                    campaign_id,
                    client_id,
                    grace,
                    wrap,
                    orphan,
                )
            if ignore_wrap_grace:
                rows = await conn.fetch(
                    f"""
                SELECT l.id FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                  AND NOT EXISTS (
                    {live_block_4}
                  ){wrap_filter}
                """,
                    campaign_id,
                    client_id,
                    grace,
                    orphan,
                )
            else:
                rows = await conn.fetch(
                    f"""
                SELECT l.id FROM leads l
                WHERE l.campaign_id = $1 AND l.client_id = $2 AND l.status = 'calling'
                  AND NOT EXISTS (
                    {live_block_5}
                  ){wrap_filter}
                """,
                    campaign_id,
                    client_id,
                    grace,
                    wrap,
                    orphan,
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
            lead_rows = await conn.fetch(
                """
                SELECT id, attempts, max_attempts FROM leads
                WHERE id = ANY($1::uuid[]) AND client_id = $2
                FOR UPDATE
                """,
                [r["id"] for r in rows],
                client_id,
            )
            camp = await get_campaign(conn, campaign_id, client_id)
            delay = int(camp.get("retry_delay_minutes") or 120) if camp else 120
            
            failed_count = 0
            callback_count = 0
            
            for lr in lead_rows:
                status, next_at, outcome = resolve_lead_retry_or_failed(
                    int(lr["attempts"] or 0),
                    int(lr["max_attempts"] or 3),
                    delay,
                    base_outcome="Unknown"
                )
                if status == "failed":
                    await conn.execute(
                        """
                        UPDATE leads
                        SET status = 'failed',
                            outcome = COALESCE(NULLIF(TRIM(outcome), ''), $3)
                        WHERE id = $1 AND client_id = $2 AND status = 'calling'
                        """,
                        lr["id"],
                        client_id,
                        outcome,
                    )
                    failed_count += 1
                else:
                    await conn.execute(
                        """
                        UPDATE leads
                        SET status = 'callback_scheduled',
                            outcome = COALESCE(NULLIF(TRIM(outcome), ''), $4),
                            next_attempt_at = COALESCE($3, NOW()),
                            scheduled_callback_at = COALESCE($3, NOW())
                        WHERE id = $1 AND client_id = $2 AND status = 'calling'
                        """,
                        lr["id"],
                        client_id,
                        next_at,
                        outcome,
                    )
                    callback_count += 1
                    
            if failed_count > 0:
                await increment_campaign_counters(
                    conn,
                    campaign_id,
                    from_status="calling",
                    to_status="failed",
                    count=failed_count,
                )
            if callback_count > 0:
                await increment_campaign_counters(
                    conn,
                    campaign_id,
                    from_status="calling",
                    to_status="callback_scheduled",
                    count=callback_count,
                )
            
            ids = [r["id"] for r in rows]
            r_reserve = await campaign_reservation_credits(
                conn, campaign_id, client_id
            )
            await release_campaign_budget_reservation(
                conn, campaign_id, client_id, r_reserve * len(ids)
            )
            return len(rows)


async def finalize_orphaned_in_progress_call_logs(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
    *,
    orphan_minutes: int | None = None,
) -> int:
    """
    Close ``in_progress`` call_logs that never received a Plivo ``call_sid``.
    Returns number settled via settle_unanswered_call.
    """
    mins = orphan_minutes if orphan_minutes is not None else orphaned_dial_minutes()
    rows = await pool.fetch(
        """
        SELECT session_call_id, lead_id, campaign_id, client_id, call_data,
               in_progress, call_sid, started_at
        FROM call_logs
        WHERE campaign_id = $1 AND client_id = $2 AND in_progress = TRUE
          AND (call_sid IS NULL OR call_sid = '')
          AND started_at < NOW() - ($3 * INTERVAL '1 minute')
        """,
        campaign_id,
        client_id,
        mins,
    )
    settled = 0
    for row in rows:
        call_log = record_to_dict(row)
        if call_log and await settle_unanswered_call(
            pool, call_log, retry_delay_minutes=0, base_outcome="Carrier_Failed"
        ):
            settled += 1
    if settled:
        logger.warning(
            "Finalized {} orphaned in_progress call_log(s) for campaign {} "
            "(no call_sid after {} min)",
            settled,
            campaign_id,
            mins,
        )
    return settled


async def release_all_stuck_calling_leads(pool: asyncpg.Pool) -> int:
    """Run release_stuck_calling_leads for all campaigns with calling_leads > 0."""
    rows = await pool.fetch("SELECT DISTINCT campaign_id AS id, client_id FROM leads WHERE status = 'calling'")
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
        WITH lead_counts AS (
            SELECT
                $1::uuid AS campaign_id,
                $2::uuid AS client_id,
                COUNT(*)::int AS total_leads,
                COUNT(*) FILTER (WHERE status = 'pending')::int AS pending_leads,
                COUNT(*) FILTER (WHERE status = 'calling')::int AS calling_leads,
                COUNT(*) FILTER (WHERE status = 'callback_scheduled')::int AS callback_leads,
                COUNT(*) FILTER (WHERE status = 'completed')::int AS completed_leads,
                COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_leads
            FROM leads
            WHERE campaign_id = $1 AND client_id = $2
        )
        UPDATE campaigns c
        SET
            total_leads = lc.total_leads,
            pending_leads = lc.pending_leads,
            calling_leads = lc.calling_leads,
            callback_leads = lc.callback_leads,
            completed_leads = lc.completed_leads,
            failed_leads = lc.failed_leads
        FROM lead_counts lc
        WHERE c.id = lc.campaign_id AND c.client_id = lc.client_id
        RETURNING
            c.total_leads, c.pending_leads, c.calling_leads,
            c.callback_leads, c.completed_leads, c.failed_leads
        """,
        campaign_id,
        client_id,
    )
    if not row:
        return {
            "total_leads": 0,
            "pending_leads": 0,
            "calling_leads": 0,
            "callback_leads": 0,
            "completed_leads": 0,
            "failed_leads": 0,
        }
    
    return {
        "total_leads": int(row["total_leads"] or 0),
        "pending_leads": int(row["pending_leads"] or 0),
        "calling_leads": int(row["calling_leads"] or 0),
        "callback_leads": int(row["callback_leads"] or 0),
        "completed_leads": int(row["completed_leads"] or 0),
        "failed_leads": int(row["failed_leads"] or 0),
    }

async def reconcile_all_campaign_counters(pool: asyncpg.Pool) -> int:
    """Reconcile counters for all running or pausing campaigns."""
    rows = await pool.fetch(
        """
        WITH lead_counts AS (
            SELECT
                c.id AS campaign_id,
                c.client_id,
                COUNT(l.id)::int AS total_leads,
                COUNT(l.id) FILTER (WHERE l.status = 'pending')::int AS pending_leads,
                COUNT(l.id) FILTER (WHERE l.status = 'calling')::int AS calling_leads,
                COUNT(l.id) FILTER (WHERE l.status = 'callback_scheduled')::int AS callback_leads,
                COUNT(l.id) FILTER (WHERE l.status = 'completed')::int AS completed_leads,
                COUNT(l.id) FILTER (WHERE l.status = 'failed')::int AS failed_leads
            FROM campaigns c
            LEFT JOIN leads l ON l.campaign_id = c.id AND l.client_id = c.client_id
            WHERE c.status IN ('running', 'pausing')
            GROUP BY c.id, c.client_id
        )
        UPDATE campaigns c
        SET
            total_leads = lc.total_leads,
            pending_leads = lc.pending_leads,
            calling_leads = lc.calling_leads,
            callback_leads = lc.callback_leads,
            completed_leads = lc.completed_leads,
            failed_leads = lc.failed_leads
        FROM lead_counts lc
        WHERE c.id = lc.campaign_id AND c.client_id = lc.client_id
          AND c.status IN ('running', 'pausing')
          AND (
              c.total_leads != lc.total_leads OR
              c.pending_leads != lc.pending_leads OR
              c.calling_leads != lc.calling_leads OR
              c.callback_leads != lc.callback_leads OR
              c.completed_leads != lc.completed_leads OR
              c.failed_leads != lc.failed_leads
          )
        RETURNING c.id
        """
    )
    return len(rows)


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


async def fetch_premature_recover_lead_for_post_call(
    conn: asyncpg.Connection,
    lead_id: UUID,
    client_id: UUID,
    session_call_id: str,
) -> dict | None:
    """Lock lead wrongly moved to pending by early recover for this session."""
    row = await conn.fetchrow(
        """
        SELECT l.status, l.next_attempt_at, l.scheduled_callback_at
        FROM leads l
        INNER JOIN call_logs cl
            ON cl.lead_id = l.id AND cl.session_call_id = $3
        WHERE l.id = $1 AND l.client_id = $2
          AND l.status = 'pending'
          AND (l.outcome IS NULL OR l.outcome IN (
              'Unknown', 'Busy', 'No_Answer', 'Rejected',
              'Carrier_Failed', 'Wrong_Requirement'
          ))
        FOR UPDATE OF l
        """,
        lead_id,
        client_id,
        session_call_id,
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
    ext_json = extraction
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
            outcome = 'Campaign_Cancelled'
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
            outcome = 'Campaign_Cancelled'
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

    async with pool.acquire() as conn, conn.transaction():
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


async def delete_campaign(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
) -> dict[str, Any]:
    """Hard-delete a campaign, its leads, call logs, and related rows."""
    await finalize_stale_in_progress_call_logs(pool, campaign_id, client_id)
    await release_stuck_calling_leads(pool, campaign_id, client_id)

    credits_returned = Decimal(0)
    async with pool.acquire() as conn, conn.transaction():
        camp = await conn.fetchrow(
            """
            SELECT status, budget_returned_at
            FROM campaigns
            WHERE id = $1 AND client_id = $2
            FOR UPDATE
            """,
            campaign_id,
            client_id,
        )
        if camp is None:
            raise ValueError(f"Campaign not found: {campaign_id}")

        in_progress = await conn.fetchval(
            """
            SELECT COUNT(*)::int FROM call_logs
            WHERE campaign_id = $1 AND client_id = $2 AND in_progress = TRUE
            """,
            campaign_id,
            client_id,
        )
        if in_progress > 0:
            raise ValueError("Cannot delete campaign while calls are in progress")

        if camp["budget_returned_at"] is None and camp["status"] not in (
            "completed",
            "cancelled",
        ):
            await terminalize_campaign_leads(conn, campaign_id, client_id)
            credits_returned, _ = await try_settle_campaign_budget(
                campaign_id,
                client_id,
                final_status="cancelled",
                conn=conn,
            )

        await conn.execute(
            "DELETE FROM call_logs WHERE campaign_id = $1 AND client_id = $2",
            campaign_id,
            client_id,
        )
        deleted = await conn.execute(
            "DELETE FROM campaigns WHERE id = $1 AND client_id = $2",
            campaign_id,
            client_id,
        )
        if deleted == "DELETE 0":
            raise ValueError(f"Campaign not found: {campaign_id}")

    return {
        "deleted": True,
        "campaign_id": str(campaign_id),
        "credits_returned": float(credits_returned),
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
    outcome: str | None = None,
) -> tuple[list[dict], int]:
    """Return a paginated list of leads for a campaign, plus total count."""
    turns_expr = _TRANSCRIPT_TURNS_EXPR.format(alias="call_logs").strip()
    query = f"""
        SELECT l.*,
               lc.session_call_id,
               lc.duration_seconds AS last_call_duration_seconds,
               lc.outcome AS last_call_outcome,
               lc.ended_at AS last_call_ended_at,
               lc.in_progress AS last_call_in_progress,
               lc.transcript_turns,
               lc.plivo_hangup_json->>'hangup_source' AS last_hangup_source,
               COALESCE(lc.turn_count, 0) AS turns
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT session_call_id, duration_seconds, outcome, ended_at, plivo_hangup_json, in_progress,
                   {turns_expr} AS transcript_turns,
                   CASE WHEN jsonb_typeof(transcript) = 'array' THEN jsonb_array_length(transcript) ELSE 0 END AS turn_count
            FROM call_logs
            WHERE lead_id = l.id
            ORDER BY started_at DESC NULLS LAST
            LIMIT 1
        ) lc ON TRUE
        WHERE l.campaign_id = $1 AND l.client_id = $2
    """
    count_query = "SELECT COUNT(*) FROM leads WHERE campaign_id = $1 AND client_id = $2"
    args: list[Any] = [campaign_id, client_id]
    idx = 3

    if status:
        query += f" AND l.status = ${idx}"
        count_query += f" AND status = ${idx}"
        args.append(status)
        idx += 1

    if search:
        search_pattern = f"%{search}%"
        query += f" AND (l.name ILIKE ${idx} OR l.phone ILIKE ${idx})"
        count_query += f" AND (name ILIKE ${idx} OR phone ILIKE ${idx})"
        args.append(search_pattern)
        idx += 1

    if outcome:
        query += f" AND l.outcome = ${idx}"
        count_query += f" AND outcome = ${idx}"
        args.append(outcome)
        idx += 1

    total_count = await pool.fetchval(count_query, *args)
    query += (
        f" ORDER BY"
        f" CASE WHEN l.status = 'calling' THEN 0 ELSE 1 END,"
        f" COALESCE(l.last_attempted_at, l.created_at) DESC NULLS LAST,"
        f" l.created_at DESC"
        f" LIMIT ${idx} OFFSET ${idx + 1}"
    )
    args.extend([limit, offset])

    rows = await pool.fetch(query, *args)
    return records_to_dicts(rows), total_count


async def list_campaign_leads_for_export(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    client_id: UUID,
    status: str | None = None,
    search: str | None = None,
    outcome: str | None = None,
) -> list[dict]:
    """Return all leads for a campaign export (no pagination)."""
    rows, _ = await list_campaign_leads(
        pool,
        campaign_id,
        client_id,
        limit=1_000_000,
        offset=0,
        status=status,
        search=search,
        outcome=outcome,
    )
    return rows

async def list_campaign_outcomes(
    pool: asyncpg.Pool,
    client_id: UUID,
    campaign_id: UUID | str | None = None,
) -> list[str]:
    """Return the outcomes THIS campaign's script can actually produce.

    Resolution order:
      1. campaign -> bot_config (for route/script_id/script_config_id)
      2. bot_config has script_config_id -> read that script_configs row's
         outcome_terminal/outcome_retry/outcome_callback (its customized
         vocabulary for Interested/Not_Interested/Busy/etc.)
      3. bot_config has no script_config_id (raw LEAD_SCHEMA-style script
         module) -> fall back to script_runtime's DEFAULT_OUTCOME_* sets,
         since those scripts don't declare their own outcome sets.
      4. If campaign/bot_config/script_config can't be resolved at all
         (including callers that pass no campaign_id — this keeps the
         client-wide admin lead-outcomes endpoint working as before),
         fall back to call_outcomes.ALL_OUTCOMES (global vocabulary) so the
         dropdown is never empty.

    call_outcomes.SYSTEM_OUTCOMES (No_Answer, Rejected, Carrier_Failed,
    Max_Attempts_Reached, Campaign_Cancelled) is always unioned in, since
    those come from dialer/telephony logic and can happen on any campaign
    regardless of its script's configured outcomes.

    Interested/Not_Interested are always sorted to the front of the
    returned list (see call_outcomes.order_outcomes) since those are the
    two outcomes users care about filtering on most.
    """
    import script_runtime
    from call_outcomes import ALL_OUTCOMES, SYSTEM_OUTCOMES, order_outcomes

    if campaign_id is None:
        return order_outcomes(ALL_OUTCOMES)

    campaign = await get_campaign(pool, campaign_id, client_id)
    if campaign is None or not campaign.get("bot_config_id"):
        return order_outcomes(ALL_OUTCOMES)

    bot = await get_bot_config(pool, UUID(str(campaign["bot_config_id"])), client_id)
    if bot is None:
        return order_outcomes(ALL_OUTCOMES)

    if bot.get("script_config_id"):
        cfg = await get_script_config(pool, bot["script_config_id"], client_id)
        if cfg is None:
            return order_outcomes(ALL_OUTCOMES)
        terminal = cfg.get("outcome_terminal") or script_runtime.DEFAULT_OUTCOME_TERMINAL
        retry = cfg.get("outcome_retry") or script_runtime.DEFAULT_OUTCOME_RETRY
        callback = cfg.get("outcome_callback") or script_runtime.DEFAULT_OUTCOME_CALLBACK
    else:
        terminal = script_runtime.DEFAULT_OUTCOME_TERMINAL
        retry = script_runtime.DEFAULT_OUTCOME_RETRY
        callback = script_runtime.DEFAULT_OUTCOME_CALLBACK

    outcomes = set(terminal) | set(retry) | set(callback) | SYSTEM_OUTCOMES
    return order_outcomes(outcomes)

_LEAD_SORT_COLUMNS = {
    "created_at": "l.created_at",
    "name": "l.name",
    "status": "l.status",
    "attempts": "l.attempts",
    "updated_at": "l.updated_at",
}



async def list_client_leads(
    pool: asyncpg.Pool,
    client_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    campaign_id: UUID | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[dict], int]:
    """Return paginated leads across all campaigns for a client."""
    sort_col = _LEAD_SORT_COLUMNS.get(sort, "l.created_at")
    order_dir = "ASC" if (order or "").lower() == "asc" else "DESC"

    query = """
        SELECT l.*,
               c.name AS campaign_name,
               lc.duration_seconds AS last_call_duration_seconds,
               lc.outcome AS last_call_outcome,
               lc.ended_at AS last_call_ended_at,
               lc.plivo_hangup_json->>'hangup_source' AS last_hangup_source
        FROM leads l
        JOIN campaigns c ON c.id = l.campaign_id
        LEFT JOIN LATERAL (
            SELECT duration_seconds, outcome, ended_at, plivo_hangup_json
            FROM call_logs
            WHERE lead_id = l.id AND ended_at IS NOT NULL
            ORDER BY ended_at DESC
            LIMIT 1
        ) lc ON TRUE
        WHERE l.client_id = $1
    """
    count_query = "SELECT COUNT(*) FROM leads l WHERE l.client_id = $1"
    args: list[Any] = [client_id]
    idx = 2

    if campaign_id:
        query += f" AND l.campaign_id = ${idx}"
        count_query += f" AND l.campaign_id = ${idx}"
        args.append(campaign_id)
        idx += 1

    if status:
        query += f" AND l.status = ${idx}"
        count_query += f" AND l.status = ${idx}"
        args.append(status)
        idx += 1

    if search:
        search_pattern = f"%{search}%"
        search_clause = (
            f" AND (l.name ILIKE ${idx} OR l.phone ILIKE ${idx} OR c.name ILIKE ${idx}"
            f" OR COALESCE(l.metadata->>'email', '') ILIKE ${idx}"
            f" OR COALESCE(l.metadata->>'company', '') ILIKE ${idx})"
        )
        query += search_clause
        count_query += (
            f" AND (l.name ILIKE ${idx} OR l.phone ILIKE ${idx}"
            f" OR COALESCE(l.metadata->>'email', '') ILIKE ${idx}"
            f" OR COALESCE(l.metadata->>'company', '') ILIKE ${idx}"
            f" OR EXISTS (SELECT 1 FROM campaigns c2 WHERE c2.id = l.campaign_id AND c2.name ILIKE ${idx}))"
        )
        args.append(search_pattern)
        idx += 1

    total_count = await pool.fetchval(count_query, *args)
    query += f" ORDER BY {sort_col} {order_dir} LIMIT ${idx} OFFSET ${idx + 1}"
    args.extend([limit, offset])

    rows = await pool.fetch(query, *args)
    return records_to_dicts(rows), total_count


async def get_client_lead_stats(
    pool: asyncpg.Pool,
    client_id: UUID,
    campaign_id: UUID | None = None,
) -> dict:
    """Aggregate lead counters for the client lead sheet KPI strip."""
    args: list[Any] = [client_id]
    campaign_filter = ""
    if campaign_id:
        campaign_filter = " AND campaign_id = $2"
        args.append(campaign_id)

    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::int AS uploaded,
            COUNT(*) FILTER (WHERE status = 'pending')::int AS pending,
            COUNT(*) FILTER (WHERE status = 'callback_scheduled')::int AS callback,
            COUNT(*) FILTER (WHERE status = 'completed')::int AS completed,
            COUNT(*) FILTER (WHERE status = 'failed')::int AS failed,
            COUNT(*) FILTER (WHERE status = 'calling')::int AS calling,
            COUNT(*) FILTER (WHERE outcome = 'Interested')::int AS interested
        FROM leads
        WHERE client_id = $1{campaign_filter}
        """,
        *args,
    )
    return dict(row) if row else {
        "uploaded": 0,
        "pending": 0,
        "callback": 0,
        "completed": 0,
        "failed": 0,
        "calling": 0,
        "interested": 0,
    }


async def get_campaign_outcome_stats(
    pool: asyncpg.Pool,
    client_id: UUID,
    campaign_id: UUID,
) -> dict:
    """Outcome and status counters for campaign detail stats.

    Status buckets prefer denormalized ``campaigns`` columns; outcome buckets
    still scan ``leads``. Results are cached for ``_STATS_CACHE_TTL_S``.
    """
    cache_key = f"{client_id}:{campaign_id}"
    cached = _outcome_stats_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _STATS_CACHE_TTL_S:
        return dict(cached[1])

    camp = await pool.fetchrow(
        """
        SELECT total_leads, pending_leads, calling_leads, callback_leads,
               completed_leads, failed_leads
        FROM campaigns
        WHERE id = $1 AND client_id = $2
        """,
        campaign_id,
        client_id,
    )
    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE outcome = 'Interested')::int AS interested_leads,
            COUNT(*) FILTER (WHERE outcome = 'Not_Interested')::int AS not_interested_leads,
            COUNT(*) FILTER (
                WHERE outcome IN ('Interested', 'Not_Interested', 'Early_Disconnect', 'Wrong_Requirement')
            )::int AS answered_leads,
            COUNT(*) FILTER (
                WHERE outcome IN ('No_Answer', 'Busy', 'Rejected', 'Carrier_Failed')
            )::int AS not_answered_leads,
            COUNT(*) FILTER (WHERE outcome = 'Busy')::int AS busy_leads
        FROM leads
        WHERE client_id = $1 AND campaign_id = $2
        """,
        client_id,
        campaign_id,
    )
    empty = {
        "total_leads": 0,
        "pending_leads": 0,
        "calling_leads": 0,
        "callback_leads": 0,
        "completed_leads": 0,
        "failed_leads": 0,
        "interested_leads": 0,
        "not_interested_leads": 0,
        "answered_leads": 0,
        "not_answered_leads": 0,
        "busy_leads": 0,
        "conversion_rate": None,
    }
    if not camp and not row:
        return empty

    stats = dict(empty)
    if camp:
        for key in (
            "total_leads",
            "pending_leads",
            "calling_leads",
            "callback_leads",
            "completed_leads",
            "failed_leads",
        ):
            stats[key] = int(camp.get(key) or 0)
    if row:
        for key in (
            "interested_leads",
            "not_interested_leads",
            "answered_leads",
            "not_answered_leads",
            "busy_leads",
        ):
            stats[key] = int(row.get(key) or 0)

    total = int(stats.get("total_leads") or 0)
    interested = int(stats.get("interested_leads") or 0)
    stats["conversion_rate"] = round((interested / total) * 100, 2) if total > 0 else None
    _outcome_stats_cache[cache_key] = (time.monotonic(), dict(stats))
    return stats


async def get_campaigns_interested_counts(
    pool: asyncpg.Pool,
    client_id: UUID,
) -> dict[str, int]:
    """Map campaign_id → interested lead count for list views."""
    cache_key = str(client_id)
    cached = _interested_counts_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _STATS_CACHE_TTL_S:
        return dict(cached[1])

    rows = await pool.fetch(
        """
        SELECT campaign_id, COUNT(*)::int AS interested_leads
        FROM leads
        WHERE client_id = $1 AND outcome = 'Interested'
        GROUP BY campaign_id
        """,
        client_id,
    )
    result = {str(r["campaign_id"]): int(r["interested_leads"] or 0) for r in rows}
    _interested_counts_cache[cache_key] = (time.monotonic(), dict(result))
    return result


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
        args.append(metadata)
        idx += 1

    if not sets:
        return False

    args.extend([lead_id, client_id])
    result = await pool.execute(
        f"UPDATE leads SET {', '.join(sets)} WHERE id = ${idx} AND client_id = ${idx + 1} AND status != 'calling'",
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
    meta_json = meta
    lead_status = lead.get("status", "pending")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO leads (
                    client_id, campaign_id, phone, name, lead_type,
                    status, max_attempts, next_attempt_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($9::timestamptz, NOW()), $8::jsonb)
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
                lead.get("next_attempt_at"),
            )
            if row is None:
                raise ValueError(
                    f"Duplicate phone {lead['phone']} in this campaign"
                )

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
        "DELETE FROM leads WHERE id = $1 AND campaign_id = $2 AND client_id = $3 AND status != 'calling'",
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
    reset_to_fresh: bool = False,
) -> bool:
    """Manually change a lead's status. Returns True if a row was updated.

    Does NOT reconcile counters — callers should run
    ``reconcile_campaign_counters`` after this.
    """
    if reset_to_fresh:
        result = await pool.execute(
            """
            UPDATE leads
            SET status = $1,
                next_attempt_at = $2,
                scheduled_callback_at = $3,
                attempts = 0,
                outcome = NULL,
                extraction = '{}'::jsonb
            WHERE id = $4 AND client_id = $5 AND status != 'calling'
            """,
            new_status,
            next_attempt_at,
            scheduled_callback_at,
            lead_id,
            client_id,
        )
    else:
        result = await pool.execute(
            """
            UPDATE leads
            SET status = $1,
                next_attempt_at = $2,
                scheduled_callback_at = $3
            WHERE id = $4 AND client_id = $5 AND status != 'calling'
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
    call_data: dict | None = None,
    is_test_call: bool = False,
    budget_reserved_credits: Decimal | float = 0,
    credits_per_minute: Decimal | float | None = None,
    fixed_start_credits: Decimal | float | None = None,
) -> UUID:
    grace = live_call_grace_minutes()
    wrap = post_call_wrap_grace_minutes()
    
    # We use an advisory lock on the lead_id to strictly prevent concurrent duplicate dials
    # (Since UUIDs are 128-bit, we take a lock on the first 64 bits)
    lock_id = None
    if lead_id:
        lock_id = int.from_bytes(lead_id.bytes[:8], 'big') - 2**63

    async with pool.acquire() as conn, conn.transaction():
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

        data = dict(call_data) if call_data else {}
        if is_test_call:
            data["is_test_call"] = True
        reserved = Decimal(str(budget_reserved_credits or 0))
        if reserved > 0:
            data["budget_reserved_credits"] = float(reserved)
        if credits_per_minute is not None:
            data["credits_per_minute"] = float(Decimal(str(credits_per_minute)))
        if fixed_start_credits is not None:
            data["fixed_start_credits"] = float(Decimal(str(fixed_start_credits)))

        row = await conn.fetchrow(
            """
                INSERT INTO call_logs (
                    session_call_id, client_id, campaign_id, lead_id,
                    bot_config_id, route, started_at, in_progress, transcript,
                    call_data
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, '[]'::jsonb, $8::jsonb)
                RETURNING id
                """,
            session_call_id,
            client_id,
            campaign_id,
            lead_id,
            bot_config_id,
            route,
            started_at,
            data,
        )
        return row["id"]


async def patch_call_log_post_call_snapshot(
    pool: asyncpg.Pool,
    session_call_id: str,
    snapshot_wrapper: dict,
) -> bool:
    """Merge post_call_snapshot into call_data if not already set (idempotent)."""
    if not session_call_id or not snapshot_wrapper:
        return False
    row = await pool.fetchrow(
        """
        UPDATE call_logs
        SET call_data = call_data || $2::jsonb
        WHERE session_call_id = $1
          AND (call_data->'post_call_snapshot') IS NULL
        RETURNING id
        """,
        session_call_id,
        snapshot_wrapper,
    )
    return row is not None


async def mark_call_log_not_in_progress(
    pool: asyncpg.Pool,
    session_call_id: str,
    *,
    set_credits_charged_zero: bool = False,
) -> bool:
    """Clear live flag as soon as the pipeline ends (before post-call extraction).

    When ``set_credits_charged_zero`` is True (Plivo never accepted the dial),
    write credits_charged = 0 so later settle paths do not bill setup. The
    caller still refunds the reservation via ``_release_lead_to_pending``.
    """
    if set_credits_charged_zero:
        sql = """
            UPDATE call_logs SET
                in_progress = FALSE,
                ended_at = COALESCE(ended_at, NOW()),
                credits_charged = 0,
                billed_minutes = 0
            WHERE session_call_id = $1 AND in_progress = TRUE
            RETURNING id
            """
    else:
        sql = """
            UPDATE call_logs SET
                in_progress = FALSE,
                ended_at = COALESCE(ended_at, NOW())
            WHERE session_call_id = $1 AND in_progress = TRUE
            RETURNING id
            """
    row = await pool.fetchrow(sql, session_call_id)
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


async def call_log_in_progress(
    pool: asyncpg.Pool,
    session_call_id: str,
) -> bool:
    """Lightweight check used by /ws teardown (avoids SELECT * + transcript)."""
    row = await pool.fetchval(
        """
        SELECT in_progress FROM call_logs
        WHERE session_call_id = $1
        """,
        session_call_id,
    )
    return bool(row)


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
    import json
    blob = json.dumps(stored)
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
    Record callee hangup metadata only.

    Lead status is updated by post-call extraction (or settle_unanswered_call),
    not here — preemptive callback_scheduled caused wrong badges and bypassed
    max-attempts logic.
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
    if not isinstance(existing, dict):
        existing = {}
    if existing.get("hangup_processed_at"):
        return bool(existing.get("callback_applied"))

    session_call_id = call_log.get("session_call_id")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE call_logs SET plivo_hangup_json = plivo_hangup_json || $2::jsonb
            WHERE session_call_id = $1
            """,
            session_call_id,
            {
                "hangup_processed_at": datetime.now(UTC).isoformat(),
                "callback_applied": False,
                "callee_hangup_recorded": True,
            },
        )
    return False


async def terminalize_exhausted_leads(
    pool: asyncpg.Pool,
    campaign_id: UUID | str,
    client_id: UUID | str,
) -> int:
    """Mark pending/callback leads as failed when attempts >= max_attempts."""
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(
            """
                SELECT id, status FROM leads
                WHERE campaign_id = $1 AND client_id = $2
                  AND status IN ('pending', 'callback_scheduled')
                  AND attempts >= max_attempts
                FOR UPDATE
                """,
            campaign_id,
            client_id,
        )
        if not rows:
            return 0
        new_status, _, outcome = resolve_lead_retry_or_failed(1, 1, 0)
        ids = [r["id"] for r in rows]
        await conn.execute(
            """
                UPDATE leads
                SET status = $3,
                    outcome = COALESCE(NULLIF(TRIM(outcome), ''), $4)
                WHERE id = ANY($1::uuid[]) AND client_id = $2
                """,
            ids,
            client_id,
            new_status,
            outcome,
        )
        for r in rows:
            await increment_campaign_counters(
                conn,
                UUID(str(campaign_id)),
                from_status=r["status"],
                to_status=new_status,
            )
        return len(rows)


async def settle_unanswered_call(
    pool: asyncpg.Pool,
    call_log: dict,
    *,
    retry_delay_minutes: int,
    base_outcome: str,
    charge_setup: bool = False,
) -> bool:
    """Settle budget and release lead for calls that were never answered.

    Handles BUSY, NO_ANSWER, REJECTED, and provider-error hangups.
    Never charges — only connected (picked-up) calls bill via post-call.
    ``charge_setup`` is ignored and kept for call-site compatibility.
    The claim reservation is fully refunded (delta settle to ₹0).
    """
    del charge_setup  # unanswered dials are always free
    session_call_id = call_log.get("session_call_id")
    lead_id = call_log.get("lead_id")
    campaign_id = call_log.get("campaign_id")
    client_id = call_log.get("client_id")
    if not session_call_id or not lead_id or not campaign_id or not client_id:
        return False

    data = parse_call_data(call_log.get("call_data"))
    reserved = budget_reserved_from_call_data(data)

    charged_4 = Decimal("0")
    budget_amt = Decimal("0")
    setup_charge = Decimal("0")
    duration_charge = Decimal("0")

    async with pool.acquire() as conn, conn.transaction():
        lead_row = await conn.fetchrow(
            """
                SELECT status, attempts, max_attempts FROM leads
                WHERE id = $1 AND client_id = $2
                FOR UPDATE
                """,
            UUID(str(lead_id)),
            UUID(str(client_id)),
        )
        if not lead_row or lead_row["status"] != "calling":
            return False

        attempts = int(lead_row["attempts"] or 0)
        max_att = int(lead_row["max_attempts"] or 3)
        new_status, next_at, outcome = resolve_lead_retry_or_failed(
            attempts,
            max_att,
            retry_delay_minutes,
            base_outcome=base_outcome,
        )

        # Mark call_log as done — unanswered = ₹0 (reservation refunded below)
        charge_patch = json.dumps({
            "setup_charge": float(setup_charge),
            "duration_charge": float(duration_charge),
        })
        result = await conn.execute(
            """
                UPDATE call_logs
                SET in_progress = FALSE,
                    ended_at = COALESCE(ended_at, NOW()),
                    credits_charged = $3,
                    billed_minutes = 0,
                    outcome = COALESCE(NULLIF(TRIM(outcome), ''), $2),
                    call_data = COALESCE(call_data, '{}'::jsonb) || $4::jsonb
                WHERE session_call_id = $1 AND in_progress = TRUE
                """,
            session_call_id,
            outcome,
            charged_4,
            charge_patch,
        )
        if result.split()[-1] == "0":
            # Already finalized by another path
            return False

        if reserved > 0 or budget_amt > 0:
            await settle_call_budget(
                conn,
                UUID(str(campaign_id)),
                UUID(str(client_id)),
                budget_amt,
                reserved,
            )

        sched_cb = next_at if new_status == "callback_scheduled" else None

        await conn.execute(
            """
                UPDATE leads
                SET status = $3,
                    outcome = $5,
                    next_attempt_at = COALESCE($4, next_attempt_at),
                    scheduled_callback_at = $6
                WHERE id = $1 AND client_id = $2 AND status = 'calling'
                """,
            UUID(str(lead_id)),
            UUID(str(client_id)),
            new_status,
            next_at,
            outcome,
            sched_cb,
        )
        await increment_campaign_counters(
            conn,
            UUID(str(campaign_id)),
            from_status="calling",
            to_status=new_status,
        )

    logger.info(
        "Settled unanswered call session={} lead={} campaign={} reserved={}",
        session_call_id,
        lead_id,
        campaign_id,
        reserved,
    )
    return True


async def append_transcript_turn(
    pool: asyncpg.Pool,
    session_call_id: str,
    role: str,
    content: str,
    ts: datetime,
) -> None:
    """Deprecated: prefer ``replace_transcript`` with a full in-memory snapshot."""
    turn = [{"role": role, "content": content, "ts": ts.isoformat()}]
    await pool.execute(
        """
        UPDATE call_logs
        SET transcript = transcript || $1::jsonb
        WHERE session_call_id = $2 AND in_progress = TRUE
        """,
        turn,
        session_call_id,
    )


async def replace_transcript(
    pool: asyncpg.Pool,
    session_call_id: str,
    transcript: list[dict],
) -> None:
    """Replace the live transcript JSONB with a full in-memory snapshot."""
    await pool.execute(
        """
        UPDATE call_logs
        SET transcript = $1::jsonb
        WHERE session_call_id = $2 AND in_progress = TRUE
        """,
        transcript,
        session_call_id,
    )


async def finalize_call_log(
    pool_or_conn: asyncpg.Pool | asyncpg.Connection,
    session_call_id: str,
    duration_seconds: int,
    outcome: str,
    extraction_json: dict,
    billed_minutes: Decimal | float,
    credits_charged: Decimal | float,
    usage: dict,
    *,
    transcript: list[dict] | None = None,
    extraction_model: str | None = None,
    extraction_error: str | None = None,
    qualified: bool | None = None,
    setup_charge: Decimal | float | None = None,
    duration_charge: Decimal | float | None = None,
) -> None:
    ext = extraction_json or {}
    qual = qualified if qualified is not None else (outcome == "Interested")
    transcript_json = transcript
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
            extraction_error = $12,
            call_data = COALESCE(call_data, '{}'::jsonb) || $13::jsonb
    """
    charge_patch: dict[str, float] = {}
    if setup_charge is not None:
        charge_patch["setup_charge"] = float(Decimal(str(setup_charge)))
    if duration_charge is not None:
        charge_patch["duration_charge"] = float(Decimal(str(duration_charge)))
    args: list[Any] = [
        duration_seconds,
        billed_minutes if isinstance(billed_minutes, Decimal) else Decimal(str(billed_minutes)),
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
        json.dumps(charge_patch),
    ]
    if transcript_json is not None:
        sql += ", transcript = $14::jsonb WHERE session_call_id = $15"
        args.extend([transcript_json, session_call_id])
    else:
        sql += " WHERE session_call_id = $14"
        args.append(session_call_id)

    if isinstance(pool_or_conn, asyncpg.Pool):
        await pool_or_conn.execute(sql, *args)
    else:
        await pool_or_conn.execute(sql, *args)


async def get_call_log(
    pool: asyncpg.Pool,
    session_call_id: str,
    client_id: UUID,
) -> dict | None:
    """Fetch a single call by session id (includes test calls — detail view)."""
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
    """Latest call for a lead (includes test calls — detail / drawer)."""
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
    limit: int = 2000,
    offset: int = 0,
    search: str | None = None,
    campaign_id: UUID | None = None,
) -> tuple[list[dict], int]:
    """
    Return call list rows by recency without heavy JSONB blobs.

    Excludes transcript, call_data, extraction_json, plivo_hangup_json —
    fetch those via get_call_log / detail endpoints.
    """
    base_query = "FROM call_logs cl LEFT JOIN leads l ON cl.lead_id = l.id"
    conditions = []
    args = []
    idx = 1
    
    if client_id is not None:
        conditions.append(f"cl.client_id = ${idx}")
        args.append(client_id)
        idx += 1
        conditions.append("(cl.call_data->>'is_test_call' IS NULL OR cl.call_data->>'is_test_call' != 'true')")

    if campaign_id is not None:
        conditions.append(f"cl.campaign_id = ${idx}")
        args.append(campaign_id)
        idx += 1
        
    if search:
        search_pattern = f"%{search}%"
        conditions.append(f"(cl.session_call_id ILIKE ${idx} OR cl.outcome ILIKE ${idx} OR l.name ILIKE ${idx} OR l.phone ILIKE ${idx})")
        args.append(search_pattern)
        idx += 1
        
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    
    total = await pool.fetchval(f"SELECT COUNT(*) {base_query} {where_clause}", *args)
    
    args.extend([limit, offset])
    turns_expr = _TRANSCRIPT_TURNS_EXPR.format(alias="cl").strip()
    rows = await pool.fetch(
        f"""
        SELECT
            cl.id, cl.session_call_id, cl.client_id, cl.campaign_id,
            cl.lead_id, cl.bot_config_id, cl.route, cl.call_sid,
            cl.started_at, cl.ended_at, cl.created_at,
            cl.in_progress, cl.duration_seconds, cl.billed_minutes,
            cl.credits_charged, cl.outcome, cl.qualified,
            (cl.call_data->>'setup_charge')::numeric AS setup_charge,
            (cl.call_data->>'duration_charge')::numeric AS duration_charge,
            cl.usage_prompt_tokens, cl.usage_completion_tokens,
            cl.usage_total_tokens, cl.usage_tts_characters,
            cl.recording_url, cl.extraction_model, cl.extraction_error,
            cl.cost_usd, cl.quality_score, cl.flagged_for_review,
            {turns_expr} AS transcript_turns,
            CASE WHEN jsonb_typeof(transcript) = 'array' THEN jsonb_array_length(transcript) ELSE 0 END AS turns,
            l.name, l.phone
        {base_query} {where_clause}
        ORDER BY cl.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *args
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
            if delta > 0:
                parts.append(f"{col} = {col} + ${idx}")
            else:
                parts.append(f"{col} = GREATEST(0, {col} - ${idx})")
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


async def update_call_log_recording_url(
    pool, session_call_id: str, recording_url: str
) -> bool:
    """Store the R2 object key (or local path) on the call_log row."""
    result = await pool.execute(
        "UPDATE call_logs SET recording_url = $1 WHERE session_call_id = $2",
        recording_url,
        session_call_id,
    )
    return result == "UPDATE 1"

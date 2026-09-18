"""n8n integration repository helpers (thin wrappers)."""

from __future__ import annotations

from uuid import UUID

from db.postgres import record_to_dict, records_to_dicts


async def list_webhook_configs(pool, *, client_id: UUID | None = None) -> list[dict]:
    if client_id is None:
        rows = await pool.fetch("SELECT * FROM webhook_configs ORDER BY updated_at DESC NULLS LAST")
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM webhook_configs
            WHERE client_id = $1
            ORDER BY updated_at DESC NULLS LAST
            """,
            client_id,
        )
    return records_to_dicts(rows)


async def get_webhook_config(pool, webhook_id: UUID) -> dict | None:
    row = await pool.fetchrow("SELECT * FROM webhook_configs WHERE id = $1", webhook_id)
    return record_to_dict(row) if row else None

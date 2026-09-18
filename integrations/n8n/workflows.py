"""Persisted n8n workflow registry (admin CRUD)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from db.postgres import record_to_dict, records_to_dicts


class WorkflowError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def list_workflows(pool) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM n8n_workflows
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
        """
    )
    return records_to_dicts(rows)


async def get_workflow(pool, workflow_id: UUID) -> dict | None:
    row = await pool.fetchrow("SELECT * FROM n8n_workflows WHERE id = $1", workflow_id)
    return record_to_dict(row) if row else None


async def create_workflow(
    pool,
    *,
    name: str,
    webhook_url: str,
    description: str | None = None,
    enabled: bool | None = True,
) -> dict:
    name = (name or "").strip()
    url = (webhook_url or "").strip()
    if not name:
        raise WorkflowError("invalid", "Workflow name is required")
    if not url.startswith("http"):
        raise WorkflowError("invalid", "Webhook URL must be http(s)")
    row = await pool.fetchrow(
        """
        INSERT INTO n8n_workflows (name, webhook_url, description, enabled)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        name,
        url,
        description,
        True if enabled is None else bool(enabled),
    )
    return record_to_dict(row)


async def update_workflow(pool, workflow_id: UUID, *, fields: dict[str, Any]) -> dict | None:
    allowed = {"name", "webhook_url", "description", "enabled"}
    sets: list[str] = []
    args: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        args.append(value)
        sets.append(f"{key} = ${len(args)}")
    if not sets:
        raise WorkflowError("invalid", "No workflow fields to update")
    args.append(workflow_id)
    row = await pool.fetchrow(
        f"""
        UPDATE n8n_workflows
        SET {', '.join(sets)}, updated_at = NOW()
        WHERE id = ${len(args)}
        RETURNING *
        """,
        *args,
    )
    return record_to_dict(row) if row else None


async def delete_workflow(pool, workflow_id: UUID) -> dict | None:
    row = await pool.fetchrow(
        "DELETE FROM n8n_workflows WHERE id = $1 RETURNING *",
        workflow_id,
    )
    return record_to_dict(row) if row else None


async def record_dry_test(pool, workflow_id: UUID) -> dict:
    row = await get_workflow(pool, workflow_id)
    if not row:
        raise WorkflowError("not_found", "Workflow not found")
    await pool.execute(
        """
        UPDATE n8n_workflows
        SET last_tested_at = NOW(), last_test_status = 'dry_run_ok', updated_at = NOW()
        WHERE id = $1
        """,
        workflow_id,
    )
    refreshed = await get_workflow(pool, workflow_id)
    return {"ok": True, "dry_run": True, "workflow": refreshed}

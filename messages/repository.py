"""Postgres access for Messages module — always tenant-scoped by client_id."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from asyncpg.exceptions import UniqueViolationError

from db.postgres import record_to_dict, records_to_dicts


async def list_integrations(pool: asyncpg.Pool, client_id: UUID) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM whatsapp_integrations
        WHERE client_id = $1
        ORDER BY created_at DESC
        """,
        client_id,
    )
    return records_to_dicts(rows)


async def get_integration(pool: asyncpg.Pool, client_id: UUID, integration_id: UUID) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE id = $1 AND client_id = $2
        """,
        integration_id,
        client_id,
    )
    return record_to_dict(row) if row else None


async def get_integration_by_id(pool: asyncpg.Pool, integration_id: UUID) -> dict | None:
    """Webhook path — resolve integration without trusting browser client_id."""
    row = await pool.fetchrow(
        "SELECT * FROM whatsapp_integrations WHERE id = $1",
        integration_id,
    )
    return record_to_dict(row) if row else None


async def get_integration_by_phone_number_id(pool: asyncpg.Pool, phone_number_id: str) -> dict | None:
    """Resolve tenant from the receiving WhatsApp business number."""
    pid = (phone_number_id or "").strip()
    if not pid:
        return None
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE phone_number_id = $1
        ORDER BY enabled DESC, updated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        pid,
    )
    return record_to_dict(row) if row else None


async def upsert_integration(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    provider: str,
    display_name: str | None,
    phone_number_id: str | None,
    business_account_id: str | None,
    webhook_verify_token: str | None,
    credentials_encrypted: str | None,
    status: str = "inactive",
    enabled: bool | None = None,
    configuration: dict | None = None,
    integration_id: UUID | None = None,
) -> dict:
    cfg_json = json.dumps(configuration or {})
    if integration_id:
        row = await pool.fetchrow(
            """
            UPDATE whatsapp_integrations SET
                provider = $3,
                display_name = COALESCE($4, display_name),
                phone_number_id = COALESCE($5, phone_number_id),
                business_account_id = COALESCE($6, business_account_id),
                webhook_verify_token = COALESCE($7, webhook_verify_token),
                credentials_encrypted = COALESCE($8, credentials_encrypted),
                status = $9,
                enabled = COALESCE($10, enabled),
                configuration = COALESCE($11::jsonb, configuration),
                updated_at = NOW()
            WHERE id = $1 AND client_id = $2
            RETURNING *
            """,
            integration_id,
            client_id,
            provider,
            display_name,
            phone_number_id,
            business_account_id,
            webhook_verify_token,
            credentials_encrypted,
            status,
            enabled,
            cfg_json if configuration is not None else None,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO whatsapp_integrations (
                client_id, provider, display_name, phone_number_id, business_account_id,
                webhook_verify_token, credentials_encrypted, status, enabled, configuration
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8, COALESCE($9, false), $10::jsonb)
            RETURNING *
            """,
            client_id,
            provider,
            display_name,
            phone_number_id,
            business_account_id,
            webhook_verify_token,
            credentials_encrypted,
            status,
            enabled,
            cfg_json,
        )
    return record_to_dict(row)


async def get_enabled_integration(pool: asyncpg.Pool, client_id: UUID) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE client_id = $1 AND enabled = TRUE
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """,
        client_id,
    )
    return record_to_dict(row) if row else None


async def ensure_n8n_bridge_integration(pool: asyncpg.Pool, client_id: UUID) -> dict:
    """Stub integration used only to attach n8n-recorded conversations to a client."""
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE client_id = $1
          AND provider = 'stub'
          AND COALESCE(configuration->>'bridge', '') = 'n8n'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        client_id,
    )
    if row:
        return record_to_dict(row)
    return await upsert_integration(
        pool,
        client_id=client_id,
        provider="stub",
        display_name="n8n Mega_Workflow bridge",
        phone_number_id=None,
        business_account_id=None,
        webhook_verify_token=None,
        credentials_encrypted=None,
        status="active",
        enabled=True,
        configuration={"bridge": "n8n"},
    )


async def set_connection_status(
    pool: asyncpg.Pool,
    client_id: UUID,
    integration_id: UUID,
    *,
    connection_status: str,
    last_error: str | None,
) -> None:
    await pool.execute(
        """
        UPDATE whatsapp_integrations
        SET connection_status = $3, last_error = $4, last_tested_at = NOW(), updated_at = NOW()
        WHERE id = $1 AND client_id = $2
        """,
        integration_id,
        client_id,
        connection_status,
        last_error,
    )


async def list_conversations(
    pool: asyncpg.Pool,
    client_id: UUID,
    *,
    search: str | None = None,
    campaign_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    args: list[Any] = [client_id]
    where = "WHERE c.client_id = $1"
    idx = 2
    if search:
        where += f" AND (c.customer_name ILIKE ${idx} OR c.customer_phone ILIKE ${idx})"
        args.append(f"%{search}%")
        idx += 1
    if campaign_id:
        where += f" AND c.campaign_id = ${idx}"
        args.append(campaign_id)
        idx += 1
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM whatsapp_conversations c {where}",
        *args,
    )
    rows = await pool.fetch(
        f"""
        SELECT c.*,
               camp.name AS campaign_name,
               (
                 SELECT m.text_body
                 FROM whatsapp_messages m
                 WHERE m.conversation_id = c.id
                 ORDER BY m.created_at DESC
                 LIMIT 1
               ) AS last_message_preview,
               (
                 SELECT m.status
                 FROM whatsapp_messages m
                 WHERE m.conversation_id = c.id
                 ORDER BY m.created_at DESC
                 LIMIT 1
               ) AS last_message_status,
               (
                 SELECT m.direction
                 FROM whatsapp_messages m
                 WHERE m.conversation_id = c.id
                 ORDER BY m.created_at DESC
                 LIMIT 1
               ) AS last_message_direction
        FROM whatsapp_conversations c
        LEFT JOIN campaigns camp
          ON camp.id = c.campaign_id AND camp.client_id = c.client_id
        {where}
        ORDER BY c.last_message_at DESC NULLS LAST, c.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *args,
        limit,
        offset,
    )
    return records_to_dicts(rows), int(total or 0)


async def get_conversation(pool: asyncpg.Pool, client_id: UUID, conversation_id: UUID) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT c.*, camp.name AS campaign_name
        FROM whatsapp_conversations c
        LEFT JOIN campaigns camp
          ON camp.id = c.campaign_id AND camp.client_id = c.client_id
        WHERE c.id = $1 AND c.client_id = $2
        """,
        conversation_id,
        client_id,
    )
    return record_to_dict(row) if row else None


async def get_conversation_by_phone(pool: asyncpg.Pool, client_id: UUID, phone: str) -> dict | None:
    from lead_upload.normaliser import normalise_phone

    normalized = normalise_phone(str(phone or "")) or str(phone or "").strip()
    if not normalized:
        return None
    row = await pool.fetchrow(
        """
        SELECT c.*, camp.name AS campaign_name
        FROM whatsapp_conversations c
        LEFT JOIN campaigns camp
          ON camp.id = c.campaign_id AND camp.client_id = c.client_id
        WHERE c.client_id = $1
          AND regexp_replace(c.customer_phone, '\\D', '', 'g')
              = regexp_replace($2, '\\D', '', 'g')
        ORDER BY c.last_message_at DESC NULLS LAST, c.created_at DESC
        LIMIT 1
        """,
        client_id,
        normalized,
    )
    return record_to_dict(row) if row else None


async def list_messages(
    pool: asyncpg.Pool,
    client_id: UUID,
    conversation_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT m.*
        FROM whatsapp_messages m
        JOIN whatsapp_conversations c ON c.id = m.conversation_id
        WHERE m.conversation_id = $1 AND m.client_id = $2 AND c.client_id = $2
        ORDER BY m.created_at ASC
        LIMIT $3 OFFSET $4
        """,
        conversation_id,
        client_id,
        limit,
        offset,
    )
    return records_to_dicts(rows)


async def list_templates(pool: asyncpg.Pool, client_id: UUID) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id, client_id, integration_id, provider_template_id, name, language,
               category, status, components, created_at, updated_at
        FROM whatsapp_templates
        WHERE client_id = $1
        ORDER BY updated_at DESC NULLS LAST, created_at DESC
        """,
        client_id,
    )
    return records_to_dicts(rows)


async def insert_message_idempotent(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    conversation_id: UUID,
    provider_message_id: str | None,
    direction: str,
    message_type: str,
    text_body: str | None,
    status: str,
    provider: str | None = None,
    lead_id: UUID | None = None,
    idempotency_key: str | None = None,
    template_name: str | None = None,
    provider_metadata: dict | None = None,
) -> dict | None:
    """Insert message; duplicate provider_message_id or idempotency_key is ignored."""
    pmid = (provider_message_id or "").strip() or None
    ikey = (idempotency_key or "").strip() or None
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO whatsapp_messages (
                conversation_id, client_id, provider_message_id, direction, message_type,
                text_body, status, provider_metadata, provider, lead_id, idempotency_key, template_name
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12)
            ON CONFLICT (client_id, provider_message_id)
                DO NOTHING
            RETURNING *
            """,
            conversation_id,
            client_id,
            pmid,
            direction,
            message_type,
            text_body,
            status,
            json.dumps(provider_metadata or {}),
            provider,
            lead_id,
            ikey,
            template_name,
        )
    except UniqueViolationError:
        if ikey:
            existing = await pool.fetchrow(
                "SELECT * FROM whatsapp_messages WHERE client_id = $1 AND idempotency_key = $2",
                client_id,
                ikey,
            )
            return record_to_dict(existing) if existing else None
        if pmid:
            existing = await pool.fetchrow(
                "SELECT * FROM whatsapp_messages WHERE client_id = $1 AND provider_message_id = $2",
                client_id,
                pmid,
            )
            return record_to_dict(existing) if existing else None
        raise
    if row is None and ikey:
        existing = await pool.fetchrow(
            """
            SELECT * FROM whatsapp_messages
            WHERE client_id = $1 AND idempotency_key = $2
            """,
            client_id,
            ikey,
        )
        return record_to_dict(existing) if existing else None
    if row:
        await pool.execute(
            """
            UPDATE whatsapp_conversations
            SET last_message_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND client_id = $2
            """,
            conversation_id,
            client_id,
        )
    return record_to_dict(row) if row else None


async def get_message_by_idempotency_key(
    pool: asyncpg.Pool,
    client_id: UUID,
    idempotency_key: str,
) -> dict | None:
    """Return an existing outbound message for this idempotency key, if any."""
    ikey = (idempotency_key or "").strip()
    if not ikey:
        return None
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_messages
        WHERE client_id = $1 AND idempotency_key = $2
        LIMIT 1
        """,
        client_id,
        ikey,
    )
    return record_to_dict(row) if row else None


async def get_last_inbound_at(
    pool: asyncpg.Pool,
    client_id: UUID,
    customer_phone: str,
) -> datetime | None:
    """Most recent inbound message time for this phone under the client (any conversation)."""
    row = await pool.fetchrow(
        """
        SELECT m.created_at
        FROM whatsapp_messages m
        JOIN whatsapp_conversations c ON c.id = m.conversation_id
        WHERE m.client_id = $1
          AND c.customer_phone = $2
          AND m.direction = 'incoming'
        ORDER BY m.created_at DESC NULLS LAST
        LIMIT 1
        """,
        client_id,
        customer_phone,
    )
    return row["created_at"] if row else None


async def get_or_create_conversation(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    integration_id: UUID,
    customer_phone: str,
    customer_name: str | None = None,
    lead_id: UUID | None = None,
    campaign_id: UUID | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO whatsapp_conversations (
            client_id, integration_id, customer_phone, customer_name, lead_id, campaign_id,
            last_message_at
        ) VALUES ($1,$2,$3,$4,$5,$6, NOW())
        ON CONFLICT (integration_id, customer_phone)
        DO UPDATE SET
            customer_name = COALESCE(EXCLUDED.customer_name, whatsapp_conversations.customer_name),
            lead_id = COALESCE(whatsapp_conversations.lead_id, EXCLUDED.lead_id),
            campaign_id = COALESCE(whatsapp_conversations.campaign_id, EXCLUDED.campaign_id),
            updated_at = NOW()
        RETURNING *
        """,
        client_id,
        integration_id,
        customer_phone,
        customer_name,
        lead_id,
        campaign_id,
    )
    return record_to_dict(row)


async def update_message_status(
    pool: asyncpg.Pool,
    client_id: UUID,
    provider_message_id: str,
    status: str,
) -> dict | None:
    col = {
        "sent": "sent_at",
        "delivered": "delivered_at",
        "read": "read_at",
        "failed": "failed_at",
    }.get((status or "").lower())
    ts_sql = f", {col} = NOW()" if col else ""
    row = await pool.fetchrow(
        f"""
        UPDATE whatsapp_messages
        SET status = $3, provider_metadata = provider_metadata || jsonb_build_object('last_status', $3)
            {ts_sql}
        WHERE client_id = $1 AND provider_message_id = $2
        RETURNING *
        """,
        client_id,
        provider_message_id,
        status,
    )
    return record_to_dict(row) if row else None


async def list_followup_plans(pool: asyncpg.Pool, client_id: UUID) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM whatsapp_followup_plans WHERE client_id = $1 ORDER BY created_at DESC",
        client_id,
    )
    return records_to_dicts(rows)


async def upsert_followup_plan(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    name: str,
    trigger_outcome: str,
    steps: list,
    active: bool = True,
    plan_id: UUID | None = None,
) -> dict:
    if plan_id:
        row = await pool.fetchrow(
            """
            UPDATE whatsapp_followup_plans
            SET name = $3, trigger_outcome = $4, steps = $5::jsonb, active = $6, updated_at = NOW()
            WHERE id = $1 AND client_id = $2
            RETURNING *
            """,
            plan_id,
            client_id,
            name,
            trigger_outcome,
            json.dumps(steps),
            active,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO whatsapp_followup_plans (client_id, name, trigger_outcome, steps, active)
            VALUES ($1,$2,$3,$4::jsonb,$5)
            RETURNING *
            """,
            client_id,
            name,
            trigger_outcome,
            json.dumps(steps),
            active,
        )
    return record_to_dict(row)


async def get_active_followup_plan(pool: asyncpg.Pool, client_id: UUID, trigger_outcome: str | None) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_followup_plans
        WHERE client_id = $1 AND active = TRUE
          AND ($2::text IS NULL OR lower(trigger_outcome) = lower($2))
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        client_id,
        trigger_outcome,
    )
    return record_to_dict(row) if row else None


async def insert_followup_jobs(pool: asyncpg.Pool, jobs: list[dict]) -> int:
    n = 0
    for job in jobs:
        await pool.execute(
            """
            INSERT INTO whatsapp_followup_jobs (
                client_id, plan_id, lead_id, campaign_id, conversation_id,
                customer_phone, step_index, scheduled_at, status
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pending')
            """,
            job["client_id"],
            job["plan_id"],
            job.get("lead_id"),
            job.get("campaign_id"),
            job.get("conversation_id"),
            job["customer_phone"],
            job["step_index"],
            job["scheduled_at"],
        )
        n += 1
    return n


async def cancel_pending_followups(
    pool: asyncpg.Pool,
    client_id: UUID,
    *,
    conversation_id: UUID | None = None,
    lead_id: UUID | None = None,
    customer_phone: str | None = None,
    reason: str = "customer_replied",
) -> int:
    result = await pool.execute(
        """
        UPDATE whatsapp_followup_jobs
        SET status = 'cancelled', cancel_reason = $5, updated_at = NOW()
        WHERE client_id = $1 AND status = 'pending'
          AND (
            ($2::uuid IS NOT NULL AND conversation_id = $2)
            OR ($3::uuid IS NOT NULL AND lead_id = $3)
            OR ($4::text IS NOT NULL AND customer_phone = $4)
          )
        """,
        client_id,
        conversation_id,
        lead_id,
        customer_phone,
        reason,
    )
    try:
        return int(str(result).split()[-1])
    except (ValueError, IndexError):
        return 0


async def claim_due_followup_jobs(pool: asyncpg.Pool, limit: int = 20) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT * FROM whatsapp_followup_jobs
        WHERE status = 'pending' AND scheduled_at <= NOW()
        ORDER BY scheduled_at ASC
        LIMIT $1
        """,
        limit,
    )
    return records_to_dicts(rows)


async def mark_followup_job(pool: asyncpg.Pool, job_id: UUID, client_id: UUID, status: str, message_id: UUID | None = None) -> None:
    await pool.execute(
        """
        UPDATE whatsapp_followup_jobs
        SET status = $3, message_id = COALESCE($4, message_id), updated_at = NOW()
        WHERE id = $1 AND client_id = $2
        """,
        job_id,
        client_id,
        status,
        message_id,
    )

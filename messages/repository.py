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
    """Prefer a real Meta Cloud integration over n8n/stub bridges.

    Outbound follow-ups and Meta inbound webhooks must share one conversation
    identity (integration_id + phone). Preferring Meta prevents dual threads.
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE client_id = $1 AND enabled = TRUE
        ORDER BY
          CASE
            WHEN provider = 'meta_cloud' THEN 0
            WHEN provider IN ('stub', 'n8n') THEN 2
            ELSE 1
          END,
          CASE
            WHEN COALESCE(configuration->>'bridge', '') IN ('n8n', 'mega', 'mega_workflow') THEN 1
            ELSE 0
          END,
          updated_at DESC NULLS LAST
        LIMIT 1
        """,
        client_id,
    )
    return record_to_dict(row) if row else None


# Meta sample — never use as a customer-facing default.
_SAMPLE_TEMPLATE_NAMES = frozenset({"hello_world"})

_DEFAULT_FIRST_CONTACT_VARIABLES = (
    {"index": 1, "source": "first_name", "fallback": "there"},
    {"index": 2, "source": "client_name", "fallback": "our team"},
)


def default_n8n_followup_configuration(
    *,
    extra: dict | None = None,
) -> dict:
    """Canonical WhatsApp config when Mega_Workflow / campaign n8n owns first contact.

    Default template name: ``bhuvisx_interested_lead_followup`` / ``en_US``.
    Meta's sample ``hello_world`` is never kept as a customer default.
    ``approved`` defaults to False until Meta approval is confirmed via Admin/API
    (or WHATSAPP_FIRST_CONTACT_APPROVED=1 after the WABA template is live).
    """
    import os

    from followups.template_registry import (
        PURPOSE_INTERESTED_INITIAL,
        recommended_interested_template_name,
        recommended_language_code,
    )

    template_name = recommended_interested_template_name()
    language = recommended_language_code()
    approved_default = str(os.getenv("WHATSAPP_FIRST_CONTACT_APPROVED") or "").strip().casefold() in (
        "1",
        "true",
        "yes",
        "on",
    )
    base_fc = {
        "enabled": True,
        "approved": approved_default,
        "template_name": template_name,
        "language_code": language,
        "purpose": PURPOSE_INTERESTED_INITIAL,
        "category": "UTILITY",
        "variables": [dict(v) for v in _DEFAULT_FIRST_CONTACT_VARIABLES],
    }
    if not extra:
        return {
            "bridge": "n8n",
            "allow_simulated_send": False,
            "first_contact_template": base_fc,
        }

    merged = dict(extra)
    merged["bridge"] = "n8n"
    if merged.get("allow_simulated_send") is None:
        merged["allow_simulated_send"] = False

    prev_fc = extra.get("first_contact_template") if isinstance(extra.get("first_contact_template"), dict) else {}
    fc = {**base_fc, **prev_fc}
    prev_name = str(prev_fc.get("template_name") or "").strip()
    # Keep real client templates; replace missing / Meta sample with the professional default.
    if not prev_name or prev_name.casefold() in _SAMPLE_TEMPLATE_NAMES:
        fc["template_name"] = base_fc["template_name"]
        # Upgrading away from hello_world must not silently mark approved.
        if "approved" not in prev_fc or prev_name.casefold() in _SAMPLE_TEMPLATE_NAMES:
            fc["approved"] = approved_default
    lang = str(fc.get("language_code") or base_fc["language_code"]).strip() or "en_US"
    if lang == "en":
        lang = "en_US"
    fc["language_code"] = lang
    fc["purpose"] = str(prev_fc.get("purpose") or PURPOSE_INTERESTED_INITIAL)
    if "enabled" not in prev_fc:
        fc["enabled"] = True
    if "approved" not in prev_fc and prev_name and prev_name.casefold() not in _SAMPLE_TEMPLATE_NAMES:
        fc["approved"] = bool(prev_fc.get("approved", approved_default))
    prev_vars = prev_fc.get("variables")
    upgrading_sample = not prev_name or prev_name.casefold() in _SAMPLE_TEMPLATE_NAMES
    if upgrading_sample or prev_vars is None or prev_vars == []:
        fc["variables"] = [dict(v) for v in _DEFAULT_FIRST_CONTACT_VARIABLES]
    merged["first_contact_template"] = fc
    return merged


async def set_client_first_contact_template(
    pool: asyncpg.Pool,
    client_id: UUID,
    *,
    template_name: str,
    language_code: str = "en_US",
    enabled: bool = True,
    approved: bool = True,
    variables: list | None = None,
) -> dict:
    """Set/replace the per-client first-contact Meta template used after interested calls.

    Meta requires each template to be pre-approved on the WABA. Different clients can
    point at different approved template names (and body variables).
    """
    name = (template_name or "").strip()
    if not name:
        raise ValueError("template_name_required")
    from followups.template_registry import PURPOSE_INTERESTED_INITIAL, is_sample_template

    if is_sample_template(name) and not (
        str(__import__("os").getenv("WHATSAPP_ALLOW_SAMPLE_TEMPLATE") or "").strip().casefold()
        in ("1", "true", "yes", "on")
    ):
        raise ValueError("sample_template_not_allowed")
    lang = (language_code or "en_US").strip() or "en_US"
    if lang == "en":
        lang = "en_US"

    # Ensure bridge row exists, then overlay the client template.
    await ensure_n8n_bridge_integration(pool, client_id)
    row = await pool.fetchrow(
        """
        SELECT * FROM whatsapp_integrations
        WHERE client_id = $1 AND enabled = TRUE
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """,
        client_id,
    )
    if not row:
        raise ValueError("whatsapp_integration_missing")
    existing = record_to_dict(row)
    raw_cfg = existing.get("configuration") or {}
    if isinstance(raw_cfg, str):
        try:
            raw_cfg = json.loads(raw_cfg)
        except json.JSONDecodeError:
            raw_cfg = {}
    if not isinstance(raw_cfg, dict):
        raw_cfg = {}
    raw_cfg["bridge"] = "n8n"
    resolved_vars = variables if isinstance(variables, list) and len(variables) > 0 else [
        dict(v) for v in _DEFAULT_FIRST_CONTACT_VARIABLES
    ]
    raw_cfg["first_contact_template"] = {
        "enabled": bool(enabled),
        "approved": bool(approved),
        "template_name": name,
        "language_code": lang,
        "purpose": PURPOSE_INTERESTED_INITIAL,
        "category": "UTILITY",
        "variables": resolved_vars,
    }
    return await upsert_integration(
        pool,
        client_id=client_id,
        provider=existing.get("provider") or "stub",
        display_name=existing.get("display_name"),
        phone_number_id=existing.get("phone_number_id"),
        business_account_id=existing.get("business_account_id"),
        webhook_verify_token=existing.get("webhook_verify_token"),
        credentials_encrypted=None,
        status="active",
        enabled=True,
        configuration=raw_cfg,
        integration_id=UUID(str(existing["id"])),
    )


async def ensure_n8n_bridge_integration(pool: asyncpg.Pool, client_id: UUID) -> dict:
    """Ensure the client can send first-contact WhatsApp via n8n Mega_Workflow.

    - Prefer an existing n8n-bridge stub and heal missing first_contact_template.
    - Else upgrade the latest enabled stub for this client.
    - Else create a bridge stub.
    """
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
    if not row:
        row = await pool.fetchrow(
            """
            SELECT * FROM whatsapp_integrations
            WHERE client_id = $1 AND provider = 'stub'
            ORDER BY enabled DESC, updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            client_id,
        )

    if row:
        existing = record_to_dict(row)
        raw_cfg = existing.get("configuration") or {}
        if isinstance(raw_cfg, str):
            try:
                raw_cfg = json.loads(raw_cfg)
            except json.JSONDecodeError:
                raw_cfg = {}
        if not isinstance(raw_cfg, dict):
            raw_cfg = {}
        healed = default_n8n_followup_configuration(extra=raw_cfg)
        fc = healed.get("first_contact_template") or {}
        prev_fc = raw_cfg.get("first_contact_template") if isinstance(raw_cfg.get("first_contact_template"), dict) else {}
        prev_lang = str(prev_fc.get("language_code") or "").strip()
        prev_name = str(prev_fc.get("template_name") or "").strip().casefold()
        needs = (
            str(raw_cfg.get("bridge") or "").casefold() != "n8n"
            or not fc.get("template_name")
            or not fc.get("enabled")
            or not fc.get("approved")
            or prev_lang in ("", "en")
            or prev_name in _SAMPLE_TEMPLATE_NAMES
            or str(fc.get("template_name") or "").strip().casefold() in _SAMPLE_TEMPLATE_NAMES
            or existing.get("enabled") is False
            or (existing.get("status") or "") != "active"
        )
        if not needs:
            return existing
        return await upsert_integration(
            pool,
            client_id=client_id,
            provider="stub",
            display_name=existing.get("display_name") or "n8n Mega_Workflow bridge",
            phone_number_id=existing.get("phone_number_id"),
            business_account_id=existing.get("business_account_id"),
            webhook_verify_token=existing.get("webhook_verify_token"),
            credentials_encrypted=None,
            status="active",
            enabled=True,
            configuration=healed,
            integration_id=UUID(str(existing["id"])),
        )

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
        configuration=default_n8n_followup_configuration(),
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


async def get_conversation_by_integration_phone(
    pool: asyncpg.Pool,
    client_id: UUID,
    integration_id: UUID,
    phone: str,
) -> dict | None:
    """Tenant + WABA scoped conversation lookup (never phone alone)."""
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
          AND c.integration_id = $2
          AND regexp_replace(c.customer_phone, '\\D', '', 'g')
              = regexp_replace($3, '\\D', '', 'g')
        ORDER BY c.last_message_at DESC NULLS LAST, c.created_at DESC
        LIMIT 1
        """,
        client_id,
        integration_id,
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
    """Return a chronological page of messages.

    Pages from the newest end (offset 0 = latest ``limit`` messages) so long
    threads do not load unbounded history on every refresh.
    """
    rows = await pool.fetch(
        """
        SELECT * FROM (
            SELECT m.*
            FROM whatsapp_messages m
            JOIN whatsapp_conversations c ON c.id = m.conversation_id
            WHERE m.conversation_id = $1 AND m.client_id = $2 AND c.client_id = $2
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT $3 OFFSET $4
        ) page
        ORDER BY created_at ASC, id ASC
        """,
        conversation_id,
        client_id,
        limit,
        offset,
    )
    return records_to_dicts(rows)


async def upsert_template_registry(
    pool: asyncpg.Pool,
    *,
    client_id: UUID,
    integration_id: UUID,
    name: str,
    language: str = "en_US",
    category: str | None = "UTILITY",
    status: str = "APPROVED",
    purpose: str = "interested_lead_initial_followup",
    variables: list | None = None,
    provider_template_id: str | None = None,
) -> dict:
    """Upsert a client-scoped WhatsApp template registry row (no Meta API call)."""
    from followups.template_ref import normalize_template_ref
    from followups.template_registry import is_sample_template, sample_templates_allowed

    ref = normalize_template_ref(name, language)
    if is_sample_template(ref["template_name"]) and not sample_templates_allowed():
        raise ValueError("sample_template_not_allowed")
    components = {
        "purpose": purpose,
        "variables": variables if isinstance(variables, list) else list(_DEFAULT_FIRST_CONTACT_VARIABLES),
    }
    existing = await pool.fetchrow(
        """
        SELECT id FROM whatsapp_templates
        WHERE client_id = $1 AND integration_id = $2 AND name = $3
          AND COALESCE(language, '') = $4
        LIMIT 1
        """,
        client_id,
        integration_id,
        ref["template_name"],
        ref["language_code"],
    )
    if existing:
        row = await pool.fetchrow(
            """
            UPDATE whatsapp_templates
            SET category = $2, status = $3, components = $4::jsonb,
                provider_template_id = COALESCE($5, provider_template_id),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            existing["id"],
            category,
            status,
            json.dumps(components),
            provider_template_id,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO whatsapp_templates (
                client_id, integration_id, provider_template_id, name, language,
                category, status, components
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
            RETURNING *
            """,
            client_id,
            integration_id,
            provider_template_id,
            ref["template_name"],
            ref["language_code"],
            category,
            status,
            json.dumps(components),
        )
    return record_to_dict(row)


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


# Delivery status rank — never let an older webhook overwrite a newer terminal state.
_STATUS_RANK = {
    "pending": 0,
    "queued": 0,
    "accepted": 1,
    "sent": 2,
    "delivered": 3,
    "read": 4,
    "failed": 5,
    "undelivered": 5,
    "error": 5,
}


async def update_message_status(
    pool: asyncpg.Pool,
    client_id: UUID,
    provider_message_id: str,
    status: str,
) -> dict | None:
    new_status = (status or "").strip().lower() or "unknown"
    existing = await pool.fetchrow(
        """
        SELECT id, status FROM whatsapp_messages
        WHERE client_id = $1 AND provider_message_id = $2
        """,
        client_id,
        provider_message_id,
    )
    if not existing:
        return None

    current = str(existing["status"] or "").strip().lower()
    cur_rank = _STATUS_RANK.get(current, -1)
    new_rank = _STATUS_RANK.get(new_status, -1)
    # Do not regress: delivered must not become sent; failed is sticky.
    if current == "failed" and new_status != "failed":
        return record_to_dict(
            await pool.fetchrow(
                "SELECT * FROM whatsapp_messages WHERE id = $1",
                existing["id"],
            )
        )
    if new_rank < cur_rank:
        return record_to_dict(
            await pool.fetchrow(
                "SELECT * FROM whatsapp_messages WHERE id = $1",
                existing["id"],
            )
        )

    col = {
        "sent": "sent_at",
        "delivered": "delivered_at",
        "read": "read_at",
        "failed": "failed_at",
    }.get(new_status)
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
        new_status,
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

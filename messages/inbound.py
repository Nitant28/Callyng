"""Inbound WhatsApp tenant resolution helpers.

Phone alone is never enough to authorize AI / lead context. Callers must supply
``phone_number_id``, ``client_id``, and/or ``integration_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass
class InboundTenantResult:
    ok: bool
    error: str | None = None
    phone_e164: str | None = None
    client_id: UUID | None = None
    integration_id: UUID | None = None
    lead: dict[str, Any] | None = None
    campaign: dict[str, Any] | None = None
    conversation: dict[str, Any] | None = None
    memory_key: str | None = None
    integration: dict[str, Any] | None = None


def _fail(
    error: str,
    *,
    phone_e164: str | None = None,
    client_id: UUID | None = None,
    integration_id: UUID | None = None,
) -> InboundTenantResult:
    return InboundTenantResult(
        ok=False,
        error=error,
        phone_e164=phone_e164,
        client_id=client_id,
        integration_id=integration_id,
    )


def _as_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _memory_key(client_id: UUID, campaign_id: Any, lead_id: Any) -> str | None:
    if not client_id or not campaign_id or not lead_id:
        return None
    return f"{client_id}:{campaign_id}:{lead_id}"


async def resolve_inbound_tenant(
    pool,
    *,
    phone: str | None = None,
    phone_number_id: str | None = None,
    client_id: UUID | str | None = None,
    integration_id: UUID | str | None = None,
    to_phone: str | None = None,
    provider: str | None = None,
) -> InboundTenantResult:
    """Resolve tenant + lead for inbound WhatsApp / n8n lead-context lookups.

    Fail closed on missing tenant identity, cross-tenant mismatches, or incomplete
    memory context. ``provider`` is accepted for call-site compatibility only.
    """
    from db import postgres as pg_db
    from lead_upload.normaliser import normalise_phone
    from messages import repository as messages_repo

    _ = provider
    raw_phone = phone or to_phone
    phone_e164 = normalise_phone(str(raw_phone or ""))
    if not phone_e164:
        return _fail("invalid_phone")

    pnid = str(phone_number_id or "").strip() or None
    want_client = _as_uuid(client_id)
    want_integration = _as_uuid(integration_id)

    if not pnid and want_client is None and want_integration is None:
        return _fail("phone_number_id_or_client_id_required", phone_e164=phone_e164)

    integration: dict[str, Any] | None = None
    resolved_client: UUID | None = None

    if pnid:
        integration = await messages_repo.get_integration_by_phone_number_id(pool, pnid)
        if not integration:
            return _fail("integration_not_found", phone_e164=phone_e164)
        resolved_client = UUID(str(integration["client_id"]))
        if want_client is not None and want_client != resolved_client:
            return _fail(
                "client_integration_mismatch",
                phone_e164=phone_e164,
                client_id=resolved_client,
                integration_id=_as_uuid(integration.get("id")),
            )

    if want_integration is not None:
        by_id = await messages_repo.get_integration_by_id(pool, want_integration)
        if not by_id:
            return _fail(
                "integration_not_found",
                phone_e164=phone_e164,
                client_id=resolved_client or want_client,
            )
        by_id_client = UUID(str(by_id["client_id"]))
        if integration and UUID(str(integration["id"])) != UUID(str(by_id["id"])):
            return _fail(
                "client_integration_mismatch",
                phone_e164=phone_e164,
                client_id=resolved_client or by_id_client,
                integration_id=UUID(str(integration["id"])),
            )
        if resolved_client is not None and resolved_client != by_id_client:
            return _fail(
                "client_integration_mismatch",
                phone_e164=phone_e164,
                client_id=resolved_client,
                integration_id=UUID(str(by_id["id"])),
            )
        if want_client is not None and want_client != by_id_client:
            return _fail(
                "client_integration_mismatch",
                phone_e164=phone_e164,
                client_id=want_client,
                integration_id=UUID(str(by_id["id"])),
            )
        integration = by_id
        resolved_client = by_id_client

    if want_client is not None:
        if resolved_client is not None and resolved_client != want_client:
            return _fail(
                "client_integration_mismatch",
                phone_e164=phone_e164,
                client_id=want_client,
                integration_id=_as_uuid((integration or {}).get("id")),
            )
        resolved_client = want_client
        if integration is None:
            integration = await messages_repo.get_enabled_integration(pool, resolved_client)

    assert resolved_client is not None
    integ_uuid = _as_uuid((integration or {}).get("id")) if integration else None

    lead = await pg_db.find_lead_by_phone(pool, phone_e164, client_id=resolved_client)
    if not lead:
        return _fail(
            "lead_not_found",
            phone_e164=phone_e164,
            client_id=resolved_client,
            integration_id=integ_uuid,
        )

    lead_client = _as_uuid(lead.get("client_id"))
    if lead_client is not None and lead_client != resolved_client:
        return _fail(
            "lead_client_mismatch",
            phone_e164=phone_e164,
            client_id=resolved_client,
            integration_id=integ_uuid,
        )

    conversation: dict[str, Any] | None = None
    if integ_uuid is not None:
        conversation = await messages_repo.get_conversation_by_integration_phone(
            pool, resolved_client, integ_uuid, phone_e164
        )
    if conversation is None:
        conversation = await messages_repo.get_conversation_by_phone(
            pool, resolved_client, phone_e164
        )

    conv_campaign = _as_uuid((conversation or {}).get("campaign_id")) if conversation else None
    lead_campaign = _as_uuid(lead.get("campaign_id"))
    if conv_campaign is not None and lead_campaign is not None and conv_campaign != lead_campaign:
        return _fail(
            "conversation_campaign_mismatch",
            phone_e164=phone_e164,
            client_id=resolved_client,
            integration_id=integ_uuid,
        )

    campaign: dict[str, Any] | None = None
    if lead_campaign is not None:
        campaign = await pg_db.get_campaign(pool, lead_campaign, resolved_client)
        if not campaign:
            campaign = {"id": lead.get("campaign_id"), "name": lead.get("campaign_name")}

    memory_key = _memory_key(resolved_client, lead.get("campaign_id"), lead.get("id"))
    if not memory_key:
        return _fail(
            "memory_context_incomplete",
            phone_e164=phone_e164,
            client_id=resolved_client,
            integration_id=integ_uuid,
        )

    return InboundTenantResult(
        ok=True,
        phone_e164=phone_e164,
        client_id=resolved_client,
        integration_id=integ_uuid,
        lead=lead,
        campaign=campaign,
        conversation=conversation,
        memory_key=memory_key,
        integration=integration,
    )

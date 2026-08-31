"""Attach deterministic fallbacks and the first-contact plan to an n8n payload.

Both the automatic post-call path and the manual follow-up path run through here,
so n8n always receives backend-generated copy it can fall back to, plus an honest
statement of whether the first outbound message may legally be free-form text.

Every database read is guarded: enrichment must never be the reason a follow-up
fails to dispatch.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger

from followups.context import LeadContext
from followups.fallback import build_fallback_bundle
from followups.templates import (
    MODE_BLOCKED,
    FirstContactPlan,
    FirstContactTemplate,
    plan_first_contact,
    select_template_config,
)


async def _conversation_window_open(pool, client_id: UUID, phone: str | None) -> bool:
    if pool is None or not phone:
        return False
    try:
        from messages import repository as messages_repo
        from messages.eligibility import conversation_window_open

        last_inbound = await messages_repo.get_last_inbound_at(pool, client_id, phone)
        return conversation_window_open(last_inbound)
    except Exception as exc:
        logger.warning("first-contact window check failed client={} err={}", client_id, exc)
        return False


async def _template_config(pool, client_id: UUID) -> FirstContactTemplate:
    if pool is None:
        return FirstContactTemplate()
    try:
        from messages import repository as messages_repo

        integrations = await messages_repo.list_integrations(pool, client_id)
        return select_template_config(integrations)
    except Exception as exc:
        logger.warning("first-contact template load failed client={} err={}", client_id, exc)
        return FirstContactTemplate()


async def resolve_first_contact(pool, *, client_id: UUID, ctx: LeadContext) -> FirstContactPlan:
    """Decide how the first outbound WhatsApp message may be delivered."""
    try:
        window_open = await _conversation_window_open(pool, client_id, ctx.phone)
        template = await _template_config(pool, client_id)
        return plan_first_contact(template, ctx, conversation_window_open=window_open)
    except Exception as exc:
        logger.warning("first-contact planning failed client={} err={}", client_id, exc)
        return FirstContactPlan(mode=MODE_BLOCKED, reason="first_contact_plan_error")


async def enrich_lead_payload(
    pool,
    payload: dict[str, Any],
    *,
    client_id: UUID,
    inbound_text: str | None = None,
) -> dict[str, Any]:
    """Add ``fallback`` and ``first_contact`` blocks to a lead_qualified payload."""
    try:
        ctx = LeadContext.from_payload(payload)
        payload["fallback"] = build_fallback_bundle(ctx, inbound_text=inbound_text)
        payload["lead_context"] = ctx.to_dict()
        plan = await resolve_first_contact(pool, client_id=client_id, ctx=ctx)
        payload["first_contact"] = plan.to_dict()
    except Exception as exc:
        logger.warning("payload enrichment failed client={} err={}", client_id, exc)
    return payload

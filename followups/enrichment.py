"""Attach deterministic fallbacks and the first-contact plan to an n8n payload.

Both the automatic post-call path and the manual follow-up path run through here.
Template name and language are always stamped as separate fields — never combined
as the Meta template name.
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


def _as_config_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def _template_config(pool, client_id: UUID) -> FirstContactTemplate:
    if pool is None:
        return FirstContactTemplate()
    try:
        from messages import repository as messages_repo

        integrations = await messages_repo.list_integrations(pool, client_id)
        normalized = [
            {**row, "configuration": _as_config_dict(row.get("configuration"))}
            for row in (integrations or [])
        ]
        return select_template_config(normalized)
    except Exception as exc:
        logger.warning("first-contact template load failed client={} err={}", client_id, exc)
        return FirstContactTemplate()


async def _attach_whatsapp_integration(pool, payload: dict[str, Any], client_id: UUID) -> None:
    if pool is None:
        return
    try:
        from messages import repository as messages_repo

        integ = await messages_repo.get_enabled_integration(pool, client_id)
        if not integ:
            return
        payload["whatsapp"] = {
            "integration_id": str(integ["id"]),
            "phone_number_id": integ.get("phone_number_id"),
            "provider": integ.get("provider"),
        }
    except Exception as exc:
        logger.warning("whatsapp integration attach failed client={} err={}", client_id, exc)


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
    """Add ``fallback``, ``first_contact``, and separate template fields."""
    try:
        ctx = LeadContext.from_payload(payload)
        payload["fallback"] = build_fallback_bundle(ctx, inbound_text=inbound_text)
        payload["lead_context"] = ctx.to_dict()
        plan = await resolve_first_contact(pool, client_id=client_id, ctx=ctx)
        fc = plan.to_dict()
        payload["first_contact"] = fc
        if fc.get("template_name"):
            from followups.template_ref import format_n8n_template_field, normalize_template_ref

            ref = normalize_template_ref(
                fc.get("template_name"),
                fc.get("language_code") or "en_US",
            )
            payload["first_contact"]["template_name"] = ref["template_name"]
            payload["first_contact"]["language_code"] = ref["language_code"]
            payload["template_name"] = ref["template_name"]
            payload["template_language"] = ref["language_code"]
            payload["language_code"] = ref["language_code"]
            # Convenience for n8n WhatsApp node UI only (single field expects name|lang).
            payload["n8n_template"] = format_n8n_template_field(
                ref["template_name"], ref["language_code"]
            )
            payload["template_parameters"] = list(fc.get("parameters") or [])
            if fc.get("components"):
                payload["template_components"] = list(fc["components"])
                body_params = []
                for comp in fc["components"]:
                    if isinstance(comp, dict) and str(comp.get("type") or "").lower() == "body":
                        for p in comp.get("parameters") or []:
                            if isinstance(p, dict) and p.get("text") is not None:
                                body_params.append({"type": "text", "text": str(p["text"])})
                if body_params:
                    payload["n8n_template_components"] = {"body": body_params}
    except Exception as exc:
        logger.warning("payload enrichment failed client={} err={}", client_id, exc)
    await _attach_whatsapp_integration(pool, payload, client_id)
    return payload

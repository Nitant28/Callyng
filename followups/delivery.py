"""Canonical WhatsApp follow-up delivery (backend Meta preferred; n8n bridge deferred)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger

from followups.template_ref import TemplateRefError, normalize_template_ref
from followups.templates import MODE_TEXT
from lead_upload.normaliser import normalise_phone
from messages import repository as messages_repo
from messages.service import send_message


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


def _is_n8n_bridge(configuration: Any) -> bool:
    cfg = _as_config_dict(configuration)
    bridge = str(cfg.get("bridge") or "").strip().casefold()
    return bridge in ("n8n", "mega", "mega_workflow")


def _has_meta_credentials(integration: dict[str, Any] | None) -> bool:
    if not integration:
        return False
    if str(integration.get("provider") or "").casefold() != "meta_cloud":
        return False
    if not integration.get("phone_number_id"):
        return False
    return bool(integration.get("credentials_encrypted") or _as_config_dict(integration.get("configuration")).get("access_token"))


def build_delivery_context(
    *,
    client_id: UUID,
    campaign_id: UUID | None,
    lead_id: UUID | None,
    phone: str,
    integration: dict[str, Any],
    template_name: str | None,
    language_code: str | None,
    message_type: str,
) -> dict[str, Any]:
    return {
        "client_id": str(client_id),
        "campaign_id": str(campaign_id) if campaign_id else None,
        "lead_id": str(lead_id) if lead_id else None,
        "phone": phone,
        "integration_id": str(integration.get("id")) if integration.get("id") else None,
        "provider": integration.get("provider"),
        "template_name": template_name,
        "language_code": language_code,
        "message_type": message_type,
    }


async def deliver_whatsapp_follow_up(
    pool,
    *,
    client_id: UUID,
    lead: dict[str, Any],
    campaign: dict[str, Any] | None = None,
    first_contact: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    message_text: str | None = None,
    whatsapp_opt_in: bool | None = None,
) -> dict[str, Any]:
    """Send via backend Meta when possible; otherwise defer to n8n with approved template only.

    Success for backend path requires a real provider_message_id (wamid).
    n8n deferral returns deferred_to_n8n=True and must NOT be treated as delivered.
    """
    lead_id = UUID(str(lead["id"])) if lead.get("id") else None
    campaign_id = None
    if campaign and campaign.get("id"):
        campaign_id = UUID(str(campaign["id"]))
    elif lead.get("campaign_id"):
        campaign_id = UUID(str(lead["campaign_id"]))

    phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
    if not phone:
        return {
            "ok": False,
            "mode": "failed",
            "error": "missing_recipient",
            "error_category": "missing_recipient",
        }

    if lead_id is not None and campaign_id is not None:
        lead_campaign = lead.get("campaign_id")
        if lead_campaign is None or str(lead_campaign) != str(campaign_id):
            return {
                "ok": False,
                "mode": "failed",
                "error": "lead_campaign_mismatch",
                "error_category": "lead_campaign_mismatch",
            }

    fc = first_contact or {}
    if fc.get("can_send") is False:
        return {
            "ok": False,
            "mode": "failed",
            "error": str(fc.get("reason") or "template_not_configured"),
            "error_category": str(fc.get("reason") or "template_not_configured"),
        }

    mode = str(fc.get("mode") or "").strip().casefold()
    text_body = (message_text or "").strip()
    use_text = mode == MODE_TEXT or (
        str(fc.get("reason") or "") == "conversation_window_open" and bool(text_body)
    )

    integration = await messages_repo.get_enabled_integration(pool, client_id)
    if not integration:
        return {
            "ok": False,
            "mode": "failed",
            "error": "integration_not_found",
            "error_category": "integration_not_found",
        }
    if integration.get("enabled") is False:
        return {
            "ok": False,
            "mode": "failed",
            "error": "integration_disabled",
            "error_category": "integration_disabled",
        }

    if use_text:
        if not text_body:
            return {
                "ok": False,
                "mode": "failed",
                "error": "text_required",
                "error_category": "text_required",
            }
        context = build_delivery_context(
            client_id=client_id,
            campaign_id=campaign_id,
            lead_id=lead_id,
            phone=phone,
            integration=integration,
            template_name=None,
            language_code=None,
            message_type="text",
        )
        if _has_meta_credentials(integration):
            result = await send_message(
                pool,
                client_id=client_id,
                to_phone=phone,
                text=text_body,
                template_name=None,
                language=None,
                lead_id=lead_id,
                campaign_id=campaign_id,
                customer_name=lead.get("name"),
                integration_id=UUID(str(integration["id"])),
                idempotency_key=idempotency_key,
                whatsapp_opt_in=whatsapp_opt_in,
                force_message_type="text",
            )
            pmid = result.get("provider_message_id")
            if result.get("ok") and pmid:
                return {
                    "ok": True,
                    "mode": "backend",
                    "deferred_to_n8n": False,
                    "message_type": "text",
                    "provider_message_id": pmid,
                    "conversation": result.get("conversation"),
                    "message": result.get("message"),
                    "deduplicated": bool(result.get("deduplicated")),
                    "delivery_context": context,
                }
            return {
                "ok": False,
                "mode": "failed",
                "error": result.get("error") or "provider_rejected",
                "error_category": "provider_rejected",
                "delivery_context": context,
            }

        if _is_n8n_bridge(integration.get("configuration")) or str(
            integration.get("provider") or ""
        ).casefold() in ("stub", "n8n"):
            logger.info(
                "[WHATSAPP_SEND] text deferred_to_n8n client={} lead={}",
                client_id,
                lead_id,
            )
            return {
                "ok": True,
                "mode": "n8n",
                "deferred_to_n8n": True,
                "message_type": "text",
                "message_text": text_body,
                "provider_message_id": None,
                "delivery_context": context,
            }
        return {
            "ok": False,
            "mode": "failed",
            "error": "meta_credentials_not_configured",
            "error_category": "meta_credentials_not_configured",
            "delivery_context": context,
        }

    try:
        ref = normalize_template_ref(
            fc.get("template_name"),
            fc.get("language_code") or fc.get("template_language"),
        )
    except TemplateRefError as exc:
        return {
            "ok": False,
            "mode": "failed",
            "error": exc.code,
            "error_category": exc.code,
        }

    from followups.template_registry import is_sample_template, sample_templates_allowed

    if is_sample_template(ref["template_name"]) and not sample_templates_allowed():
        return {
            "ok": False,
            "mode": "failed",
            "error": "template_not_configured",
            "error_category": "template_not_configured",
        }

    context = build_delivery_context(
        client_id=client_id,
        campaign_id=campaign_id,
        lead_id=lead_id,
        phone=phone,
        integration=integration,
        template_name=ref["template_name"],
        language_code=ref["language_code"],
        message_type="template",
    )

    logger.info(
        "[WHATSAPP_SEND] client={} lead={} template={} lang={} type=template",
        client_id,
        lead_id,
        ref["template_name"],
        ref["language_code"],
    )

    if _has_meta_credentials(integration):
        components = fc.get("components") or None
        result = await send_message(
            pool,
            client_id=client_id,
            to_phone=phone,
            text=None,
            template_name=ref["template_name"],
            language=ref["language_code"],
            components=components,
            lead_id=lead_id,
            campaign_id=campaign_id,
            customer_name=lead.get("name"),
            integration_id=UUID(str(integration["id"])),
            idempotency_key=idempotency_key,
            whatsapp_opt_in=whatsapp_opt_in,
            force_message_type="template",
        )
        pmid = result.get("provider_message_id")
        logger.info(
            "[WHATSAPP_PROVIDER_RESPONSE] ok={} provider_message_id={}",
            result.get("ok"),
            pmid,
        )
        if result.get("ok") and pmid:
            return {
                "ok": True,
                "mode": "backend",
                "deferred_to_n8n": False,
                "message_type": "template",
                "template_name": ref["template_name"],
                "language_code": ref["language_code"],
                "provider_message_id": pmid,
                "conversation": result.get("conversation"),
                "message": result.get("message"),
                "deduplicated": bool(result.get("deduplicated")),
                "delivery_context": context,
            }
        return {
            "ok": False,
            "mode": "failed",
            "error": result.get("error") or "provider_message_id_missing",
            "error_category": "provider_rejected",
            "delivery_context": context,
        }

    if _is_n8n_bridge(integration.get("configuration")) or str(
        integration.get("provider") or ""
    ).casefold() in ("stub", "n8n"):
        return {
            "ok": True,
            "mode": "n8n",
            "deferred_to_n8n": True,
            "message_type": "template",
            "template_name": ref["template_name"],
            "language_code": ref["language_code"],
            "provider_message_id": None,
            "delivery_context": context,
        }

    return {
        "ok": False,
        "mode": "failed",
        "error": "meta_credentials_not_configured",
        "error_category": "meta_credentials_not_configured",
        "delivery_context": context,
    }

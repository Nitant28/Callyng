"""Channel eligibility for automatic / manual follow-ups."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from lead_upload.normaliser import normalise_phone
from messages.eligibility import parse_whatsapp_opt_in


def evaluate_channel_eligibility(
    *,
    client_id: UUID | str | None,
    campaign_id: UUID | str | None,
    lead_id: Any = None,
    outcome: str | None = None,
    follow_up_target: str | None = None,
    lead: dict[str, Any] | None = None,
    first_contact: dict[str, Any] | None = None,
    whatsapp_integration: dict[str, Any] | None = None,
    qualification: dict[str, Any] | None = None,
    require_qualified: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    lead = lead or {}
    fc = first_contact or {}
    phone = normalise_phone(str(lead.get("phone") or "")) or str(lead.get("phone") or "").strip()
    raw_meta = lead.get("metadata")
    if isinstance(raw_meta, dict):
        meta = raw_meta
    elif isinstance(raw_meta, str) and raw_meta.strip():
        import json

        try:
            parsed = json.loads(raw_meta)
            meta = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            meta = {}
    else:
        meta = {}
    opt_in = parse_whatsapp_opt_in(meta)
    # Explicit manual send from the product UI is treated as operator consent.
    # Auto/post-call paths stay fail-closed on missing opt-in.
    manual_override = str(source or "").strip().casefold() == "manual"

    wa: dict[str, Any] = {"eligible": False, "reason": None}
    email: dict[str, Any] = {"eligible": False, "reason": None}

    if require_qualified:
        from followups.interested import evaluate_qualification

        decision = evaluate_qualification(outcome, follow_up_target)
        if not decision.get("qualified"):
            return {
                "any_eligible": False,
                "channels": {
                    "whatsapp": {"eligible": False, "reason": "lead_not_interested"},
                    "email": {"eligible": False, "reason": "lead_not_interested"},
                },
                "qualification": decision,
            }

    if not phone:
        wa = {"eligible": False, "reason": "missing_or_invalid_phone"}
    elif not opt_in and not manual_override:
        wa = {"eligible": False, "reason": "whatsapp_opt_in_required"}
    elif fc.get("can_send") is False:
        wa = {
            "eligible": False,
            "reason": str(fc.get("reason") or "template_not_configured"),
        }
    elif not whatsapp_integration and fc.get("can_send") is not True:
        # Integration may be attached later; if plan already allows send, proceed.
        if fc.get("can_send") is True:
            wa = {"eligible": True, "reason": None}
        else:
            wa = {"eligible": False, "reason": "whatsapp_integration_missing"}
    else:
        wa = {"eligible": True, "reason": None}

    email_addr = str(lead.get("email") or meta.get("email") or "").strip()
    if email_addr and "@" in email_addr:
        email = {"eligible": True, "reason": None}
    else:
        email = {"eligible": False, "reason": "missing_email"}

    return {
        "any_eligible": bool(wa.get("eligible") or email.get("eligible")),
        "channels": {"whatsapp": wa, "email": email},
        "client_id": str(client_id) if client_id else None,
        "campaign_id": str(campaign_id) if campaign_id else None,
        "lead_id": str(lead_id) if lead_id else None,
    }


def any_channel_eligible(decision: dict[str, Any] | None) -> bool:
    return bool((decision or {}).get("any_eligible"))

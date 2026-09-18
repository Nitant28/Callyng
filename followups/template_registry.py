"""Production WhatsApp template registry helpers.

Meta sample templates (e.g. hello_world) are never production fallbacks.
"""

from __future__ import annotations

import os
from typing import Any

from followups.template_ref import TemplateRefError, normalize_template_ref

PURPOSE_INTERESTED_INITIAL = "interested_lead_initial_followup"
PURPOSE_CALLBACK = "callback_confirmation"
PURPOSE_APPOINTMENT = "appointment_confirmation"
PURPOSE_REMINDER = "followup_reminder"
PURPOSE_REENGAGEMENT = "reengagement"

SAMPLE_TEMPLATE_NAMES = frozenset({"hello_world"})
RECOMMENDED_INTERESTED_TEMPLATE = "bhuvisx_interested_lead_followup"


def sample_templates_allowed() -> bool:
    """Interim only — must stay off in production."""
    return str(os.getenv("WHATSAPP_ALLOW_SAMPLE_TEMPLATE") or "").strip().casefold() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_sample_template(name: str | None) -> bool:
    return str(name or "").strip().casefold() in SAMPLE_TEMPLATE_NAMES


def recommended_interested_template_name() -> str:
    """Production name — never hello_world."""
    raw = (
        os.getenv("WHATSAPP_INTERESTED_TEMPLATE")
        or os.getenv("N8N_FIRST_CONTACT_TEMPLATE")
        or RECOMMENDED_INTERESTED_TEMPLATE
    ).strip()
    if not raw or is_sample_template(raw):
        return RECOMMENDED_INTERESTED_TEMPLATE
    try:
        from followups.template_ref import normalize_template_name

        return normalize_template_name(raw)
    except TemplateRefError:
        return RECOMMENDED_INTERESTED_TEMPLATE


def recommended_language_code() -> str:
    raw = (
        os.getenv("WHATSAPP_INTERESTED_LANGUAGE")
        or os.getenv("N8N_FIRST_CONTACT_LANGUAGE")
        or "en_US"
    ).strip()
    try:
        from followups.template_ref import normalize_language_code

        return normalize_language_code(raw or "en_US")
    except TemplateRefError:
        return "en_US"


def registry_entry_from_first_contact(
    fc: dict[str, Any] | None,
    *,
    purpose: str = PURPOSE_INTERESTED_INITIAL,
) -> dict[str, Any] | None:
    if not isinstance(fc, dict):
        return None
    name = str(fc.get("template_name") or fc.get("name") or "").strip()
    if not name:
        return None
    try:
        ref = normalize_template_ref(
            name, fc.get("language_code") or fc.get("language") or recommended_language_code()
        )
    except TemplateRefError:
        return None
    if is_sample_template(ref["template_name"]) and not sample_templates_allowed():
        return None
    enabled = bool(fc.get("enabled", True))
    approved = bool(fc.get("approved", False))
    status = str(fc.get("status") or ("APPROVED" if approved else "PENDING")).upper()
    if approved and status in ("", "DRAFT", "PENDING"):
        status = "APPROVED"
    return {
        "template_name": ref["template_name"],
        "language_code": ref["language_code"],
        "purpose": str(fc.get("purpose") or purpose).strip() or purpose,
        "category": str(fc.get("category") or "").strip() or None,
        "enabled": enabled,
        "approved": approved and status in ("APPROVED", "ACTIVE"),
        "status": status,
        "variables": fc.get("variables") if isinstance(fc.get("variables"), list) else [],
    }


def select_production_template(
    *,
    first_contact_config: dict[str, Any] | None,
    registry_rows: list[dict[str, Any]] | None = None,
    purpose: str = PURPOSE_INTERESTED_INITIAL,
) -> dict[str, Any]:
    entry = registry_entry_from_first_contact(first_contact_config, purpose=purpose)
    if entry and entry["enabled"] and entry["approved"]:
        return {"ok": True, **entry}
    if entry and not entry["enabled"]:
        return {"ok": False, "error": "first_contact_template_disabled", "candidate": entry}
    if entry and not entry["approved"]:
        return {"ok": False, "error": "first_contact_template_not_approved", "candidate": entry}

    for row in registry_rows or []:
        if not isinstance(row, dict):
            continue
        components = row.get("components") if isinstance(row.get("components"), dict) else {}
        row_purpose = str(components.get("purpose") or PURPOSE_INTERESTED_INITIAL).strip()
        if row_purpose != purpose:
            continue
        status = str(row.get("status") or "").strip().upper()
        if status not in ("APPROVED", "ACTIVE"):
            continue
        try:
            ref = normalize_template_ref(row.get("name"), row.get("language") or recommended_language_code())
        except TemplateRefError:
            continue
        if is_sample_template(ref["template_name"]) and not sample_templates_allowed():
            continue
        return {
            "ok": True,
            "template_name": ref["template_name"],
            "language_code": ref["language_code"],
            "purpose": purpose,
            "category": row.get("category"),
            "enabled": True,
            "approved": True,
            "status": status,
            "variables": components.get("variables") if isinstance(components.get("variables"), list) else [],
            "registry_id": str(row.get("id")) if row.get("id") else None,
        }

    return {
        "ok": False,
        "error": "template_not_configured",
        "error_alias": "first_contact_template_not_configured",
        "recommended_template_name": recommended_interested_template_name(),
        "recommended_language_code": recommended_language_code(),
        "purpose": purpose,
    }

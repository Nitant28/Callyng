"""Campaign-scoped lead field configuration helpers."""

from __future__ import annotations

from typing import Any


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def resolve_campaign_field_config(
    campaign: dict[str, Any] | None,
    schema_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge campaign.lead_field_config with lead-schema fields.

    Returns a dict used by lead create/update validation. Missing config is
    treated as permissive (no required custom fields).
    """
    camp = campaign or {}
    stored = _as_dict(camp.get("lead_field_config"))
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()

    for f in schema_fields or []:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        fields.append(
            {
                "key": key,
                "label": str(f.get("label") or key),
                "required": bool(f.get("required", False)),
                "type": str(f.get("type") or "text"),
            }
        )

    for f in stored.get("fields") or stored.get("custom_fields") or []:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        fields.append(
            {
                "key": key,
                "label": str(f.get("label") or key),
                "required": bool(f.get("required", False)),
                "type": str(f.get("type") or "text"),
            }
        )

    return {
        "enabled": bool(stored.get("enabled", True)),
        "require_name": bool(stored.get("require_name", True)),
        "require_phone": bool(stored.get("require_phone", True)),
        "fields": fields,
        "raw": stored,
    }


def validate_lead_against_config(
    *,
    config: dict[str, Any] | None,
    name: Any = None,
    phone: Any = None,
    lead_type: Any = None,
    metadata: dict[str, Any] | None = None,
    is_create: bool = True,
) -> list[str]:
    """Return a list of human-readable validation errors (empty = ok)."""
    cfg = config or {}
    if cfg.get("enabled") is False:
        return []

    errors: list[str] = []
    meta = metadata if isinstance(metadata, dict) else {}

    if cfg.get("require_name", True) and not str(name or "").strip():
        if is_create or name is not None:
            errors.append("Name is required")
    if cfg.get("require_phone", True) and not str(phone or "").strip():
        if is_create or phone is not None:
            errors.append("Phone is required")

    for field in cfg.get("fields") or []:
        if not isinstance(field, dict) or not field.get("required"):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        val = meta.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            label = str(field.get("label") or key)
            errors.append(f"{label} is required")

    _ = lead_type  # reserved for future type-specific rules
    return errors

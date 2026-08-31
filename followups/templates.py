"""First-contact WhatsApp template configuration.

WhatsApp only permits a free-form message inside the 24-hour customer-service
window, which is closed by definition for a lead who has never messaged us. The
first touch therefore needs a Meta-approved template. No template name, language
or variable mapping is hardcoded here: it is configured per client and supplied
after Meta approval. Until then :func:`plan_first_contact` reports ``blocked``
rather than pretending the path is production-ready.

Config lives in ``whatsapp_integrations.configuration -> first_contact_template``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from followups.context import LeadContext, clean
from followups.generators._text import format_budget

CONFIG_KEY = "first_contact_template"
DEFAULT_LANGUAGE = "en"

MODE_TEXT = "text"
MODE_TEMPLATE = "template"
MODE_BLOCKED = "blocked"

MAX_PARAMETER_CHARS = 900

VARIABLE_SOURCES: dict[str, Callable[[LeadContext], str | None]] = {
    "lead_name": lambda ctx: ctx.name,
    "first_name": lambda ctx: ctx.first_name,
    "client_name": lambda ctx: ctx.client_name,
    "client_industry": lambda ctx: ctx.client_industry,
    "campaign_name": lambda ctx: ctx.campaign_name,
    "city": lambda ctx: ctx.city,
    "property_type": lambda ctx: ctx.property_type,
    "bhk_preference": lambda ctx: ctx.bhk_preference,
    "location_preference": lambda ctx: ctx.location_preference,
    "locality": lambda ctx: ctx.locality,
    "budget": lambda ctx: format_budget(ctx.budget),
    "summary": lambda ctx: ctx.summary,
    "callback_time": lambda ctx: ctx.callback_time,
}


@dataclass(frozen=True)
class TemplateVariable:
    """One positional body parameter of the approved template."""

    index: int
    source: str
    fallback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "source": self.source, "fallback": self.fallback}


@dataclass(frozen=True)
class FirstContactTemplate:
    enabled: bool = False
    approved: bool = False
    template_name: str | None = None
    language_code: str = DEFAULT_LANGUAGE
    phone_number_id: str | None = None
    variables: tuple[TemplateVariable, ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        """True only when a real, approved template has been configured."""
        return bool(self.template_name) and self.enabled and self.approved

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "approved": self.approved,
            "template_name": self.template_name,
            "language_code": self.language_code,
            "phone_number_id": self.phone_number_id,
            "variables": [v.to_dict() for v in self.variables],
        }


@dataclass(frozen=True)
class FirstContactPlan:
    """How the first outbound message may be delivered, if at all."""

    mode: str
    reason: str | None = None
    template_name: str | None = None
    language_code: str | None = None
    parameters: tuple[str, ...] = field(default_factory=tuple)
    components: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    phone_number_id: str | None = None

    @property
    def can_send(self) -> bool:
        return self.mode in (MODE_TEXT, MODE_TEMPLATE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "template_name": self.template_name,
            "language_code": self.language_code,
            "parameters": list(self.parameters),
            "components": [dict(c) for c in self.components],
            "phone_number_id": self.phone_number_id,
            "can_send": self.can_send,
        }


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().casefold() in ("1", "true", "yes", "y", "on")


def _parse_variables(raw: Any) -> tuple[TemplateVariable, ...]:
    if not isinstance(raw, list):
        return ()
    parsed: list[TemplateVariable] = []
    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        source = clean(item.get("source"))
        if not source:
            continue
        try:
            index = int(item.get("index") or position)
        except (TypeError, ValueError):
            index = position
        parsed.append(
            TemplateVariable(
                index=index,
                source=source,
                fallback=str(item.get("fallback") or "").strip(),
            )
        )
    return tuple(sorted(parsed, key=lambda v: v.index))


def parse_first_contact_template(configuration: Any) -> FirstContactTemplate:
    """Read the template config off an integration row's ``configuration`` JSONB."""
    config = configuration if isinstance(configuration, dict) else {}
    raw = config.get(CONFIG_KEY)
    if not isinstance(raw, dict):
        return FirstContactTemplate()
    return FirstContactTemplate(
        enabled=_as_bool(raw.get("enabled")),
        approved=_as_bool(raw.get("approved")),
        template_name=clean(raw.get("template_name")),
        language_code=clean(raw.get("language_code")) or DEFAULT_LANGUAGE,
        phone_number_id=clean(raw.get("phone_number_id")) or clean(config.get("phone_number_id")),
        variables=_parse_variables(raw.get("variables")),
    )


def _sanitise_parameter(value: str) -> str:
    """Meta rejects newlines, tabs and runs of spaces inside template params."""
    collapsed = re.sub(r"\s+", " ", str(value)).strip()
    return collapsed[:MAX_PARAMETER_CHARS]


def resolve_variables(
    template: FirstContactTemplate,
    ctx: LeadContext,
) -> tuple[list[str], str | None]:
    """Resolve positional parameters, or report the first one we cannot fill."""
    resolved: list[str] = []
    for variable in template.variables:
        source = VARIABLE_SOURCES.get(variable.source)
        raw = source(ctx) if source else None
        value = clean(raw) or variable.fallback
        if not str(value).strip():
            if variable.source not in VARIABLE_SOURCES:
                return [], f"unknown_variable_source:{variable.source}"
            return [], f"unresolved_variable:{variable.index}:{variable.source}"
        resolved.append(_sanitise_parameter(value))
    return resolved, None


def build_components(parameters: list[str]) -> tuple[dict[str, Any], ...]:
    """Meta Cloud API body component for positional text parameters."""
    if not parameters:
        return ()
    return (
        {
            "type": "body",
            "parameters": [{"type": "text", "text": value} for value in parameters],
        },
    )


def plan_first_contact(
    template: FirstContactTemplate,
    ctx: LeadContext,
    *,
    conversation_window_open: bool,
) -> FirstContactPlan:
    """Decide how the first outbound WhatsApp message may be delivered.

    Free-form text is only allowed while the customer-service window is open.
    Otherwise an approved template is mandatory, and if none is configured the
    plan is ``blocked`` so callers do not send something Meta will reject.
    """
    # Prefer an approved template for the first outbound, even inside the 24h
    # window — session text is only a fallback when no template is configured.
    if template.is_usable:
        parameters, error = resolve_variables(template, ctx)
        if not error:
            return FirstContactPlan(
                mode=MODE_TEMPLATE,
                reason="approved_template" if not conversation_window_open else "template_preferred",
                template_name=template.template_name,
                language_code=template.language_code,
                parameters=tuple(parameters),
                components=build_components(parameters),
                phone_number_id=template.phone_number_id,
            )

    if conversation_window_open:
        return FirstContactPlan(mode=MODE_TEXT, reason="conversation_window_open")

    if not template.template_name:
        return FirstContactPlan(mode=MODE_BLOCKED, reason="first_contact_template_not_configured")
    if not template.approved:
        return FirstContactPlan(mode=MODE_BLOCKED, reason="first_contact_template_not_approved")
    if not template.enabled:
        return FirstContactPlan(mode=MODE_BLOCKED, reason="first_contact_template_disabled")

    parameters, error = resolve_variables(template, ctx)
    if error:
        return FirstContactPlan(mode=MODE_BLOCKED, reason=error)

    return FirstContactPlan(
        mode=MODE_TEMPLATE,
        reason=None,
        template_name=template.template_name,
        language_code=template.language_code,
        parameters=tuple(parameters),
        components=build_components(parameters),
        phone_number_id=template.phone_number_id,
    )


def select_template_config(integrations: list[dict[str, Any]] | None) -> FirstContactTemplate:
    """Pick the first-contact template from a client's integrations.

    Prefers an enabled integration that actually has a usable template configured.
    """
    rows = integrations or []
    candidates = [parse_first_contact_template(row.get("configuration")) for row in rows]
    for template in candidates:
        if template.is_usable:
            return template
    for row, template in zip(rows, candidates):
        if _as_bool(row.get("enabled")) and template.template_name:
            return template
    return candidates[0] if candidates else FirstContactTemplate()

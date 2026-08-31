"""Verified lead context shared by every follow-up generator.

Only fields that came from the database or the call extraction land here. A field
that is missing, blank or a placeholder string is normalised to ``None`` so the
deterministic generators can never reference information we do not actually have.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

_PLACEHOLDER_VALUES = frozenset(
    {"", "none", "null", "nil", "undefined", "n/a", "na", "-", "--", "unknown", "not specified"}
)

INITIAL_FOLLOWUP = "INITIAL_FOLLOWUP"
CONTINUE_CHAT = "CONTINUE_CHAT"


def clean(value: Any) -> str | None:
    """Return a trimmed string, or None for blank/placeholder values."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text.casefold() in _PLACEHOLDER_VALUES:
        return None
    return text


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _pick(*values: Any) -> str | None:
    for value in values:
        cleaned = clean(value)
        if cleaned:
            return cleaned
    return None


@dataclass(frozen=True)
class LeadContext:
    """Immutable snapshot of everything we may legitimately say to a customer."""

    lead_id: str | None = None
    client_id: str | None = None
    campaign_id: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    client_name: str | None = None
    client_industry: str | None = None
    campaign_name: str | None = None
    city: str | None = None
    property_type: str | None = None
    bhk_preference: str | None = None
    location_preference: str | None = None
    budget: str | None = None
    summary: str | None = None
    callback_time: str | None = None
    intent_status: str | None = None
    lead_type: str | None = None
    flow_type: str = INITIAL_FOLLOWUP

    @property
    def first_name(self) -> str | None:
        if not self.name:
            return None
        return self.name.split()[0]

    @property
    def company(self) -> str | None:
        return self.client_name

    @property
    def locality(self) -> str | None:
        """Where the customer wants to buy, falling back to where they live."""
        return self.location_preference or self.city

    @property
    def is_continue_chat(self) -> bool:
        return str(self.flow_type or "").strip().upper() in {CONTINUE_CHAT, "INBOUND_REPLY"}

    def with_flow(self, flow_type: str) -> LeadContext:
        return replace(self, flow_type=flow_type)

    @classmethod
    def from_lead_row(
        cls,
        lead: dict[str, Any] | None,
        *,
        campaign: dict[str, Any] | None = None,
        client: dict[str, Any] | None = None,
        extraction: dict[str, Any] | None = None,
        flow_type: str = INITIAL_FOLLOWUP,
    ) -> LeadContext:
        lead = lead or {}
        campaign = campaign or {}
        client = client or {}
        meta = _as_dict(lead.get("metadata"))
        ext = _as_dict(extraction) or _as_dict(lead.get("extraction_json")) or _as_dict(lead.get("extraction"))

        return cls(
            lead_id=_pick(lead.get("id")),
            client_id=_pick(lead.get("client_id"), client.get("id")),
            campaign_id=_pick(lead.get("campaign_id"), campaign.get("id")),
            name=_pick(lead.get("name"), meta.get("name")),
            phone=_pick(lead.get("phone")),
            email=_pick(lead.get("email"), meta.get("email")),
            client_name=_pick(client.get("name"), meta.get("client_name")),
            client_industry=_pick(client.get("industry")),
            campaign_name=_pick(campaign.get("name")),
            city=_pick(meta.get("lead_city"), meta.get("city")),
            property_type=_pick(ext.get("property_type"), meta.get("property_type")),
            bhk_preference=_pick(ext.get("bhk_preference"), meta.get("bhk_preference")),
            location_preference=_pick(ext.get("location_preference"), meta.get("location_preference")),
            budget=_pick(ext.get("budget"), meta.get("budget")),
            summary=_pick(ext.get("summary"), meta.get("summary")),
            callback_time=_pick(ext.get("callback_time"), meta.get("callback_time")),
            intent_status=_pick(ext.get("intent_status"), lead.get("outcome")),
            lead_type=_pick(lead.get("lead_type")),
            flow_type=flow_type or INITIAL_FOLLOWUP,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> LeadContext:
        """Build from a Mega_Workflow ``lead_qualified`` payload."""
        payload = payload or {}
        lead = _as_dict(payload.get("lead"))
        return cls.from_lead_row(
            {**lead, "client_id": payload.get("client_id")},
            campaign=_as_dict(payload.get("campaign")),
            client=_as_dict(payload.get("client")),
            extraction=_as_dict(payload.get("extraction")),
            flow_type=_pick(payload.get("flow_type")) or INITIAL_FOLLOWUP,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "client_id": self.client_id,
            "campaign_id": self.campaign_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "client_name": self.client_name,
            "client_industry": self.client_industry,
            "campaign_name": self.campaign_name,
            "city": self.city,
            "property_type": self.property_type,
            "bhk_preference": self.bhk_preference,
            "location_preference": self.location_preference,
            "budget": self.budget,
            "summary": self.summary,
            "callback_time": self.callback_time,
            "intent_status": self.intent_status,
            "lead_type": self.lead_type,
            "flow_type": self.flow_type,
        }

"""Per-call lead fields passed into STS / cascade script modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeadContext:
    """Built from ``runner_args.body`` (+ server-injected ``phone_number``)."""

    lead_name: str
    lead_phone: str = ""
    lead_city: str = ""

    @classmethod
    def from_body(cls, body: dict, *, default_lead_name: str = "Sir / Madam") -> "LeadContext":
        b = body or {}
        name = (b.get("lead_name") or default_lead_name).strip() or default_lead_name
        phone = str(b.get("phone_number") or "").strip()
        city = str(b.get("city") or "").strip()
        return cls(lead_name=name, lead_phone=phone, lead_city=city)

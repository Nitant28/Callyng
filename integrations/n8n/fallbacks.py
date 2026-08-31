"""Deterministic follow-up copy when Gemini/n8n AI fails. Not an AI call."""

from __future__ import annotations

from typing import Any


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first_name(name: str) -> str:
    token = name.split()[0] if name else ""
    return token if token and token.lower() not in {"there", "customer", "lead"} else name


def _search_bits(extraction: dict[str, Any], meta: dict[str, Any]) -> str:
    bhk = _clean(extraction.get("bhk_preference") or meta.get("bhk_preference"))
    loc = _clean(
        extraction.get("location_preference")
        or meta.get("location_preference")
        or meta.get("lead_city")
        or meta.get("city")
    )
    budget = _clean(extraction.get("budget") or meta.get("budget"))
    parts = [p for p in (bhk, loc, f"budget {budget}" if budget else "") if p]
    return ", ".join(parts)


def fallback_initial_whatsapp(
    *,
    name: str | None,
    client_name: str | None,
    extraction: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    extraction = extraction or {}
    metadata = metadata or {}
    first = _first_name(_clean(name)) or "there"
    client = _clean(client_name) or "our team"
    about = _search_bits(extraction, metadata)
    if about:
        return (
            f"Hi {first}, thank you for speaking with {client}. "
            f"We noted your interest in {about}. "
            f"Reply here and we will help with the next step."
        )
    return (
        f"Hi {first}, thank you for speaking with {client}. "
        f"We are following up on your call. Reply here with any questions and we will assist you."
    )


def fallback_initial_email(
    *,
    name: str | None,
    client_name: str | None,
    extraction: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    extraction = extraction or {}
    metadata = metadata or {}
    first = _first_name(_clean(name)) or "there"
    client = _clean(client_name) or "our team"
    about = _search_bits(extraction, metadata)
    summary = _clean(extraction.get("summary") or extraction.get("reason"))
    subject = f"Following up from {client}"
    lines = [
        f"Hi {first},",
        "",
        f"Thank you for speaking with {client} today.",
    ]
    if about:
        lines.append(f"We noted your interest in {about}.")
    if summary:
        lines.append(f"Call summary: {summary}")
    lines.extend(
        [
            "A specialist will continue over WhatsApp. You can also reply to this email.",
            "",
            "Regards,",
            client,
        ]
    )
    return subject, "\n".join(lines)


def fallback_inbound_whatsapp(
    *,
    name: str | None,
    client_name: str | None,
    inbound_text: str | None = None,
    extraction: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    extraction = extraction or {}
    metadata = metadata or {}
    first = _first_name(_clean(name)) or "there"
    client = _clean(client_name) or "our team"
    about = _search_bits(extraction, metadata)
    text = _clean(inbound_text).lower()
    who = any(k in text for k in ("who is this", "who are you", "who's this", "who is u"))
    if who:
        if about:
            return (
                f"Hi {first}, this is {client} following up on your enquiry about {about}. "
                f"Happy to help with the options you were looking at. "
                f"What type of property are you interested in?"
            )
        return (
            f"Hi {first}, this is {client} following up on your enquiry. "
            f"I'd be happy to help with the options you were looking for. "
            f"What type of property are you interested in?"
        )
    if about:
        return (
            f"Thanks {first} — noted. Based on your earlier interest in {about}, "
            f"could you share a bit more (location, BHK, or budget) so we can share the right options?"
        )
    return (
        f"Thanks {first}. I've got your message. "
        f"Could you tell me the location and type of property you're looking for so I can help further?"
    )

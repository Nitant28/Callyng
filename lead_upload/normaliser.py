"""Phone normalisation to E.164 (India default)."""

from __future__ import annotations

import phonenumbers


def normalise_phone(raw: str, default_region: str = "IN") -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = phonenumbers.parse(text, default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        return None


def last10_digits(raw: str, default_region: str = "IN") -> str | None:
    """Canonical last-10 national digits for India-centric lead matching."""
    normalized = normalise_phone(raw, default_region)
    digits = "".join(ch for ch in (normalized or raw or "") if ch.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits or None

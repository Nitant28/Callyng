"""Canonical interested/not-interested matching.

Substring checks like ``"interest" in outcome`` are unsafe because
``"not interested"`` contains that substring. All auto-follow-up gates
must use this helper.
"""

from __future__ import annotations

_POSITIVE = frozenset({"interested", "hot", "warm", "qualified"})
_NEGATIVE = frozenset(
    {
        "not interested",
        "not_interested",
        "uninterested",
        "disinterested",
        "no",
        "nope",
        "stop",
        "unsubscribe",
    }
)


def canonicalize_intent(raw: str | None) -> str:
    return " ".join((raw or "").strip().casefold().replace("-", " ").replace("_", " ").split())


def is_negative_intent(raw: str | None) -> bool:
    s = canonicalize_intent(raw)
    if not s:
        return False
    if s in _NEGATIVE or s.replace(" ", "_") in _NEGATIVE:
        return True
    return s.startswith("not ")


def is_interested_outcome(raw: str | None) -> bool:
    """True only for genuine positive interest labels."""
    s = canonicalize_intent(raw)
    if not s or is_negative_intent(s):
        return False
    return s in _POSITIVE

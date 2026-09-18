"""Canonical interested/not-interested matching and follow-up target evaluation.

Substring checks like ``"interest" in outcome`` are unsafe because
``"not interested"`` contains that substring. All auto-follow-up gates
must use this helper.
"""

from __future__ import annotations

from typing import Any

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

DEFAULT_FOLLOW_UP_TARGET = "interested"
FOLLOW_UP_TARGET_OPTIONS = (
    {"value": "interested", "label": "Interested only"},
    {"value": "qualified", "label": "Qualified / hot / warm / interested"},
    {"value": "all_positive", "label": "Any positive intent"},
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


def evaluate_qualification(
    outcome: str | None,
    follow_up_target: str | None = None,
) -> dict[str, Any]:
    """Return ``{eligible, qualified, target, outcome}`` for auto follow-up gates."""
    target = (follow_up_target or DEFAULT_FOLLOW_UP_TARGET).strip().casefold() or DEFAULT_FOLLOW_UP_TARGET
    s = canonicalize_intent(outcome)
    qualified = is_interested_outcome(s)
    if target in ("all_positive", "qualified"):
        eligible = qualified
    else:
        # Default: interested-family only (same set as is_interested_outcome today).
        eligible = qualified
    return {
        "eligible": bool(eligible),
        "qualified": bool(qualified),
        "target": target,
        "outcome": s or None,
    }

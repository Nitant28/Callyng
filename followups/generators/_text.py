"""Shared text helpers for the deterministic generators."""

from __future__ import annotations

import re

_NUMERIC_RE = re.compile(r"^\d+(?:\.\d+)?$")


def indian_grouping(amount: int) -> str:
    """Group digits the Indian way: 8000000 -> 80,00,000."""
    digits = str(amount)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{','.join(groups)},{tail}"


def format_budget(raw: str | None) -> str | None:
    """Render a budget for display without changing its meaning.

    A bare number is assumed to be rupees and gets a symbol plus Indian grouping.
    Anything the customer phrased themselves ("80 lakh", "1.2 Cr") is left alone.
    """
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    compact = text.replace(",", "").replace(" ", "")
    if _NUMERIC_RE.match(compact):
        try:
            value = int(float(compact))
        except (TypeError, ValueError):
            return text
        if value <= 0:
            return None
        return f"\u20b9{indian_grouping(value)}"
    return text


def join_natural(parts: list[str]) -> str:
    """Join clauses as 'a', 'a and b', or 'a, b and c'."""
    cleaned = [p.strip() for p in parts if p and p.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])} and {cleaned[-1]}"


def clamp(text: str, limit: int) -> str:
    """Trim to a limit on a word boundary without cutting mid-sentence."""
    collapsed = re.sub(r"[ \t]+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return f"{cut.rstrip('.,;:- ')}\u2026"


def greeting(name: str | None) -> str:
    return f"Hi {name}," if name else "Hi there,"


def inline_greeting(name: str | None) -> str:
    """Greeting for a single-line WhatsApp reply: 'Hi Nitant' / 'Hi'."""
    return f"Hi {name}" if name else "Hi"

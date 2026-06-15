"""TRAI-style compliance checks before outbound dials."""

from __future__ import annotations

import os
from datetime import datetime

from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv(override=True)

_IST = ZoneInfo("Asia/Kolkata")

# Internal opt-out list (E.164). Extend via env or DB in a later phase.
_DND_NUMBERS: set[str] = set()


def _load_dnd_from_env() -> None:
    raw = (os.getenv("INTERNAL_DND_NUMBERS") or "").strip()
    if not raw:
        return
    for part in raw.split(","):
        p = part.strip()
        if p:
            _DND_NUMBERS.add(p)


_load_dnd_from_env()


def add_dnd(phone: str) -> None:
    _DND_NUMBERS.add(phone)


from datetime import timedelta

def is_call_allowed(phone: str) -> tuple[bool, str]:
    now_ist = datetime.now(tz=_IST)
    if not (9 <= now_ist.hour < 21):
        return False, "outside 9am-9pm IST window"
    if phone in _DND_NUMBERS:
        return False, "number on internal DND list"
    return True, "ok"

def next_compliant_time() -> datetime:
    """Returns the next available 9 AM IST timestamp."""
    now_ist = datetime.now(tz=_IST)
    if now_ist.hour < 9:
        return now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    next_day = now_ist + timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)

"""TRAI-style compliance checks before outbound dials."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import timedelta

_IST = ZoneInfo("Asia/Kolkata")


def is_call_allowed() -> tuple[bool, str]:
    now_ist = datetime.now(tz=_IST)
    if not (9 <= now_ist.hour < 21):
        return False, "outside 9am-9pm IST window"
    return True, "ok"

def next_compliant_time() -> datetime:
    """Returns the next available 9 AM IST timestamp."""
    now_ist = datetime.now(tz=_IST)
    if now_ist.hour < 9:
        return now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    next_day = now_ist + timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)

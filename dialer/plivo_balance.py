"""Plivo account balance guard for the campaign dialer."""

from __future__ import annotations

import os
import time
from decimal import Decimal

import aiohttp
from loguru import logger

from telephony import fetch_plivo_cash_credits, plivo_error_is_insufficient_balance

_cache_balance: Decimal | None = None
_cache_at: float = 0.0


def _min_plivo_balance_usd() -> Decimal:
    raw = (os.getenv("PLIVO_MIN_BALANCE_USD") or "0.50").strip()
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("0.50")


def _cache_ttl_seconds() -> float:
    raw = (os.getenv("PLIVO_BALANCE_CACHE_SECONDS") or "30").strip()
    try:
        return max(float(raw), 5.0)
    except ValueError:
        return 30.0


def invalidate_plivo_balance_cache() -> None:
    global _cache_balance, _cache_at
    _cache_balance = None
    _cache_at = 0.0


async def get_plivo_cash_credits_cached(
    session: aiohttp.ClientSession,
) -> Decimal | None:
    """Cached Plivo ``cash_credits``; None if the account API is unreachable."""
    global _cache_balance, _cache_at
    now = time.monotonic()
    if _cache_balance is not None and (now - _cache_at) < _cache_ttl_seconds():
        return _cache_balance
    try:
        balance = await fetch_plivo_cash_credits(session)
    except Exception as exc:
        logger.warning("Plivo balance check failed: {}", exc)
        return None
    _cache_balance = balance
    _cache_at = now
    return balance


async def check_plivo_balance(session: aiohttp.ClientSession) -> bool:
    """
    Return False when Plivo prepaid balance is at or below the minimum threshold.
    If the balance API fails, return True (do not block dials on transient errors).
    """
    balance = await get_plivo_cash_credits_cached(session)
    if balance is None:
        return True
    ok = balance > _min_plivo_balance_usd()
    if not ok:
        logger.error(
            "Plivo cash_credits={} below minimum {} — dialer must pause",
            balance,
            _min_plivo_balance_usd(),
        )
    return ok


def exception_is_plivo_balance_exhausted(exc: BaseException) -> bool:
    msg = str(exc)
    if "Plivo error" not in msg:
        return False
    # Format: Plivo error (402): {...}
    status = 0
    for part in msg.split():
        if part.startswith("(") and part.endswith("):"):
            try:
                status = int(part[1:-2])
            except ValueError:
                pass
    return plivo_error_is_insufficient_balance(status, msg)

"""Telnyx account balance guard for the campaign dialer."""

from __future__ import annotations

import os
import time
from decimal import Decimal

import aiohttp
from loguru import logger

from telephony import fetch_telnyx_balance, telnyx_error_is_insufficient_balance

_balance_cache: tuple[float, Decimal | None] = (0.0, None)


def _min_telnyx_balance_usd() -> Decimal:
    raw = (os.getenv("TELNYX_MIN_BALANCE_USD") or "0.50").strip()
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("0.50")


def _balance_cache_ttl_s() -> float:
    raw = (os.getenv("TELNYX_BALANCE_CACHE_SECONDS") or "30").strip()
    try:
        return max(1.0, float(raw))
    except Exception:
        return 30.0


def invalidate_telnyx_balance_cache() -> None:
    global _balance_cache
    _balance_cache = (0.0, None)


invalidate_plivo_balance_cache = invalidate_telnyx_balance_cache


async def get_telnyx_balance_cached(
    session: aiohttp.ClientSession,
) -> Decimal | None:
    """Cached Telnyx balance in USD; None if the account API is unreachable."""
    global _balance_cache
    now = time.monotonic()
    ts, val = _balance_cache
    if val is not None and (now - ts) < _balance_cache_ttl_s():
        return val
    try:
        balance = await fetch_telnyx_balance(session)
        _balance_cache = (now, balance)
        return balance
    except Exception as exc:
        logger.warning("Telnyx balance check failed: {}", exc)
        _balance_cache = (now, None)
        return None


get_plivo_cash_credits_cached = get_telnyx_balance_cached


async def check_telnyx_balance(session: aiohttp.ClientSession) -> bool:
    """Return False when Telnyx prepaid balance is at or below the minimum threshold.

    If the balance check API is down, returns True (fail-open) so outages in
    the Telnyx account API don't block the dialer indefinitely.
    """
    balance = await get_telnyx_balance_cached(session)
    if balance is None:
        return True
    ok = balance > _min_telnyx_balance_usd()
    if not ok:
        logger.warning(
            "Telnyx balance={} below minimum {} — dialer must pause",
            balance,
            _min_telnyx_balance_usd(),
        )
    return ok


check_plivo_balance = check_telnyx_balance


def exception_is_telnyx_balance_exhausted(exc: BaseException) -> bool:
    """True when an exception from make_telnyx_call represents insufficient balance."""
    msg = str(exc)
    if "Telnyx error" not in msg and "Plivo error" not in msg and "balance" not in msg.lower():
        return False
    status = 500
    if "(402)" in msg or "402" in msg:
        status = 402
    elif "(403)" in msg or "403" in msg:
        status = 403
    return telnyx_error_is_insufficient_balance(status, msg)


exception_is_plivo_balance_exhausted = exception_is_telnyx_balance_exhausted

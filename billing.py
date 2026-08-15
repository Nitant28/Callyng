"""Per-second call billing and claim-time reservation math.

Rates are never hardcoded here. Callers pass the bot's credits_per_minute
and fixed_start_credits. All money math uses Decimal.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import TypedDict

BILLING_RESERVE_MINUTES = 2

_FOUR_DP = Decimal("0.0001")
_TWO_DP = Decimal("0.01")
_SECONDS_PER_MINUTE = Decimal(60)
_ONE = Decimal(1)
_ZERO = Decimal(0)


class CallCharge(TypedDict):
    billed_minutes: Decimal
    started_minutes: Decimal
    setup_charge: Decimal
    duration_charge: Decimal
    credits_charged: Decimal
    budget_amount: Decimal


def _as_decimal(value: Decimal | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def reservation_credits(
    setup: Decimal | float | str,
    rate: Decimal | float | str,
) -> Decimal:
    """Credits to reserve at claim: (setup + rate) × BILLING_RESERVE_MINUTES.

    Quantized HALF_UP to 0.01 for campaigns.budget_used_credits (NUMERIC(12,2)).
    """
    raw = BILLING_RESERVE_MINUTES * (_as_decimal(setup) + _as_decimal(rate))
    return raw.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


def compute_call_charge(
    duration_seconds: Decimal | float | str,
    rate: Decimal | float | str,
    setup: Decimal | float | str,
) -> CallCharge:
    """Pro-rata per-second talk charge plus setup per started minute.

    started_minutes    = max(1, ceil(duration_seconds / 60))
    setup_charge       = started_minutes × setup          (telephony)
    duration_charge    = (duration_seconds / 60) × rate   (bot)
    billed_minutes     = duration_seconds / 60
    credits_charged    = (setup_charge + duration_charge) quantized to 0.0001
    budget_amount      = credits_charged quantized HALF_UP to 0.01
    """
    seconds = max(_as_decimal(duration_seconds), _ZERO)
    rate_d = _as_decimal(rate)
    setup_d = _as_decimal(setup)
    billed_minutes = (seconds / _SECONDS_PER_MINUTE).quantize(
        _FOUR_DP, rounding=ROUND_HALF_UP
    )
    started_minutes = max(
        _ONE,
        (seconds / _SECONDS_PER_MINUTE).to_integral_value(rounding=ROUND_CEILING),
    )
    setup_charge = (started_minutes * setup_d).quantize(
        _FOUR_DP, rounding=ROUND_HALF_UP
    )
    duration_charge = ((seconds / _SECONDS_PER_MINUTE) * rate_d).quantize(
        _FOUR_DP, rounding=ROUND_HALF_UP
    )
    credits_charged = (setup_charge + duration_charge).quantize(
        _FOUR_DP, rounding=ROUND_HALF_UP
    )
    budget_amount = credits_charged.quantize(_TWO_DP, rounding=ROUND_HALF_UP)
    return CallCharge(
        billed_minutes=billed_minutes,
        started_minutes=started_minutes,
        setup_charge=setup_charge,
        duration_charge=duration_charge,
        credits_charged=credits_charged,
        budget_amount=budget_amount,
    )

"""STS (Gemini Live) approximate cost in INR from token counts and env USD rates."""

from __future__ import annotations

import os


def compute_sts_cost_inr(
    route: str,
    *,
    usage_prompt_tokens: int,
    usage_completion_tokens: int,
) -> float | None:
    """
    Return estimated cost in INR for Route B (route is ``sts``), or ``None``.

    Requires ``GEMINI_LIVE_INPUT_USD_PER_1M`` and ``GEMINI_LIVE_OUTPUT_USD_PER_1M``
    (USD per 1M tokens, matching Google's pricing sheet for your SKU). Uses
    ``USD_INR`` for conversion (default ``85``). Non-STS routes return ``None``.
    """
    if route != "sts":
        return None
    rin_raw = os.getenv("GEMINI_LIVE_INPUT_USD_PER_1M", "").strip()
    rout_raw = os.getenv("GEMINI_LIVE_OUTPUT_USD_PER_1M", "").strip()
    if not rin_raw or not rout_raw:
        return None
    try:
        rin = float(rin_raw)
        rout = float(rout_raw)
    except ValueError:
        return None
    try:
        usd_inr = float(os.getenv("USD_INR", "85").strip() or "85")
    except ValueError:
        usd_inr = 85.0
    cost_usd = (usage_prompt_tokens / 1_000_000.0) * rin + (
        usage_completion_tokens / 1_000_000.0
    ) * rout
    return round(cost_usd * usd_inr, 4)

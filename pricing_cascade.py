"""Cascade (STT + LLM + TTS) approximate provider cost in USD from env rates."""

from __future__ import annotations

import os

from loguru import logger


def _env_float(name: str) -> float | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _slug(provider: str) -> str:
    return (provider or "").strip().upper()


def compute_cascade_cost_usd(
    *,
    duration_seconds: int,
    usage_prompt_tokens: int,
    usage_completion_tokens: int,
    usage_tts_characters: int,
    stt_provider: str,
    llm_provider: str,
    tts_provider: str,
) -> float | None:
    """
    Return estimated cascade COGS in USD, or ``None`` if no component rate is set.

    Env (provider slug uppercased, matching catalog keys):

    * ``STT_{PROVIDER}_USD_PER_MIN`` — pipeline wall-clock minutes
    * ``LLM_{PROVIDER}_INPUT_USD_PER_1M`` / ``LLM_{PROVIDER}_OUTPUT_USD_PER_1M``
    * ``TTS_{PROVIDER}_USD_PER_1K_CHARS``

    If **no** component env is set, returns ``None`` (unknown). If **any** is set,
    sums configured components and treats missing ones as ``0``.
    """
    skipped: list[str] = []
    total = 0.0
    any_rate = False

    stt_key = f"STT_{_slug(stt_provider)}_USD_PER_MIN"
    stt_rate = _env_float(stt_key) if _slug(stt_provider) else None
    if stt_rate is None:
        skipped.append("stt")
    else:
        any_rate = True
        total += (duration_seconds / 60.0) * stt_rate

    llm_slug = _slug(llm_provider)
    llm_in = _env_float(f"LLM_{llm_slug}_INPUT_USD_PER_1M") if llm_slug else None
    llm_out = _env_float(f"LLM_{llm_slug}_OUTPUT_USD_PER_1M") if llm_slug else None
    if llm_in is None:
        skipped.append("llm_input")
    else:
        any_rate = True
        total += (usage_prompt_tokens / 1_000_000.0) * llm_in
    if llm_out is None:
        skipped.append("llm_output")
    else:
        any_rate = True
        total += (usage_completion_tokens / 1_000_000.0) * llm_out

    tts_key = f"TTS_{_slug(tts_provider)}_USD_PER_1K_CHARS"
    tts_rate = _env_float(tts_key) if _slug(tts_provider) else None
    if tts_rate is None:
        skipped.append("tts")
    else:
        any_rate = True
        total += (usage_tts_characters / 1000.0) * tts_rate

    if not any_rate:
        return None
    if skipped:
        logger.debug(
            "cascade cost: skipped unconfigured components {}",
            skipped,
        )
    return round(total, 6)

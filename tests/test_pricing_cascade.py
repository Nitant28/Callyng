"""Unit tests for cascade COGS (pricing_cascade.compute_cascade_cost_usd)."""

from __future__ import annotations

import inspect

import pytest

from pricing_cascade import compute_cascade_cost_usd
from pricing_sts import compute_sts_cost_inr, usd_inr_rate

_RATE_KEYS = (
    "STT_SARVAM_USD_PER_MIN",
    "STT_SONIOX_USD_PER_MIN",
    "STT_ELEVENLABS_USD_PER_MIN",
    "STT_DEEPGRAM_USD_PER_MIN",
    "LLM_GROQ_INPUT_USD_PER_1M",
    "LLM_GROQ_OUTPUT_USD_PER_1M",
    "LLM_OPENAI_INPUT_USD_PER_1M",
    "LLM_OPENAI_OUTPUT_USD_PER_1M",
    "LLM_GOOGLE_INPUT_USD_PER_1M",
    "LLM_GOOGLE_OUTPUT_USD_PER_1M",
    "TTS_CARTESIA_USD_PER_1K_CHARS",
    "TTS_ELEVENLABS_USD_PER_1K_CHARS",
    "TTS_DEEPGRAM_USD_PER_1K_CHARS",
    "TTS_SARVAM_USD_PER_1K_CHARS",
    "TTS_SONIOX_USD_PER_1K_CHARS",
)


@pytest.fixture(autouse=True)
def _clear_cascade_rates(monkeypatch):
    for key in _RATE_KEYS:
        monkeypatch.delenv(key, raising=False)


def _cost(**overrides):
    kwargs = {
        "duration_seconds": 60,
        "usage_prompt_tokens": 0,
        "usage_completion_tokens": 0,
        "usage_tts_characters": 0,
        "stt_provider": "sarvam",
        "llm_provider": "groq",
        "tts_provider": "cartesia",
    }
    kwargs.update(overrides)
    return compute_cascade_cost_usd(**kwargs)


def test_sts_signature_unchanged():
    params = inspect.signature(compute_sts_cost_inr).parameters
    assert "usage_prompt_tokens" in params
    assert "usage_completion_tokens" in params
    assert "duration_seconds" not in params
    assert "stt_provider" not in params
    assert "usage_tts_characters" not in params


def test_all_four_rates_sum(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "1")
    monkeypatch.setenv("LLM_GROQ_INPUT_USD_PER_1M", "2")
    monkeypatch.setenv("LLM_GROQ_OUTPUT_USD_PER_1M", "3")
    monkeypatch.setenv("TTS_CARTESIA_USD_PER_1K_CHARS", "4")
    cost = _cost(
        duration_seconds=60,
        usage_prompt_tokens=1_000_000,
        usage_completion_tokens=1_000_000,
        usage_tts_characters=1000,
    )
    # 1 min * $1 + 1M in * $2 + 1M out * $3 + 1k chars * $4
    assert cost == 10.0


def test_only_stt_rate(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "1")
    assert _cost() == 1.0


def test_no_rates_returns_none():
    assert _cost() is None


def test_zero_usage_with_rates_is_zero(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "1")
    monkeypatch.setenv("LLM_GROQ_INPUT_USD_PER_1M", "2")
    monkeypatch.setenv("LLM_GROQ_OUTPUT_USD_PER_1M", "3")
    monkeypatch.setenv("TTS_CARTESIA_USD_PER_1K_CHARS", "4")
    assert (
        _cost(
            duration_seconds=0,
            usage_prompt_tokens=0,
            usage_completion_tokens=0,
            usage_tts_characters=0,
        )
        == 0.0
    )


def test_zero_usage_without_rates_is_none():
    assert (
        _cost(
            duration_seconds=0,
            usage_prompt_tokens=0,
            usage_completion_tokens=0,
            usage_tts_characters=0,
        )
        is None
    )


def test_invalid_env_float_treated_as_unset(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "not-a-number")
    assert _cost() is None


def test_unknown_provider_skips_that_component(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "1")
    assert _cost(stt_provider="unknown-vendor") is None
    monkeypatch.setenv("LLM_GROQ_INPUT_USD_PER_1M", "2")
    cost = _cost(
        stt_provider="unknown-vendor",
        usage_prompt_tokens=1_000_000,
    )
    assert cost == 2.0


def test_usd_inr_override_does_not_change_cascade_usd(monkeypatch):
    monkeypatch.setenv("STT_SARVAM_USD_PER_MIN", "1")
    monkeypatch.setenv("USD_INR", "999")
    assert usd_inr_rate() == 999.0
    assert _cost() == 1.0

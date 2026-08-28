"""Unit tests for call_metrics usage capture (LLM, TTS, STT, audio tokens)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import (
    LLMTokenUsage,
    LLMUsageMetricsData,
    STTUsage,
    STTUsageMetricsData,
    TTSUsageMetricsData,
)

from call_metrics import UsageMetricsAccumulator, UsageMetricsTap, _MAX_USAGE_SNAPSHOTS


def _llm_usage(**kwargs) -> LLMUsageMetricsData:
    defaults = {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    defaults.update(kwargs)
    return LLMUsageMetricsData(
        processor="llm",
        model="gemini-live",
        value=LLMTokenUsage(**defaults),
    )


def test_llm_usage_accumulates_text_tokens():
    acc = UsageMetricsAccumulator()
    acc.add_llm_usage(
        processor="llm",
        model="gpt",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cache_read_input_tokens=2,
        reasoning_tokens=3,
    )
    summary = acc.to_summary()
    assert summary["llm_prompt_tokens"] == 10
    assert summary["llm_completion_tokens"] == 5
    assert summary["llm_total_tokens"] == 15
    assert summary["llm_cache_read_input_tokens"] == 2
    assert summary["llm_reasoning_tokens"] == 3
    assert summary["llm_input_audio_tokens"] == 0
    assert summary["stt_audio_seconds"] == 0.0
    assert summary["snapshots"][0]["kind"] == "llm"


def test_llm_audio_tokens_accumulate():
    acc = UsageMetricsAccumulator()
    acc.add_llm_usage(
        processor="llm",
        model="gemini-live",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cache_read_input_tokens=None,
        reasoning_tokens=None,
        input_audio_tokens=8,
        output_audio_tokens=6,
        cache_read_input_audio_tokens=3,
    )
    acc.add_llm_usage(
        processor="llm",
        model="gemini-live",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cache_read_input_tokens=None,
        reasoning_tokens=None,
        input_audio_tokens=2,
        output_audio_tokens=1,
        cache_read_input_audio_tokens=1,
    )
    summary = acc.to_summary()
    assert summary["llm_input_audio_tokens"] == 10
    assert summary["llm_output_audio_tokens"] == 7
    assert summary["llm_cache_read_input_audio_tokens"] == 4


def test_stt_audio_seconds_sum_across_frames():
    acc = UsageMetricsAccumulator()
    acc.add_stt_usage(processor="stt", model="saaras:v3", audio_seconds=1.25)
    acc.add_stt_usage(processor="stt", model="saaras:v3", audio_seconds=0.75)
    summary = acc.to_summary()
    assert summary["stt_audio_seconds"] == pytest.approx(2.0)
    assert summary["snapshots"][0]["kind"] == "stt"
    assert summary["snapshots"][1]["kind"] == "stt"


def test_tts_characters_still_accumulate():
    acc = UsageMetricsAccumulator()
    acc.add_tts_usage(processor="tts", model="sonic", characters=40)
    acc.add_tts_usage(processor="tts", model="sonic", characters=10)
    assert acc.to_summary()["tts_characters"] == 50
    assert acc.to_summary()["snapshots"][0]["kind"] == "tts"


def test_snapshots_cap_at_max():
    acc = UsageMetricsAccumulator()
    for i in range(_MAX_USAGE_SNAPSHOTS + 5):
        acc.add_tts_usage(processor="tts", model="x", characters=1)
    assert acc.to_summary()["tts_characters"] == _MAX_USAGE_SNAPSHOTS + 5
    assert len(acc.to_summary()["snapshots"]) == _MAX_USAGE_SNAPSHOTS


def test_tap_records_mixed_metrics():
    acc = UsageMetricsAccumulator()
    tap = UsageMetricsTap(acc)
    frame = MetricsFrame(
        data=[
            _llm_usage(
                prompt_tokens=10,
                completion_tokens=4,
                total_tokens=14,
                input_audio_tokens=5,
                output_audio_tokens=7,
                cache_read_input_audio_tokens=1,
            ),
            STTUsageMetricsData(
                processor="stt",
                model="scribe",
                value=STTUsage(audio_seconds=2.5),
            ),
            TTSUsageMetricsData(processor="tts", model="sonic", value=40),
        ]
    )
    tap.capture_metrics_frame(frame)
    summary = acc.to_summary()
    assert summary["llm_prompt_tokens"] == 10
    assert summary["llm_input_audio_tokens"] == 5
    assert summary["llm_output_audio_tokens"] == 7
    assert summary["llm_cache_read_input_audio_tokens"] == 1
    assert summary["stt_audio_seconds"] == pytest.approx(2.5)
    assert summary["tts_characters"] == 40


def test_tap_missing_audio_attrs_do_not_crash():
    acc = UsageMetricsAccumulator()
    tap = UsageMetricsTap(acc)
    fake = LLMUsageMetricsData.model_construct(
        processor="llm",
        model="old",
        value=SimpleNamespace(
            prompt_tokens=2,
            completion_tokens=1,
            total_tokens=3,
            cache_read_input_tokens=None,
            reasoning_tokens=None,
        ),
    )
    tap.capture_metrics_frame(MetricsFrame(data=[fake]))
    summary = acc.to_summary()
    assert summary["llm_prompt_tokens"] == 2
    assert summary["llm_input_audio_tokens"] == 0

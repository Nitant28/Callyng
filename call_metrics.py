"""In-pipeline capture of Pipecat ``MetricsFrame`` usage (LLM tokens, TTS chars, STT audio)."""

from __future__ import annotations

from typing import Any

from pipecat.frames.frames import Frame, MetricsFrame
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    STTUsageMetricsData,
    TTSUsageMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_MAX_USAGE_SNAPSHOTS = 100


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


class UsageMetricsAccumulator:
    """Running totals and capped per-frame usage snapshots for one call."""

    def __init__(self) -> None:
        self.llm_prompt_tokens = 0
        self.llm_completion_tokens = 0
        self.llm_total_tokens = 0
        self.llm_cache_read_input_tokens = 0
        self.llm_reasoning_tokens = 0
        self.llm_input_audio_tokens = 0
        self.llm_output_audio_tokens = 0
        self.llm_cache_read_input_audio_tokens = 0
        self.tts_characters = 0
        self.stt_audio_seconds = 0.0
        self._snapshots: list[dict[str, Any]] = []

    def add_llm_usage(
        self,
        *,
        processor: str,
        model: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cache_read_input_tokens: int | None,
        reasoning_tokens: int | None,
        input_audio_tokens: int | None = None,
        output_audio_tokens: int | None = None,
        cache_read_input_audio_tokens: int | None = None,
    ) -> None:
        self.llm_prompt_tokens += prompt_tokens
        self.llm_completion_tokens += completion_tokens
        self.llm_total_tokens += total_tokens
        if cache_read_input_tokens:
            self.llm_cache_read_input_tokens += cache_read_input_tokens
        if reasoning_tokens:
            self.llm_reasoning_tokens += reasoning_tokens
        if input_audio_tokens:
            self.llm_input_audio_tokens += input_audio_tokens
        if output_audio_tokens:
            self.llm_output_audio_tokens += output_audio_tokens
        if cache_read_input_audio_tokens:
            self.llm_cache_read_input_audio_tokens += cache_read_input_audio_tokens
        if len(self._snapshots) < _MAX_USAGE_SNAPSHOTS:
            self._snapshots.append(
                {
                    "kind": "llm",
                    "processor": processor,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cache_read_input_tokens": cache_read_input_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "input_audio_tokens": input_audio_tokens,
                    "output_audio_tokens": output_audio_tokens,
                    "cache_read_input_audio_tokens": cache_read_input_audio_tokens,
                }
            )

    def add_tts_usage(self, *, processor: str, model: str | None, characters: int) -> None:
        self.tts_characters += characters
        if len(self._snapshots) < _MAX_USAGE_SNAPSHOTS:
            self._snapshots.append(
                {
                    "kind": "tts",
                    "processor": processor,
                    "model": model,
                    "characters": characters,
                }
            )

    def add_stt_usage(
        self, *, processor: str, model: str | None, audio_seconds: float
    ) -> None:
        self.stt_audio_seconds += float(audio_seconds)
        if len(self._snapshots) < _MAX_USAGE_SNAPSHOTS:
            self._snapshots.append(
                {
                    "kind": "stt",
                    "processor": processor,
                    "model": model,
                    "audio_seconds": audio_seconds,
                }
            )

    def to_summary(self) -> dict[str, Any]:
        return {
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "llm_cache_read_input_tokens": self.llm_cache_read_input_tokens,
            "llm_reasoning_tokens": self.llm_reasoning_tokens,
            "llm_input_audio_tokens": self.llm_input_audio_tokens,
            "llm_output_audio_tokens": self.llm_output_audio_tokens,
            "llm_cache_read_input_audio_tokens": self.llm_cache_read_input_audio_tokens,
            "tts_characters": self.tts_characters,
            "stt_audio_seconds": self.stt_audio_seconds,
            "snapshots": list(self._snapshots),
        }


class UsageMetricsTap(FrameProcessor):
    """Pass-through processor that records LLM / TTS / STT usage metrics."""

    def __init__(self, accumulator: UsageMetricsAccumulator):
        super().__init__()
        self._acc = accumulator

    def capture_metrics_frame(self, frame: MetricsFrame) -> None:
        """Record usage items from a metrics frame (no pipeline lifecycle)."""
        for item in frame.data:
            if isinstance(item, LLMUsageMetricsData):
                v = item.value
                self._acc.add_llm_usage(
                    processor=item.processor,
                    model=item.model,
                    prompt_tokens=v.prompt_tokens,
                    completion_tokens=v.completion_tokens,
                    total_tokens=v.total_tokens,
                    cache_read_input_tokens=v.cache_read_input_tokens,
                    reasoning_tokens=v.reasoning_tokens,
                    input_audio_tokens=_opt_int(
                        getattr(v, "input_audio_tokens", None)
                    ),
                    output_audio_tokens=_opt_int(
                        getattr(v, "output_audio_tokens", None)
                    ),
                    cache_read_input_audio_tokens=_opt_int(
                        getattr(v, "cache_read_input_audio_tokens", None)
                    ),
                )
            elif isinstance(item, TTSUsageMetricsData):
                self._acc.add_tts_usage(
                    processor=item.processor,
                    model=item.model,
                    characters=item.value,
                )
            elif isinstance(item, STTUsageMetricsData):
                usage = item.value
                seconds = getattr(usage, "audio_seconds", usage)
                self._acc.add_stt_usage(
                    processor=item.processor,
                    model=item.model,
                    audio_seconds=float(seconds),
                )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
            self.capture_metrics_frame(frame)

        await self.push_frame(frame, direction)

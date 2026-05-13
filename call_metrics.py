"""In-pipeline capture of Pipecat ``MetricsFrame`` usage (LLM tokens, TTS chars)."""

from __future__ import annotations

from typing import Any

from pipecat.frames.frames import Frame, MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_MAX_USAGE_SNAPSHOTS = 100


class UsageMetricsAccumulator:
    """Running totals and capped per-frame usage snapshots for one call."""

    def __init__(self) -> None:
        self.llm_prompt_tokens = 0
        self.llm_completion_tokens = 0
        self.llm_total_tokens = 0
        self.llm_cache_read_input_tokens = 0
        self.llm_reasoning_tokens = 0
        self.tts_characters = 0
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
    ) -> None:
        self.llm_prompt_tokens += prompt_tokens
        self.llm_completion_tokens += completion_tokens
        self.llm_total_tokens += total_tokens
        if cache_read_input_tokens:
            self.llm_cache_read_input_tokens += cache_read_input_tokens
        if reasoning_tokens:
            self.llm_reasoning_tokens += reasoning_tokens
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

    def to_summary(self) -> dict[str, Any]:
        return {
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "llm_cache_read_input_tokens": self.llm_cache_read_input_tokens,
            "llm_reasoning_tokens": self.llm_reasoning_tokens,
            "tts_characters": self.tts_characters,
            "snapshots": list(self._snapshots),
        }


class UsageMetricsTap(FrameProcessor):
    """Pass-through processor that records ``LLMUsageMetricsData`` / ``TTSUsageMetricsData``."""

    def __init__(self, accumulator: UsageMetricsAccumulator):
        super().__init__()
        self._acc = accumulator

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
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
                    )
                elif isinstance(item, TTSUsageMetricsData):
                    self._acc.add_tts_usage(
                        processor=item.processor,
                        model=item.model,
                        characters=item.value,
                    )

        await self.push_frame(frame, direction)

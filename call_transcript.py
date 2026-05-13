"""Per-call transcript capture via Pipecat universal aggregator turn events."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext, LLMSpecificMessage

from call_log_db import insert_call_log, update_call_log_extraction
from call_metrics import UsageMetricsAccumulator
from post_call_extract import extract_post_call, normalize_post_call_extraction

# STS bootstrap user message prefix (see bot_sts.py) — omit from stored transcripts.
_STS_BOOTSTRAP_PREFIX = "The call has just connected."


class TranscriptBuffer:
    """Collects user/assistant turns from aggregator ``on_*_turn_stopped`` events."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def register(self, user_aggregator: Any, assistant_aggregator: Any) -> None:
        @user_aggregator.event_handler("on_user_turn_stopped")
        async def on_user_turn_stopped(aggregator, strategy, message):
            self.turns.append(
                {
                    "role": "user",
                    "content": message.content,
                    "timestamp": message.timestamp,
                }
            )

        @assistant_aggregator.event_handler("on_assistant_turn_stopped")
        async def on_assistant_turn_stopped(aggregator, message):
            self.turns.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "timestamp": message.timestamp,
                    "interrupted": message.interrupted,
                }
            )


def _strip_sts_bootstrap(turns: list[dict[str, Any]]) -> None:
    if not turns:
        return
    first = turns[0]
    if first.get("role") != "user":
        return
    content = (first.get("content") or "").strip()
    if content.startswith(_STS_BOOTSTRAP_PREFIX):
        turns.pop(0)


def _message_to_turn(msg: Any) -> dict[str, Any] | None:
    if isinstance(msg, LLMSpecificMessage):
        return None
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role not in ("user", "assistant", "system"):
        return None
    raw = msg.get("content")
    if isinstance(raw, str):
        text = raw
    elif isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        text = " ".join(parts)
    else:
        text = str(raw) if raw is not None else ""
    return {"role": role, "content": text, "timestamp": ""}


def snapshot_from_context(context: LLMContext) -> list[dict[str, Any]]:
    """Fallback when turn events are empty (e.g. edge cases on Gemini Live)."""
    out: list[dict[str, Any]] = []
    for msg in context.get_messages():
        turn = _message_to_turn(msg)
        if turn:
            out.append(turn)
    return out


def finalize_transcript(
    buffer: TranscriptBuffer,
    context: LLMContext | None,
    *,
    strip_bootstrap: bool,
) -> list[dict[str, Any]]:
    turns = [dict(t) for t in buffer.turns]
    if strip_bootstrap:
        _strip_sts_bootstrap(turns)
    if not turns and context is not None:
        turns = snapshot_from_context(context)
        if strip_bootstrap:
            _strip_sts_bootstrap(turns)
    return turns


def attach_pipeline_finalize(
    task: PipelineTask,
    buffer: TranscriptBuffer,
    context: LLMContext | None,
    *,
    route: str,
    session_call_id: str | None,
    plivo_call_id: str | None,
    started_at_iso: str,
    perf_start: float,
    strip_bootstrap: bool = False,
    usage_accumulator: UsageMetricsAccumulator | None = None,
) -> None:
    @task.event_handler("on_pipeline_finished")
    async def _on_pipeline_finished(task, frame):
        ended_at = datetime.now(timezone.utc).isoformat()
        duration_ms = (time.perf_counter() - perf_start) * 1000
        transcript = finalize_transcript(
            buffer, context, strip_bootstrap=strip_bootstrap
        )
        usage_summary: dict[str, Any] | None = None
        if usage_accumulator is not None:
            usage_summary = usage_accumulator.to_summary()
        summary = {
            "session_call_id": session_call_id,
            "plivo_call_id": plivo_call_id,
            "route": route,
            "started_at": started_at_iso,
            "ended_at": ended_at,
            "duration_ms": round(duration_ms, 2),
            "turn_count": len(transcript),
        }
        if usage_summary is not None:
            summary["usage"] = {
                "llm_prompt_tokens": usage_summary.get("llm_prompt_tokens"),
                "llm_completion_tokens": usage_summary.get("llm_completion_tokens"),
                "llm_total_tokens": usage_summary.get("llm_total_tokens"),
                "tts_characters": usage_summary.get("tts_characters"),
            }
        logger.info(
            "call_transcript_summary {}",
            json.dumps(summary, ensure_ascii=False),
        )
        # Avoid flooding logs on long calls; full JSON remains in SQLite.
        preview = json.dumps(transcript, ensure_ascii=False)
        if len(preview) > 4000:
            logger.info(
                "call_transcript_payload {}",
                preview[:4000] + f"... [{len(preview)} chars total]",
            )
        else:
            logger.info("call_transcript_payload {}", preview)

        usage_metrics_blob: str | None = None
        up, uc, ut, tts_c = 0, 0, 0, 0
        if usage_summary is not None:
            usage_metrics_blob = json.dumps(usage_summary, ensure_ascii=False)
            up = int(usage_summary.get("llm_prompt_tokens") or 0)
            uc = int(usage_summary.get("llm_completion_tokens") or 0)
            ut = int(usage_summary.get("llm_total_tokens") or 0)
            tts_c = int(usage_summary.get("tts_characters") or 0)

        try:
            row_id = insert_call_log(
                session_call_id=session_call_id,
                plivo_call_id=plivo_call_id,
                route=route,
                started_at=started_at_iso,
                ended_at=ended_at,
                duration_ms=duration_ms,
                transcript=transcript,
                usage_prompt_tokens=up,
                usage_completion_tokens=uc,
                usage_total_tokens=ut,
                usage_tts_characters=tts_c,
                usage_metrics_json=usage_metrics_blob,
            )
        except Exception as exc:
            logger.error("call_log_db insert failed: {}", exc)
            return

        if os.getenv("GROQ_API_KEY"):
            async def _extract_and_patch() -> None:
                try:
                    parsed, err, model_used = await extract_post_call(transcript)
                    if parsed is not None and err is None:
                        parsed = normalize_post_call_extraction(parsed)
                        update_call_log_extraction(
                            row_id,
                            extraction_json=json.dumps(parsed, ensure_ascii=False),
                            extraction_error=None,
                            extraction_model=model_used,
                        )
                    else:
                        update_call_log_extraction(
                            row_id,
                            extraction_json=None,
                            extraction_error=err or "extraction_failed",
                            extraction_model=model_used,
                        )
                except Exception as exc:
                    logger.exception("post_call extraction failed: {}", exc)
                    try:
                        update_call_log_extraction(
                            row_id,
                            extraction_json=None,
                            extraction_error=f"{type(exc).__name__}: {exc}",
                            extraction_model=os.getenv(
                                "POST_CALL_MODEL", "llama-3.3-70b-versatile"
                            ),
                        )
                    except Exception:
                        logger.exception("call_log extraction update failed")

            asyncio.create_task(_extract_and_patch())
        else:
            logger.debug("post_call_extract skipped: GROQ_API_KEY not set")

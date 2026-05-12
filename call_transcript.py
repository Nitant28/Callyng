"""Per-call transcript capture via Pipecat universal aggregator turn events."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext, LLMSpecificMessage

from call_log_db import insert_call_log

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
) -> None:
    @task.event_handler("on_pipeline_finished")
    async def _on_pipeline_finished(task, frame):
        ended_at = datetime.now(timezone.utc).isoformat()
        duration_ms = (time.perf_counter() - perf_start) * 1000
        transcript = finalize_transcript(
            buffer, context, strip_bootstrap=strip_bootstrap
        )
        summary = {
            "session_call_id": session_call_id,
            "plivo_call_id": plivo_call_id,
            "route": route,
            "started_at": started_at_iso,
            "ended_at": ended_at,
            "duration_ms": round(duration_ms, 2),
            "turn_count": len(transcript),
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

        try:
            insert_call_log(
                session_call_id=session_call_id,
                plivo_call_id=plivo_call_id,
                route=route,
                started_at=started_at_iso,
                ended_at=ended_at,
                duration_ms=duration_ms,
                transcript=transcript,
            )
        except Exception as exc:
            logger.error("call_log_db insert failed: {}", exc)

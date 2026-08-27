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

from background_tasks import spawn_background_task
from call_log_db import get_row_id_by_session, insert_call_log, update_call_log_extraction
from call_metrics import UsageMetricsAccumulator
from n8n_webhook import send_call_completed_webhook
from post_call_extract import (
    extract_post_call,
    normalize_post_call_extraction,
    post_call_llm_configured,
    post_call_missing_key_message,
    prepare_transcript_for_storage,
)
from pricing_sts import compute_sts_cost_inr

from db.redis_client import get_redis
from db import postgres as pg_db

_PGCTX_KEY_PREFIX = "pgctx:"
_PG_WRITE_TIMEOUT_S = 5.0
_PG_WRITE_LIVE_TIMEOUT_S = 2.0
_TRANSCRIPT_DEBOUNCE_S = 2.0
_CAMPAIGN_PG_FIELDS = ("client_id", "campaign_id", "lead_id", "bot_config_id")
_EVENT_PG_FIELDS = ("client_id", "event_id", "lead_id", "bot_config_id")


def _pgctx_key(session_call_id: str) -> str:
    return f"{_PGCTX_KEY_PREFIX}{session_call_id}"


def _pgctx_ttl_seconds() -> int:
    return pg_db.live_call_grace_minutes() * 60


async def register_pg_context(session_call_id: str, pg: dict[str, Any]) -> None:
    if not session_call_id or not pg:
        return
    redis = get_redis()
    await redis.set(
        _pgctx_key(session_call_id),
        json.dumps(pg, ensure_ascii=False),
        ex=_pgctx_ttl_seconds(),
    )


async def pop_pg_context(session_call_id: str | None) -> dict[str, Any] | None:
    if not session_call_id:
        return None
    redis = get_redis()
    raw = await redis.getdel(_pgctx_key(session_call_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid pgctx JSON for session {}", session_call_id)
        return None
    return data if isinstance(data, dict) else None


def _pg_context_has_campaign_fields(ctx: dict[str, Any] | None) -> bool:
    if not ctx:
        return False

    has_campaign = all(ctx.get(k) for k in _CAMPAIGN_PG_FIELDS)
    has_event = all(ctx.get(k) for k in _EVENT_PG_FIELDS)

    return has_campaign or has_event

def _pg_context_from_call_log(row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("client_id"):
        return None

    is_test_call = False
    call_data = row.get("call_data")

    if call_data and isinstance(call_data, dict):
        is_test_call = bool(call_data.get("is_test_call"))
    elif call_data and isinstance(call_data, str):
        try:
            parsed = json.loads(call_data)
            if isinstance(parsed, dict):
                is_test_call = bool(parsed.get("is_test_call"))
        except json.JSONDecodeError:
            pass

    # Event call
    if row.get("event_id"):
        if not is_test_call:
            if not all(row.get(k) for k in _EVENT_PG_FIELDS):
                return None

        ctx: dict[str, Any] = {
            "client_id": str(row["client_id"]),
            "event_id": str(row["event_id"]),
            "lead_id": str(row["lead_id"]) if row.get("lead_id") else "",
            "bot_config_id": (
                str(row["bot_config_id"])
                if row.get("bot_config_id")
                else ""
            ),
        }

        if row.get("route"):
            ctx["route"] = row["route"]

        return ctx

    # Campaign call
    if not is_test_call:
        if not all(row.get(k) for k in _CAMPAIGN_PG_FIELDS):
            return None

    ctx = {
        "client_id": str(row["client_id"]),
        "campaign_id": (
            str(row["campaign_id"])
            if row.get("campaign_id")
            else ""
        ),
        "lead_id": str(row["lead_id"]) if row.get("lead_id") else "",
        "bot_config_id": (
            str(row["bot_config_id"])
            if row.get("bot_config_id")
            else ""
        ),
    }

    if row.get("route"):
        ctx["route"] = row["route"]

    return ctx


async def resolve_pg_context(
    pool: Any,
    session_call_id: str | None,
    redis_ctx: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if redis_ctx and redis_ctx.get("client_id"):
        # Event context
        if all(redis_ctx.get(k) for k in _EVENT_PG_FIELDS):
            return redis_ctx

        # Campaign context
        if _pg_context_has_campaign_fields(redis_ctx):
            return redis_ctx

        if not redis_ctx.get("campaign_id") and not redis_ctx.get("event_id"):
            return redis_ctx

    if not pool or not session_call_id:
        return None

    row = await pg_db.get_call_log_by_session(pool, session_call_id)

    if not row:
        return None

    return _pg_context_from_call_log(row)

async def _run_campaign_post_call(
    *,
    resolved_ctx: dict[str, Any] | None,
    session_call_id: str | None,
    duration_seconds: int,
    transcript: list[dict],
    extraction: dict | None,
    usage_dict: dict,
    extraction_model: str | None = None,
    extraction_error: str | None = None,
    post_call_snapshot: dict | None = None,
) -> None:
    if not session_call_id:
        return

    if resolved_ctx is None:
        logger.warning(
            "post_call skipped: no context for session={}",
            session_call_id,
        )
        return

    try:
        from uuid import UUID

        pool = _pg_pool()
        if pool is None:
            return

        client_id = resolved_ctx.get("client_id")
        lead_id = resolved_ctx.get("lead_id")
        bot_config_id = resolved_ctx.get("bot_config_id")
        campaign_id = resolved_ctx.get("campaign_id")
        event_id = resolved_ctx.get("event_id")

        # ---------------------------------------------------------
        # EVENT POST-CALL
        # ---------------------------------------------------------
        if event_id:
            from post_call_processor import process_event_post_call

            await process_event_post_call(
                pool,
                session_call_id,
                UUID(lead_id),
                UUID(event_id),
                UUID(client_id),
                UUID(bot_config_id),
                duration_seconds,
                transcript,
                extraction or {},
                usage=usage_dict,
                extraction_model=extraction_model,
                extraction_error=extraction_error,
            )

            return

        # ---------------------------------------------------------
        # CAMPAIGN POST-CALL
        # ---------------------------------------------------------
        if campaign_id:
            from post_call_processor import process_post_call

            await process_post_call(
                pool,
                session_call_id,
                UUID(lead_id),
                UUID(campaign_id),
                UUID(client_id),
                UUID(bot_config_id),
                duration_seconds,
                transcript,
                extraction or {},
                usage=usage_dict,
                extraction_model=extraction_model,
                extraction_error=extraction_error,
                post_call_snapshot=post_call_snapshot,
            )

            return

        # ---------------------------------------------------------
        # NO CAMPAIGN / EVENT
        # ---------------------------------------------------------
        logger.warning(
            "post_call skipped: context has neither campaign_id nor event_id "
            "for session={} ctx={}",
            session_call_id,
            resolved_ctx,
        )

    except Exception as exc:
        logger.exception(
            "post_call_processor failed: {}",
            exc,
        )

def _pg_pool():
    try:
        return pg_db.get_pool()
    except Exception as exc:
        logger.error("Failed to get pg_pool in transcript writer: {}", exc)
        return None


async def _pg_write(coro, *, timeout_s: float = _PG_WRITE_TIMEOUT_S):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except Exception as exc:
        logger.warning("postgres call_log write skipped: {}", exc)
        return None


async def _pg_write_live(coro):
    return await _pg_write(coro, timeout_s=_PG_WRITE_LIVE_TIMEOUT_S)


async def _pg_write_finalize(coro):
    return await _pg_write(coro, timeout_s=_PG_WRITE_TIMEOUT_S)


def _schedule_call_completed_webhook(payload: dict[str, Any]) -> None:
    """Fire-and-forget n8n webhook; failures must not abort pipeline finalize."""

    async def _send() -> None:
        try:
            await send_call_completed_webhook(payload)
        except Exception as exc:
            logger.exception("n8n webhook failed: {}", exc)

    spawn_background_task(_send(), "call_completed_webhook")


def _resolve_sqlite_row_id(row_id: int, session_call_id: str | None) -> int:
    """Recover a valid SQLite row id when insert failed (row_id <= 0)."""
    if row_id > 0:
        return row_id
    if not session_call_id:
        return row_id
    recovered = get_row_id_by_session(session_call_id)
    if recovered is not None and recovered > 0:
        logger.info(
            "Recovered SQLite row_id={} for session={}",
            recovered,
            session_call_id,
        )
        return recovered
    logger.warning(
        "No SQLite row_id for session={}; extraction update will be skipped",
        session_call_id,
    )
    return row_id

# STS bootstrap user message prefix (see bot_sts.py) — omit from stored transcripts.
_STS_BOOTSTRAP_PREFIX = "The call has just connected."

# Cap JSON size of transcript in n8n payload (full transcript remains in SQLite).
_MAX_WEBHOOK_TRANSCRIPT_JSON_CHARS = 120_000


class TranscriptBuffer:
    """Collects user/assistant turns from aggregator ``on_*_turn_stopped`` events."""

    def __init__(self, *, session_call_id: str | None = None) -> None:
        self.turns: list[dict[str, Any]] = []
        self._session_call_id = session_call_id
        self._pg_flush_task: asyncio.Task[Any] | None = None
        self._pg_flush_pending = False

    def _schedule_pg_flush(self) -> None:
        """Debounce a full-transcript replace write for live UI polling."""
        if not self._session_call_id:
            return
        self._pg_flush_pending = True
        if self._pg_flush_task is not None and not self._pg_flush_task.done():
            return

        async def _debounced() -> None:
            try:
                while self._pg_flush_pending:
                    self._pg_flush_pending = False
                    await asyncio.sleep(_TRANSCRIPT_DEBOUNCE_S)
                    if self._pg_flush_pending:
                        continue
                    pool = _pg_pool()
                    if pool is None or not self._session_call_id:
                        return
                    snapshot = list(self.turns)
                    await _pg_write_live(
                        pg_db.replace_transcript(pool, self._session_call_id, snapshot)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("transcript pg flush failed: {}", exc)

        self._pg_flush_task = spawn_background_task(
            _debounced(), "transcript_pg_flush"
        )

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
            self._schedule_pg_flush()

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
            self._schedule_pg_flush()


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
    return prepare_transcript_for_storage(turns)


def _transcript_for_webhook(
    transcript: list[dict[str, Any]],
    max_json_chars: int = _MAX_WEBHOOK_TRANSCRIPT_JSON_CHARS,
) -> tuple[list[dict[str, Any]], bool]:
    """Return a prefix of ``transcript`` whose JSON fits within ``max_json_chars``."""
    if not transcript:
        return [], False
    lo, hi = 0, len(transcript)
    best: list[dict[str, Any]] = []
    while lo <= hi:
        mid = (lo + hi) // 2
        chunk = transcript[:mid]
        size = len(json.dumps(chunk, ensure_ascii=False))
        if size <= max_json_chars:
            best = chunk
            lo = mid + 1
        else:
            hi = mid - 1
    truncated = len(best) < len(transcript)
    return best, truncated


def _build_n8n_payload(
    *,
    row_id: int,
    session_call_id: str | None,
    plivo_call_id: str | None,
    route: str,
    started_at: str,
    ended_at: str,
    duration_ms: float,
    transcript: list[dict[str, Any]],
    usage_prompt_tokens: int,
    usage_completion_tokens: int,
    usage_total_tokens: int,
    usage_tts_characters: int,
    cost_inr: float | None,
    extraction: dict[str, Any] | None,
    extraction_error: str | None,
    extraction_model: str | None,
    post_call_extraction_skipped: bool,
) -> dict[str, Any]:
    tw, trunc = _transcript_for_webhook(transcript)
    return {
        "event": "call_completed",
        "call_log_id": row_id,
        "session_call_id": session_call_id,
        "plivo_call_id": plivo_call_id,
        "route": route,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": round(duration_ms, 2),
        "usage": {
            "llm_prompt_tokens": usage_prompt_tokens,
            "llm_completion_tokens": usage_completion_tokens,
            "llm_total_tokens": usage_total_tokens,
            "tts_characters": usage_tts_characters,
        },
        "cost_inr": cost_inr,
        "transcript": tw,
        "transcript_truncated": trunc,
        "extraction": extraction,
        "extraction_error": extraction_error,
        "extraction_model": extraction_model,
        "post_call_extraction_skipped": post_call_extraction_skipped,
    }


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
    extraction_schema: dict[str, Any],
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
        # Avoid flooding logs / full dumps on long calls; full JSON remains in SQLite.
        turn_count = len(transcript)
        if turn_count == 0:
            logger.info("call_transcript_payload turns=0")
        else:
            preview_turns = transcript[:3]
            preview = json.dumps(preview_turns, ensure_ascii=False)
            if len(preview) > 1500:
                preview = preview[:1500] + "..."
            logger.info(
                "call_transcript_payload turns={} preview={}",
                turn_count,
                preview,
            )

        usage_metrics_blob: str | None = None
        up, uc, ut, tts_c = 0, 0, 0, 0
        if usage_summary is not None:
            usage_metrics_blob = json.dumps(usage_summary, ensure_ascii=False)
            up = int(usage_summary.get("llm_prompt_tokens") or 0)
            uc = int(usage_summary.get("llm_completion_tokens") or 0)
            ut = int(usage_summary.get("llm_total_tokens") or 0)
            tts_c = int(usage_summary.get("tts_characters") or 0)

        cost_inr = compute_sts_cost_inr(
            route,
            usage_prompt_tokens=up,
            usage_completion_tokens=uc,
        )

        try:
            row_id = await asyncio.to_thread(
                insert_call_log,
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
                cost_inr=cost_inr,
            )
        except Exception as exc:
            logger.error("call_log_db insert failed: {}", exc)
            row_id = -1

        row_id = _resolve_sqlite_row_id(row_id, session_call_id)
        pg_ctx = await pop_pg_context(session_call_id)
        pool = _pg_pool()
        resolved_ctx = await resolve_pg_context(pool, session_call_id, pg_ctx)
        if session_call_id and pool is not None:
            try:
                cleared = await _pg_write_finalize(
                    pg_db.mark_call_log_not_in_progress(pool, session_call_id)
                )
                if cleared:
                    logger.debug(
                        "call_log in_progress cleared at hangup session={}",
                        session_call_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to clear in_progress for {}: {}",
                    session_call_id,
                    exc,
                )
        duration_seconds = int(round(duration_ms / 1000))
        usage_dict = {
            "llm_prompt_tokens": up,
            "llm_completion_tokens": uc,
            "llm_total_tokens": ut,
            "tts_characters": tts_c,
        }

        if post_call_llm_configured():

            async def _extract_patch_and_webhook() -> None:
                extraction: dict[str, Any] | None = None
                extraction_error: str | None = None
                extraction_model: str | None = None
                snapshot: dict[str, Any] | None = None
                schema = extraction_schema
                norm_rules: list[Any] | None = None

                pool = _pg_pool()
                if pool is not None and session_call_id:
                    try:
                        from script_runtime import parse_post_call_snapshot

                        call_log = await pg_db.get_call_log_by_session(
                            pool, session_call_id
                        )
                        snapshot = parse_post_call_snapshot(
                            call_log.get("call_data") if call_log else None
                        )
                        if snapshot:
                            schema = snapshot.get("extraction_schema") or schema
                            rules = snapshot.get("normalization_rules")
                            norm_rules = rules if rules else None
                    except Exception as exc:
                        logger.warning(
                            "post_call snapshot load failed, using closure fallback: {}",
                            exc,
                        )

                try:
                    parsed, err, model_used = await extract_post_call(
                        transcript, extraction_schema=schema
                    )
                    extraction_model = model_used
                    if parsed is not None and err is None:
                        extraction = normalize_post_call_extraction(
                            parsed,
                            normalization_rules=norm_rules,
                        )
                        update_call_log_extraction(
                            row_id,
                            extraction_json=json.dumps(extraction, ensure_ascii=False),
                            extraction_error=None,
                            extraction_model=model_used,
                        )
                    else:
                        extraction_error = err or "extraction_failed"
                        update_call_log_extraction(
                            row_id,
                            extraction_json=None,
                            extraction_error=extraction_error,
                            extraction_model=model_used,
                        )
                except Exception as exc:
                    logger.exception("post_call extraction failed: {}", exc)
                    extraction_error = f"{type(exc).__name__}: {exc}"
                    try:
                        update_call_log_extraction(
                            row_id,
                            extraction_json=None,
                            extraction_error=extraction_error,
                            extraction_model=os.getenv(
                                "POST_CALL_MODEL", "llama-3.3-70b-versatile"
                            ),
                        )
                    except Exception:
                        logger.exception("call_log extraction update failed")

                await _run_campaign_post_call(
                    resolved_ctx=resolved_ctx,
                    session_call_id=session_call_id,
                    duration_seconds=duration_seconds,
                    transcript=transcript,
                    extraction=extraction,
                    usage_dict=usage_dict,
                    extraction_model=extraction_model,
                    extraction_error=extraction_error,
                    post_call_snapshot=snapshot,
                )

                if not _pg_context_has_campaign_fields(resolved_ctx):
                    payload = _build_n8n_payload(
                        row_id=row_id,
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
                        cost_inr=cost_inr,
                        extraction=extraction,
                        extraction_error=extraction_error,
                        extraction_model=extraction_model,
                        post_call_extraction_skipped=False,
                    )
                    await send_call_completed_webhook(payload)

            spawn_background_task(_extract_patch_and_webhook())
        else:
            logger.debug("post_call_extract skipped: {}", post_call_missing_key_message())
            if session_call_id and _pg_context_has_campaign_fields(resolved_ctx):
                spawn_background_task(
                    _run_campaign_post_call(
                        resolved_ctx=resolved_ctx,
                        session_call_id=session_call_id,
                        duration_seconds=duration_seconds,
                        transcript=transcript,
                        extraction=None,
                        usage_dict=usage_dict,
                    )
                )
            if not _pg_context_has_campaign_fields(resolved_ctx):
                payload = _build_n8n_payload(
                    row_id=row_id,
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
                    cost_inr=cost_inr,
                    extraction=None,
                    extraction_error=None,
                    extraction_model=None,
                    post_call_extraction_skipped=True,
                )
                _schedule_call_completed_webhook(payload)

"""Post-call: lead state machine, billing, counters, webhooks."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger

from db import postgres as pg_db
from n8n_webhook import fire_event_webhook, outcome_to_event
from script_runtime import outcome_buckets

_DEBUG_LOG_PATH = "/home/satyam/aakashvani/.cursor/debug-d77155.log"


def _agent_log(
    location: str,
    message: str,
    data: dict,
    *,
    hypothesis_id: str,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "d77155",
                        "runId": run_id,
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion




def _parse_callback_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            import dateparser

            parsed = dateparser.parse(
                raw,
                settings={
                    "TIMEZONE": "Asia/Kolkata",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                },
            )
            if parsed is not None:
                return parsed
        except Exception:
            pass
    return None


def _matches_bucket(val: str, bucket: set[str]) -> bool:
    v = val.casefold()
    return any(v == x.casefold() for x in bucket)


def _lead_transition(
    outcome: str,
    attempts: int,
    max_attempts: int,
    retry_delay_minutes: int,
    extraction: dict,
    *,
    post_call_snapshot: dict | None = None,
) -> tuple[str, datetime | None, datetime | None, bool]:
    """Returns (new_status, next_attempt_at, scheduled_callback_at, fire_webhook)."""
    now = datetime.now(timezone.utc)
    terminal_set, retry_set, callback_set = outcome_buckets(post_call_snapshot)

    if outcome.casefold() == "dnc":
        return "dnc", None, None, False

    if _matches_bucket(outcome, terminal_set):
        return "completed", None, None, True

    if _matches_bucket(outcome, callback_set):
        cb = _parse_callback_time(extraction.get("callback_time"))
        next_at = cb or (now + timedelta(hours=4))
        return "callback_scheduled", next_at, next_at, True

    if _matches_bucket(outcome, retry_set):
        if attempts < max_attempts:
            return (
                "pending",
                now + timedelta(minutes=retry_delay_minutes),
                None,
                False,
            )
        return "failed", None, None, True

    if attempts < max_attempts:
        return (
            "pending",
            now + timedelta(minutes=retry_delay_minutes),
            None,
            False,
        )
    return "failed", None, None, True


def resolve_post_call_transition(
    from_status: str,
    outcome: str,
    attempts: int,
    max_attempts: int,
    retry_delay_minutes: int,
    extraction: dict,
    *,
    lead_next_attempt_at: datetime | None,
    lead_scheduled_callback_at: datetime | None,
    callee_hangup: bool,
    post_call_snapshot: dict | None = None,
) -> tuple[str, datetime | None, datetime | None, bool]:
    """Apply post-call state machine using locked lead status as source of truth."""
    terminal_set, _, _ = outcome_buckets(post_call_snapshot)
    terminal_outcome = _matches_bucket(outcome, terminal_set) or outcome.casefold() == "dnc"

    new_status, next_at, sched_cb, fire_webhook = _lead_transition(
        outcome,
        attempts,
        max_attempts,
        retry_delay_minutes,
        extraction,
        post_call_snapshot=post_call_snapshot,
    )

    if from_status == "callback_scheduled" and not terminal_outcome:
        new_status = "callback_scheduled"
        next_at = lead_next_attempt_at
        sched_cb = lead_scheduled_callback_at
    elif callee_hangup and not terminal_outcome:
        now = datetime.now(timezone.utc)
        next_at = now + timedelta(minutes=retry_delay_minutes)
        new_status = "callback_scheduled"
        sched_cb = next_at
        fire_webhook = True

    return new_status, next_at, sched_cb, fire_webhook


async def _finalize_call_log_and_settle_budget(
    conn: asyncpg.Connection,
    *,
    session_call_id: str,
    duration_seconds: int,
    outcome: str,
    extraction_json: dict,
    billed_minutes: int,
    credits_charged: float,
    usage: dict,
    transcript: list[dict],
    extraction_model: str | None,
    extraction_error: str | None,
    campaign_id: UUID,
    client_id: UUID,
    call_log: dict | None,
) -> None:
    prior_outcome = (call_log or {}).get("outcome")
    prior_charged = (call_log or {}).get("credits_charged")
    already_settled = (
        prior_outcome
        and str(prior_outcome).strip()
        and prior_charged is not None
    )
    await pg_db.finalize_call_log(
        conn,
        session_call_id,
        duration_seconds,
        outcome,
        extraction_json,
        billed_minutes,
        credits_charged,
        usage,
        transcript=transcript,
        extraction_model=extraction_model,
        extraction_error=extraction_error,
    )
    if already_settled:
        return
    reserved = pg_db.budget_reserved_from_call_data(
        call_log.get("call_data") if call_log else None
    )
    await pg_db.settle_call_budget(
        conn, campaign_id, client_id, credits_charged, reserved
    )


async def recover_abandoned_session(
    pool: asyncpg.Pool,
    session_call_id: str,
) -> bool:
    """Run post-call recovery after abnormal WS disconnect."""
    from uuid import UUID

    from call_transcript import _pg_context_from_call_log, _run_campaign_post_call

    call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if not call_log or not call_log.get("lead_id"):
        return False

    hangup_json = call_log.get("plivo_hangup_json") or {}
    if isinstance(hangup_json, str):
        try:
            hangup_json = json.loads(hangup_json)
        except json.JSONDecodeError:
            hangup_json = {}
    hangup_source = str((hangup_json or {}).get("hangup_source") or "").strip().lower()
    if hangup_source.replace("_", " ") in ("api", "api request"):
        # #region agent log
        _agent_log(
            "post_call_processor.py:recover_skip_api",
            "recover skipped for API-initiated hangup",
            {"session_call_id": session_call_id, "hangup_source": hangup_source},
            hypothesis_id="A",
        )
        # #endregion
        logger.debug(
            "recover_abandoned_session skip: API hangup session={}",
            session_call_id,
        )
        return False

    client_id = UUID(str(call_log["client_id"]))
    lead = await pg_db.get_lead(pool, UUID(str(call_log["lead_id"])), client_id)
    if not lead or lead.get("status") not in ("calling", "callback_scheduled"):
        return False

    resolved_ctx = _pg_context_from_call_log(call_log)
    if not resolved_ctx:
        return False

    started = call_log.get("started_at")
    ended = call_log.get("ended_at")
    if isinstance(started, str):
        started = datetime.fromisoformat(started.replace("Z", "+00:00"))
    if isinstance(ended, str):
        ended = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    if started:
        end_ts = ended or datetime.now(timezone.utc)
        duration_seconds = max(0, int((end_ts - started).total_seconds()))
    else:
        duration_seconds = 0

    transcript = call_log.get("transcript") or []
    if isinstance(transcript, str):
        try:
            transcript = json.loads(transcript)
        except json.JSONDecodeError:
            transcript = []
    if not isinstance(transcript, list):
        transcript = []

    extraction = {"intent_status": "Unknown"}
    extraction_error = "ws_disconnect_recovery"

    if transcript:
        try:
            from post_call_extract import extract_post_call, normalize_post_call_extraction
            from script_runtime import parse_post_call_snapshot

            schema = None
            norm_rules = None
            try:
                snapshot = parse_post_call_snapshot(call_log.get("call_data") if call_log else None)
                if snapshot:
                    schema = snapshot.get("extraction_schema")
                    norm_rules = snapshot.get("normalization_rules")
            except Exception:
                pass

            parsed, err, _ = await extract_post_call(transcript, extraction_schema=schema)
            if parsed and not err:
                extraction = normalize_post_call_extraction(
                    parsed, normalization_rules=norm_rules, transcript=transcript
                )
                extraction_error = None
            else:
                extraction_error = err or "ws_recovery_extraction_failed"
        except Exception as exc:
            extraction_error = f"ws_recovery_error: {exc}"

    # #region agent log
    _agent_log(
        "post_call_processor.py:recover_extraction",
        "recover extraction result",
        {
            "session_call_id": session_call_id,
            "intent_status": (extraction or {}).get("intent_status"),
            "callback_time": (extraction or {}).get("callback_time"),
            "transcript_turns": len(transcript),
            "extraction_error": extraction_error,
        },
        hypothesis_id="B",
    )
    # #endregion

    try:
        await _run_campaign_post_call(
            resolved_ctx=resolved_ctx,
            session_call_id=session_call_id,
            duration_seconds=duration_seconds,
            transcript=transcript,
            extraction=extraction,
            usage_dict={},
            extraction_error=extraction_error,
        )
        logger.info("Recovered abandoned session {}", session_call_id)
        return True
    except Exception as exc:
        logger.exception(
            "recover_abandoned_session failed session={}: {}",
            session_call_id,
            exc,
        )
        return False


async def process_post_call(
    pool: asyncpg.Pool,
    session_call_id: str,
    lead_id: UUID,
    campaign_id: UUID,
    client_id: UUID,
    bot_config_id: UUID,
    duration_seconds: int,
    transcript: list[dict],
    extraction_json: dict,
    *,
    usage: dict | None = None,
    extraction_model: str | None = None,
    extraction_error: str | None = None,
    post_call_snapshot: dict | None = None,
) -> None:
    """
    Atomic DB transaction for lead + call_log + billing + counters.
    Webhook fires outside the transaction.
    """
    usage = usage or {}
    campaign = await pg_db.get_campaign(pool, campaign_id, client_id)
    bot_config = await pg_db.get_bot_config(pool, bot_config_id, client_id)
    lead = await pg_db.get_lead(pool, lead_id, client_id)
    if not campaign or not bot_config or not lead:
        logger.error("post_call_processor missing campaign/bot/lead")
        return

    credits_per_minute = float(bot_config["credits_per_minute"])
    _MIN_BILLABLE_DURATION_S = 15
    billed_minutes = math.ceil(duration_seconds / 60) if duration_seconds >= _MIN_BILLABLE_DURATION_S else 0
    credits_charged = billed_minutes * credits_per_minute

    outcome = (extraction_json or {}).get("intent_status", "Unknown")
    # #region agent log
    _agent_log(
        "post_call_processor.py:process_post_call",
        "post_call starting",
        {
            "session_call_id": session_call_id,
            "lead_id": str(lead_id),
            "lead_status_before": lead.get("status"),
            "outcome": outcome,
            "callback_time": (extraction_json or {}).get("callback_time"),
        },
        hypothesis_id="C",
    )
    # #endregion
    attempts = int(lead.get("attempts") or 0)
    max_attempts = int(lead.get("max_attempts") or campaign.get("max_attempts") or 3)
    retry_delay = int(campaign.get("retry_delay_minutes") or 120)

    call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if post_call_snapshot is None and call_log:
        from script_runtime import parse_post_call_snapshot

        post_call_snapshot = parse_post_call_snapshot(call_log.get("call_data"))
    _, retry_set, _ = outcome_buckets(post_call_snapshot)
    hangup_json: dict = {}
    if call_log:
        raw_hangup = call_log.get("plivo_hangup_json") or {}
        if isinstance(raw_hangup, str):
            try:
                hangup_json = json.loads(raw_hangup)
            except json.JSONDecodeError:
                hangup_json = {}
        elif isinstance(raw_hangup, dict):
            hangup_json = raw_hangup
    callee_hangup = hangup_json.get("hangup_source") == "callee"

    fire_webhook = False
    applied = False
    just_completed = False

    async with pool.acquire() as conn:
        async with conn.transaction():
            active = await pg_db.fetch_active_lead_for_post_call(
                conn, lead_id, client_id
            )
            if active is None:
                active = await pg_db.fetch_premature_recover_lead_for_post_call(
                    conn, lead_id, client_id, session_call_id
                )
            if active is None:
                await _finalize_call_log_and_settle_budget(
                    conn,
                    session_call_id=session_call_id,
                    duration_seconds=duration_seconds,
                    outcome=outcome,
                    extraction_json=extraction_json or {},
                    billed_minutes=billed_minutes,
                    credits_charged=credits_charged,
                    usage=usage,
                    transcript=transcript,
                    extraction_model=extraction_model,
                    extraction_error=extraction_error,
                    campaign_id=campaign_id,
                    client_id=client_id,
                    call_log=call_log,
                )
                logger.debug(
                    "post_call skipped lead/counters (not active) lead={} call={}",
                    lead_id,
                    session_call_id,
                )
                # #region agent log
                _agent_log(
                    "post_call_processor.py:process_post_call_skip",
                    "post_call skipped inactive lead",
                    {
                        "session_call_id": session_call_id,
                        "lead_id": str(lead_id),
                        "outcome": outcome,
                    },
                    hypothesis_id="C",
                )
                # #endregion
            else:
                from_status = active["status"]
                new_status, next_at, sched_cb, fire_webhook = resolve_post_call_transition(
                    from_status,
                    outcome,
                    attempts,
                    max_attempts,
                    retry_delay,
                    extraction_json or {},
                    lead_next_attempt_at=active.get("next_attempt_at"),
                    lead_scheduled_callback_at=active.get("scheduled_callback_at"),
                    callee_hangup=callee_hangup,
                    post_call_snapshot=post_call_snapshot,
                )
                # #region agent log
                _agent_log(
                    "post_call_processor.py:process_post_call_transition",
                    "post_call transition resolved",
                    {
                        "session_call_id": session_call_id,
                        "from_status": from_status,
                        "new_status": new_status,
                        "outcome": outcome,
                        "next_attempt_at": next_at.isoformat() if next_at else None,
                        "scheduled_callback_at": sched_cb.isoformat() if sched_cb else None,
                    },
                    hypothesis_id="C",
                )
                # #endregion
                if (
                    new_status == "pending"
                    and next_at is not None
                    and duration_seconds < 90
                    and _matches_bucket(outcome, retry_set)
                ):
                    cap_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                    if next_at > cap_at:
                        next_at = cap_at
                updated = await pg_db.update_lead_post_call(
                    conn,
                    lead_id,
                    client_id,
                    from_status,
                    new_status,
                    outcome,
                    extraction_json or {},
                    attempts,
                    next_at,
                    sched_cb,
                )
                if not updated:
                    await _finalize_call_log_and_settle_budget(
                        conn,
                        session_call_id=session_call_id,
                        duration_seconds=duration_seconds,
                        outcome=outcome,
                        extraction_json=extraction_json or {},
                        billed_minutes=billed_minutes,
                        credits_charged=credits_charged,
                        usage=usage,
                        transcript=transcript,
                        extraction_model=extraction_model,
                        extraction_error=extraction_error,
                        campaign_id=campaign_id,
                        client_id=client_id,
                        call_log=call_log,
                    )
                    logger.debug(
                        "post_call lead status race lead={} call={}",
                        lead_id,
                        session_call_id,
                    )
                else:
                    await _finalize_call_log_and_settle_budget(
                        conn,
                        session_call_id=session_call_id,
                        duration_seconds=duration_seconds,
                        outcome=outcome,
                        extraction_json=extraction_json or {},
                        billed_minutes=billed_minutes,
                        credits_charged=credits_charged,
                        usage=usage,
                        transcript=transcript,
                        extraction_model=extraction_model,
                        extraction_error=extraction_error,
                        campaign_id=campaign_id,
                        client_id=client_id,
                        call_log=call_log,
                    )
                    await pg_db.increment_campaign_counters(
                        conn, campaign_id, from_status=from_status, to_status=new_status
                    )
                    _, just_completed = await pg_db.maybe_auto_settle_campaign(
                        conn, campaign_id, client_id
                    )
                    await pg_db.maybe_transition_pausing(
                        conn, campaign_id, client_id
                    )
                    applied = True

    if applied and just_completed:
        from n8n_webhook import fire_campaign_completed_webhook
        await fire_campaign_completed_webhook(pool, client_id, campaign)

    if applied and fire_webhook:
        event_map = (
            post_call_snapshot.get("outcome_event_map")
            if post_call_snapshot
            else None
        )
        event = outcome_to_event(outcome, event_map=event_map)
        if event:
            await fire_event_webhook(
                pool,
                client_id,
                event,
                session_call_id=session_call_id,
                lead=lead,
                campaign=campaign,
                extraction=extraction_json or {},
                duration_seconds=duration_seconds,
                billed_minutes=billed_minutes,
                credits_charged=credits_charged,
                route=bot_config.get("route"),
                recording_url=call_log.get("recording_url") if call_log else None,
            )

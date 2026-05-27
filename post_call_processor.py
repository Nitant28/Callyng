"""Post-call: lead state machine, billing, counters, webhooks."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger

from db import postgres as pg_db
from n8n_webhook import fire_event_webhook, outcome_to_event

_IST = timezone.utc  # callback parsing uses UTC; compliance uses IST separately


def _parse_callback_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _lead_transition(
    outcome: str,
    attempts: int,
    max_attempts: int,
    retry_delay_minutes: int,
    extraction: dict,
) -> tuple[str, datetime | None, datetime | None, bool]:
    """Returns (new_status, next_attempt_at, scheduled_callback_at, fire_webhook)."""
    now = datetime.now(timezone.utc)

    if outcome == "dnc":
        return "dnc", None, None, False

    if outcome in ("Interested", "Not_Interested"):
        return "completed", None, None, True

    if outcome == "Callback_Requested":
        cb = _parse_callback_time(extraction.get("callback_time"))
        next_at = cb or (now + timedelta(hours=4))
        return "callback_scheduled", next_at, next_at, True

    if outcome in ("Busy", "Unknown", "Wrong_Requirement"):
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
) -> tuple[str, datetime | None, datetime | None, bool]:
    """Apply post-call state machine using locked lead status as source of truth."""
    terminal_outcome = outcome in ("Interested", "Not_Interested", "dnc")

    new_status, next_at, sched_cb, fire_webhook = _lead_transition(
        outcome,
        attempts,
        max_attempts,
        retry_delay_minutes,
        extraction,
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
    billed_minutes = max(1, math.ceil(duration_seconds / 60)) if duration_seconds > 0 else 0
    if duration_seconds > 0 and billed_minutes == 0:
        billed_minutes = 1
    credits_charged = billed_minutes * credits_per_minute

    outcome = (extraction_json or {}).get("intent_status", "Unknown")
    attempts = int(lead.get("attempts") or 0) + 1
    max_attempts = int(lead.get("max_attempts") or campaign.get("max_attempts") or 3)
    retry_delay = int(campaign.get("retry_delay_minutes") or 120)

    call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
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
                await pg_db.finalize_call_log(
                    conn,
                    session_call_id,
                    duration_seconds,
                    outcome,
                    extraction_json or {},
                    billed_minutes,
                    credits_charged,
                    usage,
                    transcript=transcript,
                    extraction_model=extraction_model,
                    extraction_error=extraction_error,
                )
                logger.debug(
                    "post_call skipped lead/counters (not active) lead={} call={}",
                    lead_id,
                    session_call_id,
                )
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
                )
                if (
                    new_status == "pending"
                    and next_at is not None
                    and duration_seconds < 90
                    and outcome in ("Busy", "Unknown", "Wrong_Requirement")
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
                    await pg_db.finalize_call_log(
                        conn,
                        session_call_id,
                        duration_seconds,
                        outcome,
                        extraction_json or {},
                        billed_minutes,
                        credits_charged,
                        usage,
                        transcript=transcript,
                        extraction_model=extraction_model,
                        extraction_error=extraction_error,
                    )
                    logger.debug(
                        "post_call lead status race lead={} call={}",
                        lead_id,
                        session_call_id,
                    )
                else:
                    await pg_db.finalize_call_log(
                        conn,
                        session_call_id,
                        duration_seconds,
                        outcome,
                        extraction_json or {},
                        billed_minutes,
                        credits_charged,
                        usage,
                        transcript=transcript,
                        extraction_model=extraction_model,
                        extraction_error=extraction_error,
                    )
                    await pg_db.increment_budget_used(
                        conn, campaign_id, client_id, credits_charged
                    )
                    await pg_db.increment_campaign_counters(
                        conn, campaign_id, from_status=from_status, to_status=new_status
                    )
                    _, just_completed = await pg_db.maybe_auto_settle_campaign(
                        conn, campaign_id, client_id
                    )
                    applied = True

    if applied and just_completed:
        from n8n_webhook import fire_campaign_completed_webhook
        await fire_campaign_completed_webhook(pool, client_id, campaign)

    if applied and fire_webhook:
        event = outcome_to_event(outcome)
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
            )

"""Asyncio campaign dialer with FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import aiohttp
from loguru import logger

from compliance import is_call_allowed, next_compliant_time
from db import postgres as pg_db
from dialer.cost_guard import MIN_REMAINING_CREDITS, check_campaign_budget
from telephony import build_hangup_url, make_plivo_call
from script_prefetch import (
    build_lead_dict,
    pop_prefetched_config,
    register_prefetched_config,
    render_script_config,
)
from script_runtime import build_post_call_snapshot_from_prefetch
from dialer.dialer_lock import (
    acquire_dialer_lock,
    refresh_dialer_lock,
    release_dialer_lock,
)
from dialer.plivo_balance import (
    check_plivo_balance,
    exception_is_plivo_balance_exhausted,
    invalidate_plivo_balance_cache,
)

_active_tasks: dict[str, asyncio.Task] = {}
import time as _time

_last_release_stuck_at: dict[str, float] = {}
_RELEASE_STUCK_COOLDOWN_S = 30.0


def _campaign_key(campaign_id: UUID, client_id: UUID) -> str:
    return f"{client_id}:{campaign_id}"


async def _release_lead_to_pending(
    pool,
    lead: dict,
    campaign_id: UUID,
    client_id: UUID,
    *,
    defer_until: datetime | None = None,
) -> None:
    """Return a claimed lead to pending when compliance blocks the dial."""
    lead_id = UUID(str(lead["id"]))
    attempts = int(lead.get("attempts") or 0)
    max_att = int(lead.get("max_attempts") or 3)
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT status FROM leads WHERE id = $1 AND client_id = $2 FOR UPDATE",
                lead_id, client_id
            )
            if not row or row["status"] != "calling":
                return
                
            if attempts >= max_att:
                await conn.execute(
                    """
                    UPDATE leads
                    SET status = 'failed',
                        outcome = COALESCE(NULLIF(TRIM(outcome), ''), 'Max_Attempts_Reached')
                    WHERE id = $1
                    """,
                    lead_id,
                )
                await pg_db.increment_campaign_counters(
                    conn, campaign_id, from_status="calling", to_status="failed"
                )
            else:
                next_at = defer_until or datetime.now(timezone.utc)
                await conn.execute(
                    """
                    UPDATE leads
                    SET status = 'pending',
                        next_attempt_at = $2
                    WHERE id = $1
                    """,
                    lead_id,
                    next_at,
                )
                await pg_db.increment_campaign_counters(
                    conn, campaign_id, from_status="calling", to_status="pending"
                )

            grace = pg_db.live_call_grace_minutes()
            has_live_call = await conn.fetchval(
                """
                SELECT 1 FROM call_logs
                WHERE lead_id = $1 AND in_progress = TRUE
                  AND started_at > NOW() - ($2 * INTERVAL '1 minute')
                LIMIT 1
                """,
                lead_id,
                grace,
            )
            if not has_live_call:
                await pg_db.release_campaign_budget_reservation(
                    conn, campaign_id, client_id, 1
                )


async def pause_campaign(
    pool,
    campaign_id: UUID,
    client_id: UUID,
    *,
    reason: str,
) -> None:
    await pg_db.update_campaign_status(pool, campaign_id, client_id, "paused")
    logger.warning("Campaign {} paused: {}", campaign_id, reason)


async def complete_campaign(pool, campaign_id: UUID, client_id: UUID) -> None:
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
    if released:
        logger.warning(
            "Campaign {} released {} lead(s) stuck in calling before complete",
            campaign_id,
            released,
        )
    await pg_db.return_unused_budget(campaign_id, client_id, final_status="completed")
    logger.info("Campaign {} completed, unused credits returned", campaign_id)


def _public_base_url(host: str) -> str:
    """Plivo must reach a public URL — never localhost."""
    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    if ngrok:
        return ngrok
    if host and not host.startswith(("localhost", "127.0.0.1")):
        return f"https://{host.split(':')[0]}"
    return "http://localhost:7860"


async def fire_call(
    session: aiohttp.ClientSession,
    lead: dict,
    campaign: dict,
    bot_config: dict,
    *,
    host: str = "localhost:7860",
    pool=None,
    client_id: UUID | None = None,
    campaign_id: UUID | None = None,
    dial_phone: str | None = None,
    is_test_call: bool = False,
    budget_reserved_credits: Decimal | float = 0,
) -> str | None:
    """Place outbound call via Plivo. Returns session_call_id or None if skipped."""
    call_id = str(uuid.uuid4())
    phone = dial_phone or lead["phone"]
    cid = client_id or UUID(str(campaign["client_id"]))
    camp_id = campaign_id or (UUID(str(campaign["id"])) if campaign.get("id") else None)
    lead_uuid = UUID(str(lead["id"])) if lead.get("id") else None
    bot_config_id = UUID(str(bot_config["id"])) if bot_config.get("id") else None
    
    if pool is None:
        pool = pg_db.get_pool()
        
    grace = pg_db.live_call_grace_minutes()
    wrap = pg_db.post_call_wrap_grace_minutes()
    
    if lead_uuid:
        live = await pool.fetchval(
            """
            SELECT 1 FROM call_logs
            WHERE lead_id = $1 AND in_progress = TRUE
              AND started_at > NOW() - ($2 * INTERVAL '1 minute')
            LIMIT 1
            """,
            lead_uuid,
            grace,
        )
        if live:
            logger.warning(
                "Skipping duplicate Plivo dial for lead {} — in_progress call_log exists",
                lead_uuid,
            )
            return
        recent_end = await pool.fetchval(
            """
            SELECT 1 FROM call_logs
            WHERE lead_id = $1
              AND ended_at IS NOT NULL
              AND ended_at > NOW() - ($2 * INTERVAL '1 minute')
            LIMIT 1
            """,
            lead_uuid,
            wrap,
        )
        if recent_end:
            logger.warning(
                "Skipping Plivo dial for lead {} — post_call wrap-up in progress",
                lead_uuid,
            )
            return

    meta = lead.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}

    body_data = {
        "phone_number": phone,
        "lead_name": lead.get("name") or "Sir/Madam",
        "city": meta.get("city", ""),
        "_session_call_id": call_id,
        "_pg": {
            "client_id": str(cid),
            "campaign_id": str(camp_id) if camp_id else "",
            "lead_id": str(lead_uuid) if lead_uuid else "",
            "bot_config_id": str(bot_config_id) if bot_config_id else "",
            "route": bot_config["route"],
            "script_id": bot_config["script_id"],
            "max_call_minutes": campaign.get("max_call_minutes"),
            "extraction_schema_override": campaign.get("extraction_schema_override"),
        },
    }

    script_config_id = bot_config.get("script_config_id")
    prefetch_registered = False
    call_data_for_insert = None
    if script_config_id:
        row = await pg_db.get_script_config(
            pool, UUID(str(script_config_id)), cid
        )
        if row is None:
            logger.error(
                "script_config {} missing or inactive for bot_config {}",
                script_config_id,
                bot_config.get("id"),
            )
            await _release_lead_to_pending(pool, lead, camp_id, cid)
            return
        if row.get("route") != bot_config["route"]:
            logger.error(
                "script_config {} route {} != bot_config route {}",
                script_config_id,
                row.get("route"),
                bot_config["route"],
            )
            if lead_uuid:
                await _release_lead_to_pending(pool, lead, camp_id, cid)
            return
        lead_dict = build_lead_dict(lead, meta)
        try:
            config = render_script_config(
                row, lead_dict, expected_route=bot_config["route"]
            )
        except ValueError as exc:
            logger.error(
                "Failed to render script_config {} for call {}: {}",
                script_config_id,
                call_id,
                exc,
            )
            if lead_uuid:
                await _release_lead_to_pending(pool, lead, camp_id, cid)
            return
        await register_prefetched_config(call_id, config)
        prefetch_registered = True
        call_data_for_insert = build_post_call_snapshot_from_prefetch(
            config,
            extraction_override=campaign.get("extraction_schema_override"),
        )

    started_at = datetime.now(timezone.utc)
    base = _public_base_url(host)
    encoded = urllib.parse.quote(json.dumps(body_data))
    answer_url = f"{base}/answer?call_id={call_id}&body_data={encoded}"
    hangup_url = build_hangup_url(call_id, host=host)

    from_number = (
        bot_config.get("telephony_number")
        or os.getenv("PLIVO_PHONE_NUMBER", "")
    )
    if not await check_plivo_balance(session):
        if prefetch_registered:
            await pop_prefetched_config(call_id)
        if lead_uuid:
            await _release_lead_to_pending(pool, lead, camp_id, cid)
        raise Exception("Plivo error (402): Insufficient balance")

    try:
        await pg_db.insert_call_log_start(
            pool,
            session_call_id=call_id,
            client_id=cid,
            campaign_id=camp_id,
            lead_id=lead_uuid,
            bot_config_id=bot_config_id,
            route=bot_config["route"],
            started_at=started_at,
            call_data=call_data_for_insert,
            is_test_call=is_test_call,
            budget_reserved_credits=budget_reserved_credits,
        )
    except Exception as exc:
        if prefetch_registered:
            await pop_prefetched_config(call_id)
        logger.error(
            "DB insert failed for lead {} (call_id={}): {}",
            lead_uuid,
            call_id,
            exc,
        )
        if lead_uuid:
            await _release_lead_to_pending(pool, lead, camp_id, cid)
        raise

    try:
        await make_plivo_call(
            session,
            phone,
            from_number,
            answer_url,
            hangup_url=hangup_url,
        )
        logger.info(
            "Dialer fired call call_id={} lead={} campaign={} answer_url={}",
            call_id,
            lead.get("id"),
            camp_id,
            answer_url,
        )
        return call_id
    except Exception as exc:
        if prefetch_registered:
            await pop_prefetched_config(call_id)
        # Mark orphaned call_log as not-in-progress so _release_lead_to_pending
        # doesn't see it as live and skip budget release (EDGE-05).
        try:
            await pg_db.mark_call_log_not_in_progress(
                pool, call_id, set_credits_charged_zero=True
            )
        except Exception:
            pass
        if exception_is_plivo_balance_exhausted(exc):
            invalidate_plivo_balance_cache()
        logger.error(
            "Plivo dial failed for lead {} (call_id={}): {}",
            lead_uuid,
            call_id,
            exc,
        )
        if lead_uuid:
            await _release_lead_to_pending(pool, lead, camp_id, cid)
        raise


async def run_campaign_dialer(
    pool,
    campaign_id: UUID,
    client_id: UUID,
    *,
    session: aiohttp.ClientSession,
    host: str = "localhost:7860",
    lock_token: str,
) -> None:
    """Main dialer loop per guides/aakash_arch.md §7."""
    logger.info("Dialer started for campaign {}", campaign_id)
    stale = await pg_db.finalize_stale_in_progress_call_logs(
        pool, campaign_id, client_id
    )
    if stale:
        logger.warning(
            "Campaign {} finalized {} stale call_log(s) at dialer start",
            campaign_id,
            stale,
        )
    released = await pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)
    if released:
        logger.warning(
            "Campaign {} released {} lead(s) stuck in calling at dialer start",
            campaign_id,
            released,
        )
    counts = await pg_db.reconcile_campaign_counters(pool, campaign_id, client_id)
    logger.info(
        "Campaign {} counters reconciled: pending={} calling={} callback={}",
        campaign_id,
        counts["pending_leads"],
        counts["calling_leads"],
        counts["callback_leads"],
    )
    try:
        while True:
            if not await refresh_dialer_lock(campaign_id, lock_token):
                logger.warning(
                    "Dialer lock lost for campaign {}; stopping",
                    campaign_id,
                )
                break

            campaign = await pg_db.get_campaign(pool, campaign_id, client_id)
            if campaign is None:
                break
            if campaign["status"] != "running":
                logger.info(
                    "Campaign {} status={}, dialer stopping",
                    campaign_id,
                    campaign["status"],
                )
                break

            actual_calling = await pool.fetchval(
                """
                SELECT COUNT(*)::int FROM leads
                WHERE campaign_id = $1 AND client_id = $2 AND status = 'calling'
                """,
                campaign_id,
                client_id,
            )
            effective_calling = max(
                int(campaign["calling_leads"]),
                int(actual_calling or 0),
            )
            client_max_row = await pool.fetchrow(
                "SELECT max_concurrent_calls FROM clients WHERE id = $1",
                client_id,
            )
            client_max = int(
                (client_max_row["max_concurrent_calls"] if client_max_row else None)
                or 5
            )
            campaign_max = min(
                int(campaign["max_concurrent_calls"]),
                client_max,
            )
            slots = campaign_max - effective_calling
            if slots <= 0:
                ck = _campaign_key(campaign_id, client_id)
                now_mono = _time.monotonic()
                last = _last_release_stuck_at.get(ck, 0.0)
                if now_mono - last >= _RELEASE_STUCK_COOLDOWN_S:
                    _last_release_stuck_at[ck] = now_mono
                    released = await pg_db.release_stuck_calling_leads(
                        pool, campaign_id, client_id
                    )
                    if released:
                        logger.info(
                            "Campaign {} released {} lead(s) stuck in calling (slots full)",
                            campaign_id,
                            released,
                        )
                        continue
                await asyncio.sleep(2)
                continue

            if not await check_plivo_balance(session):
                invalidate_plivo_balance_cache()
                await pause_campaign(
                    pool,
                    campaign_id,
                    client_id,
                    reason="plivo_balance_exhausted",
                )
                break

            if not await check_campaign_budget(pool, campaign_id, client_id):
                await pause_campaign(
                    pool,
                    campaign_id,
                    client_id,
                    reason="budget_exhausted",
                )
                break

            exhausted = await pg_db.terminalize_exhausted_leads(
                pool, campaign_id, client_id
            )
            if exhausted:
                logger.info(
                    "Campaign {} terminalized {} exhausted lead(s)",
                    campaign_id,
                    exhausted,
                )

            leads = await pg_db.claim_leads_for_dialer(
                pool, campaign_id, client_id, slots
            )
            if not leads:
                pending = int(campaign["pending_leads"])
                callback = int(campaign["callback_leads"])
                calling = int(campaign["calling_leads"])
                actual_calling_loop = int(actual_calling or 0)

                # Ghost ``calling`` rows (no live call_log) block the dialer. Skip live calls.
                if calling > 0 or actual_calling_loop > 0:
                    ck = _campaign_key(campaign_id, client_id)
                    now_mono = _time.monotonic()
                    last = _last_release_stuck_at.get(ck, 0.0)
                    if now_mono - last >= _RELEASE_STUCK_COOLDOWN_S:
                        _last_release_stuck_at[ck] = now_mono
                        released = await pg_db.release_stuck_calling_leads(
                            pool, campaign_id, client_id
                        )
                        if released:
                            logger.info(
                                "Campaign {} released {} lead(s) stuck in calling",
                                campaign_id,
                                released,
                            )
                            continue
                    else:
                        logger.debug(
                            "Campaign {} skipping release_stuck (cooldown, {}s since last)",
                            campaign_id,
                            round(now_mono - last, 1),
                        )

                if pending == 0 and callback == 0 and calling == 0:
                    await complete_campaign(pool, campaign_id, client_id)
                    break

                diag = await pg_db.diagnose_claim_blockers(
                    pool, campaign_id, client_id
                )
                claimable = int(diag.get("claimable_now") or 0)
                pending_future = int(diag.get("pending_future") or 0)
                blocked_live = int(diag.get("blocked_live_call_log") or 0)
                blocked_wrap = int(diag.get("blocked_wrap_up") or 0)

                if blocked_live > 0:
                    stale = await pg_db.finalize_stale_in_progress_call_logs(
                        pool, campaign_id, client_id
                    )
                    if stale:
                        logger.info(
                            "Campaign {} finalized {} stale call_log(s) blocking claim",
                            campaign_id,
                            stale,
                        )
                        continue

                if claimable == 0 and pending_future > 0:
                    logger.info(
                        "Campaign {} has {} pending lead(s) waiting for retry "
                        "(next_attempt_at in future, claimable=0). "
                        "Counter pending_leads={} includes not-yet-due rows. "
                        "next_retry_at={}",
                        campaign_id,
                        pending_future,
                        pending,
                        diag.get("next_pending_retry_at"),
                    )
                elif claimable == 0 and blocked_wrap > 0:
                    logger.info(
                        "Campaign {} claimable=0: {} lead(s) in post-call wrap-up "
                        "(wait {} min after last ended call_log)",
                        campaign_id,
                        blocked_wrap,
                        pg_db.post_call_wrap_grace_minutes(),
                    )
                else:
                    logger.debug(
                        "Campaign {} waiting: pending={} callback={} calling={} "
                        "claimable={}",
                        campaign_id,
                        pending,
                        callback,
                        calling,
                        claimable,
                    )
                await asyncio.sleep(5)
                continue

            bot_config = await pg_db.get_bot_config(
                pool,
                UUID(str(campaign["bot_config_id"])),
                client_id,
            )
            if bot_config is None:
                logger.error("Bot config missing for campaign {}", campaign_id)
                break

            tasks = []
            for lead in leads:
                allowed, reason = is_call_allowed()
                if not allowed:
                    logger.warning(
                        "Skipping lead {} ({}): {}",
                        lead.get("id"),
                        lead.get("phone"),
                        reason,
                    )
                    defer_until = None
                    if "outside 9am-9pm" in reason:
                        defer_until = next_compliant_time()
                    
                    await _release_lead_to_pending(
                        pool, lead, campaign_id, client_id, defer_until=defer_until
                    )
                    continue
                tasks.append(
                    fire_call(
                        session,
                        lead,
                        campaign,
                        bot_config,
                        host=host,
                        pool=pool,
                        client_id=client_id,
                        campaign_id=campaign_id,
                        budget_reserved_credits=MIN_REMAINING_CREDITS,
                    )
                )
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception) and (
                        exception_is_plivo_balance_exhausted(result)
                    ):
                        invalidate_plivo_balance_cache()
                        await pause_campaign(
                            pool,
                            campaign_id,
                            client_id,
                            reason="plivo_balance_exhausted",
                        )
                        return

            cpm = max(int(campaign.get("calls_per_minute") or 10), 1)
            await asyncio.sleep(60 / cpm)
    except asyncio.CancelledError:
        logger.info("Dialer cancelled for campaign {}", campaign_id)
        raise
    finally:
        key = _campaign_key(campaign_id, client_id)
        if _active_tasks.get(key) is asyncio.current_task():
            _active_tasks.pop(key, None)
        await release_dialer_lock(campaign_id, lock_token)


async def start_dialer(
    app,
    campaign_id: UUID,
    client_id: UUID,
    *,
    host: str | None = None,
) -> None:
    pool = app.state.pool
    if pool is None:
        raise RuntimeError("PostgreSQL pool not available")
    key = _campaign_key(campaign_id, client_id)
    existing = _active_tasks.get(key)
    if existing and not existing.done():
        logger.warning(
            "Dialer already running locally for campaign {} (key={})",
            campaign_id,
            key,
        )
        return

    lock_token = await acquire_dialer_lock(campaign_id)
    if lock_token is None:
        logger.warning(
            "Dialer lock not acquired for campaign {} — another worker is active",
            campaign_id,
        )
        return

    h = host or os.getenv("DIALER_CALLBACK_HOST", "localhost:7860")

    async def _runner() -> None:
        try:
            await run_campaign_dialer(
                pool,
                campaign_id,
                client_id,
                session=app.state.session,
                host=h,
                lock_token=lock_token,
            )
        finally:
            if app.state.dialer_tasks.get(key) is task:
                app.state.dialer_tasks.pop(key, None)

    task = asyncio.create_task(_runner())
    _active_tasks[key] = task
    app.state.dialer_tasks[key] = task


async def stop_dialer(campaign_id: UUID, client_id: UUID) -> None:
    ck = _campaign_key(campaign_id, client_id)
    _last_release_stuck_at.pop(ck, None)

    task = _active_tasks.get(ck)
    if not task:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("stop_dialer: dialer teardown raised: {}", exc)

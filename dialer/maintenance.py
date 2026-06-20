"""Background maintenance for dialer / call_logs."""

from __future__ import annotations

import asyncio
import os

import asyncpg
from loguru import logger

from db import postgres as pg_db
from script_prefetch import sweep_stale_prefetched_configs


def stale_call_log_sweep_enabled() -> bool:
    raw = (os.getenv("STALE_CALL_LOG_SWEEP_ENABLED") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def stale_call_log_sweep_seconds() -> int:
    raw = (os.getenv("STALE_CALL_LOG_SWEEP_SECONDS") or "300").strip()
    try:
        secs = int(raw)
    except ValueError:
        secs = 300
    return max(secs, 60)


async def run_stale_call_log_sweep(pool: asyncpg.Pool) -> int:
    n = await pg_db.finalize_all_stale_in_progress_call_logs(pool)
    if n:
        logger.info("Stale call_log sweep finalized {} row(s)", n)
        
    settled = await pg_db.settle_budget_for_stale_call_logs(pool)
    if settled:
        logger.info("Stale sweep settled budget for {} call_log(s)", settled)
    
    released = await pg_db.release_all_stuck_calling_leads(pool)
    if released:
        logger.info("Global sweep released {} stuck calling lead(s)", released)
        
    transitioned = await pg_db.transition_all_pausing_to_paused(pool)
    if transitioned:
        logger.info("Global sweep transitioned {} pausing campaign(s) to paused", transitioned)

    await sweep_stale_prefetched_configs(pool)

    return n


async def stale_call_log_loop(pool: asyncpg.Pool, interval_seconds: int) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await run_stale_call_log_sweep(pool)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Stale call_log sweep failed: {}", exc)

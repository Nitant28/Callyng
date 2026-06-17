"""Redis-backed call state tests (require REDIS_URL)."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)


def _run(coro):
    return asyncio.run(coro)


async def _init_redis():
    from db import redis_client as redis_db

    await redis_db.init_redis()


async def _close_redis():
    from db import redis_client as redis_db

    await redis_db.close_redis()


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
def test_prefetch_register_and_pop_round_trip():
    async def _run_test():
        import script_prefetch as sp

        await _init_redis()
        try:
            await sp.register_prefetched_config("sid-rt", {"route": "sts", "version": 1})
            cfg = await sp.pop_prefetched_config("sid-rt")
            assert cfg == {"route": "sts", "version": 1}
            assert await sp.pop_prefetched_config("sid-rt") is None
        finally:
            await _close_redis()

    _run(_run_test())


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
def test_pg_context_register_and_pop_round_trip():
    async def _run_test():
        from call_transcript import pop_pg_context, register_pg_context

        await _init_redis()
        try:
            pg = {"client_id": "c1", "campaign_id": "camp1", "lead_id": "l1"}
            await register_pg_context("call-pg", pg)
            ctx = await pop_pg_context("call-pg")
            assert ctx == pg
            assert await pop_pg_context("call-pg") is None
        finally:
            await _close_redis()

    _run(_run_test())


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
def test_warmup_pending_to_ready():
    async def _run_test():
        from db import redis_client as redis_db
        from db.warmup_state import (
            set_warmup_pending,
            set_warmup_ready,
            wait_for_warmup,
        )

        await _init_redis()
        call_id = f"warmup-{uuid.uuid4().hex}"
        try:
            await set_warmup_pending(call_id)
            redis = redis_db.get_redis()
            assert await redis.get(f"warmup:{call_id}") == "pending"
            await set_warmup_ready(call_id)
            ready = await wait_for_warmup(call_id, timeout_s=1.0)
            assert ready is True
        finally:
            await _close_redis()

    _run(_run_test())


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
def test_dialer_lock_acquire_refresh_release():
    async def _run_test():
        from dialer.dialer_lock import (
            acquire_dialer_lock,
            refresh_dialer_lock,
            release_dialer_lock,
        )

        await _init_redis()
        campaign_id = uuid.uuid4()
        try:
            token_a = await acquire_dialer_lock(campaign_id)
            assert token_a is not None
            token_b = await acquire_dialer_lock(campaign_id)
            assert token_b is None
            assert await refresh_dialer_lock(campaign_id, token_a) is True
            await release_dialer_lock(campaign_id, token_a)
            token_c = await acquire_dialer_lock(campaign_id)
            assert token_c is not None
            await release_dialer_lock(campaign_id, token_c)
        finally:
            await _close_redis()

    _run(_run_test())


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
def test_sweep_stale_prefetched_configs():
    async def _run_test():
        import script_prefetch as sp

        await _init_redis()
        try:
            await sp.register_prefetched_config("call-live", {"route": "sts"})
            await sp.register_prefetched_config("call-done", {"route": "sts"})
            await sp.register_prefetched_config("call-orphan", {"route": "sts"})

            class _Pool:
                async def fetch(self, _sql, keys):
                    assert "call-live" in keys
                    return [{"session_call_id": "call-done"}]

            n = await sp.sweep_stale_prefetched_configs(_Pool())
            assert n == 1
            assert await sp.pop_prefetched_config("call-live") is not None
            assert await sp.pop_prefetched_config("call-done") is None
            assert await sp.pop_prefetched_config("call-orphan") is not None
        finally:
            await _close_redis()

    _run(_run_test())

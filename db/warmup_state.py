"""Redis-backed Gemini pre-warm signaling for /start → /answer."""

from __future__ import annotations

import asyncio
import time

from db.redis_client import get_redis

WARMUP_TTL_SECONDS = 120
_WARMUP_KEY_PREFIX = "warmup:"


def _warmup_key(call_id: str) -> str:
    return f"{_WARMUP_KEY_PREFIX}{call_id}"


async def set_warmup_pending(call_id: str) -> None:
    redis = get_redis()
    await redis.set(_warmup_key(call_id), "pending", ex=WARMUP_TTL_SECONDS)


async def set_warmup_ready(call_id: str) -> None:
    redis = get_redis()
    await redis.set(_warmup_key(call_id), "ready", ex=WARMUP_TTL_SECONDS)


async def clear_warmup(call_id: str) -> None:
    redis = get_redis()
    await redis.delete(_warmup_key(call_id))


async def wait_for_warmup(call_id: str, *, timeout_s: float = 3.0) -> bool:
    """Poll Redis until warmup is ready or timeout. Returns True if ready."""
    redis = get_redis()
    key = _warmup_key(call_id)
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            value = await redis.get(key)
            if value == "ready":
                return True
            if value is None:
                return False
            await asyncio.sleep(0.1)
        return (await redis.get(key)) == "ready"
    finally:
        await redis.delete(key)

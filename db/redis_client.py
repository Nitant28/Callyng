"""Async Redis connection pool (required for multi-worker state)."""

from __future__ import annotations

import os

from loguru import logger
from redis.asyncio import Redis

_redis: Redis | None = None


def redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL is not set")
    return url


async def init_redis(url: str | None = None) -> Redis:
    global _redis
    dsn = url or redis_url()
    client = Redis.from_url(dsn, decode_responses=True)
    await client.ping()
    _redis = client
    logger.info("[startup] Redis ready at {}", dsn.split("@")[-1])
    return client


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized; call init_redis() first")
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None

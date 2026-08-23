"""Redis helpers for cold-transfer Dial XML lookup."""

from __future__ import annotations

from loguru import logger

from db.redis_client import get_redis

TRANSFER_TTL_SECONDS = 600


def transfer_redis_key(session_call_id: str) -> str:
    return f"transfer:{session_call_id}"


async def store_transfer_destination(session_call_id: str, e164: str) -> None:
    sid = (session_call_id or "").strip()
    number = (e164 or "").strip()
    if not sid or not number:
        return
    try:
        redis = get_redis()
    except RuntimeError:
        logger.warning("Redis not initialized; transfer XML lookup will 404")
        return
    await redis.set(transfer_redis_key(sid), number, ex=TRANSFER_TTL_SECONDS)
    logger.info("transfer dest stored session={} to={}", sid, number)


async def load_transfer_destination(session_call_id: str) -> str | None:
    sid = (session_call_id or "").strip()
    if not sid:
        return None
    try:
        redis = get_redis()
    except RuntimeError:
        return None
    raw = await redis.get(transfer_redis_key(sid))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    text = str(raw).strip()
    return text or None


async def has_transfer_flag(session_call_id: str) -> bool:
    return await load_transfer_destination(session_call_id) is not None

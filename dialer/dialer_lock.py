"""Redis distributed lock so only one worker runs a campaign dialer."""

from __future__ import annotations

import uuid
from uuid import UUID

from db.redis_client import get_redis

DIALER_LOCK_TTL_SECONDS = 30
_LOCK_PREFIX = "dialer_lock:"

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_REFRESH_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


def _lock_key(resource_id: UUID | str, resource_type: str = "campaign") -> str:
    return f"{_LOCK_PREFIX}{resource_type}:{resource_id}"

async def acquire_dialer_lock(
    resource_id: UUID | str,
    resource_type: str = "campaign",
) -> str | None:
    """Return lock token if acquired, else None."""
    redis = get_redis()
    token = uuid.uuid4().hex

    acquired = await redis.set(
        _lock_key(resource_id, resource_type),
        token,
        nx=True,
        ex=DIALER_LOCK_TTL_SECONDS,
    )

    return token if acquired else None


async def refresh_dialer_lock(
    resource_id: UUID | str,
    token: str,
    resource_type: str = "campaign",
) -> bool:
    redis = get_redis()

    result = await redis.eval(
        _REFRESH_SCRIPT,
        1,
        _lock_key(resource_id, resource_type),
        token,
        str(DIALER_LOCK_TTL_SECONDS),
    )

    return bool(result)


async def release_dialer_lock(
    resource_id: UUID | str,
    token: str,
    resource_type: str = "campaign",
) -> None:
    redis = get_redis()

    await redis.eval(
        _RELEASE_SCRIPT,
        1,
        _lock_key(resource_id, resource_type),
        token,
    )
"""API key resolution for cascade providers (env today; BYOK in Phase 3)."""

from __future__ import annotations

import os
from typing import Any


async def resolve_api_key(
    env_name: str,
    *,
    provider: str,
    client_id: Any = None,
    pool: Any = None,
) -> str:
    """Return the platform API key for *env_name*.

    *client_id* and *pool* are reserved for Phase 3 BYOK; both may be ``None``.
    """
    del client_id, pool  # BYOK hook — unused until Phase 3
    key = (os.getenv(env_name) or "").strip()
    if not key:
        raise ValueError(f"{provider}: {env_name} is not set")
    return key

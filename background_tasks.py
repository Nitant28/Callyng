"""Track in-flight post-call background tasks for graceful shutdown."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_registry: set[asyncio.Task[Any]] | None = None


def bind_background_tasks(registry: set[asyncio.Task[Any]]) -> None:
    """Wire ``app.state.background_tasks`` at startup."""
    global _registry
    _registry = registry


def spawn_background_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Create a task and retain a strong reference until it completes."""
    task = asyncio.create_task(coro)
    if _registry is not None:
        _registry.add(task)
        task.add_done_callback(_registry.discard)
    return task


async def drain_background_tasks() -> None:
    """Await pending background tasks (e.g. before DB pool teardown)."""
    if _registry is None:
        return
    pending = [t for t in list(_registry) if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

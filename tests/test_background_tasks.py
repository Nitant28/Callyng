"""Tests for background task registry."""

from __future__ import annotations

import asyncio

from background_tasks import bind_background_tasks, drain_background_tasks, spawn_background_task


def test_spawn_registers_and_drains_tasks():
    async def _run():
        registry: set[asyncio.Task] = set()
        bind_background_tasks(registry)
        done = asyncio.Event()

        async def _work():
            await asyncio.sleep(0.05)
            done.set()

        spawn_background_task(_work())
        assert len(registry) == 1
        await drain_background_tasks()
        assert done.is_set()
        assert len(registry) == 0

    asyncio.run(_run())


def test_spawn_removes_task_on_completion():
    async def _run():
        registry: set[asyncio.Task] = set()
        bind_background_tasks(registry)

        async def _noop():
            return None

        task = spawn_background_task(_noop())
        await task
        assert task not in registry
        assert len(registry) == 0

    asyncio.run(_run())


def test_spawn_keeps_strong_reference_until_done():
    """Regression: orphan create_task can be GC'd; spawn retains in registry."""

    async def _run():
        registry: set[asyncio.Task] = set()
        bind_background_tasks(registry)
        ran = asyncio.Event()

        async def _work():
            await asyncio.sleep(0.02)
            ran.set()

        spawn_background_task(_work(), "prewarm_like")
        assert len(registry) == 1
        await drain_background_tasks()
        assert ran.is_set()

    asyncio.run(_run())

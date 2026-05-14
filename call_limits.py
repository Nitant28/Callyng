"""Shared max-duration watchdog and idempotent ``end_call`` LLM tool wiring."""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.task import PipelineTask
from pipecat.services.llm_service import FunctionCallParams


def parse_max_call_minutes() -> float:
    """Return minutes for the watchdog; ``0`` means disabled.

    Default ``10``. Invalid env values disable the watchdog (log warning).
    """
    raw = (os.getenv("MAX_CALL_MINUTES") or "10").strip()
    try:
        v = float(raw)
        return v if v > 0 else 0.0
    except ValueError:
        logger.warning("Invalid MAX_CALL_MINUTES={!r}; watchdog disabled", raw)
        return 0.0


def end_call_function_schema() -> FunctionSchema:
    """Single no-arg tool: hang up after the model finishes its closing turn."""
    return FunctionSchema(
        name="end_call",
        description=(
            "Call exactly once in the same turn after you have spoken your final "
            "goodbye, when the conversation should end and the phone should hang up. "
            "Do not call mid-conversation or before your closing line."
        ),
        properties={},
        required=[],
    )


class CallEndCoordinator:
    """Queues ``EndFrame`` at most once (timer + tool + races)."""

    def __init__(self, task: PipelineTask) -> None:
        self._task = task
        self._lock = asyncio.Lock()
        self._ended = False
        self._watchdog_task: asyncio.Task[None] | None = None

    def attach_watchdog_task(self, t: asyncio.Task[None] | None) -> None:
        """Background max-duration task; cancelled on successful ``try_end`` or by caller."""
        self._watchdog_task = t

    def _cancel_watchdog_if_pending(self) -> None:
        wt = self._watchdog_task
        if wt is None or wt.done():
            return
        # Do not cancel the watchdog while we are running inside it (timer path).
        if wt is asyncio.current_task():
            return
        wt.cancel()

    async def try_end(self, reason: str) -> bool:
        async with self._lock:
            if self._ended:
                return False
            self._ended = True
        logger.info("call end: {}", reason)
        try:
            await self._task.queue_frames([EndFrame()])
        except Exception as exc:
            async with self._lock:
                self._ended = False
            logger.warning("call end queue_frames failed: {}", exc)
            return False
        self._cancel_watchdog_if_pending()
        return True


@dataclass(frozen=True)
class ScheduledCallLimits:
    """Result of ``schedule_max_call_duration`` — use ``watchdog_task`` to cancel early."""

    coordinator: CallEndCoordinator
    watchdog_task: asyncio.Task[None] | None


def schedule_max_call_duration(
    task: PipelineTask, minutes: float, label: str
) -> ScheduledCallLimits:
    """Start optional background sleep then ``try_end(label)``; return coordinator + task."""
    coordinator = CallEndCoordinator(task)
    if minutes <= 0:
        logger.debug("max call duration watchdog disabled (minutes={})", minutes)
        return ScheduledCallLimits(coordinator=coordinator, watchdog_task=None)

    async def _watchdog() -> None:
        try:
            await asyncio.sleep(minutes * 60.0)
            await coordinator.try_end(label)
        except asyncio.CancelledError:
            raise

    watchdog_task = asyncio.create_task(_watchdog())
    coordinator.attach_watchdog_task(watchdog_task)
    logger.info("max call duration watchdog: {:.2f} min ({})", minutes, label)
    return ScheduledCallLimits(
        coordinator=coordinator, watchdog_task=watchdog_task
    )


# Docs / backward-friendly name for ``ScheduledCallLimits``.
ScheduledCall = ScheduledCallLimits


def parse_goodbye_hangup_enabled() -> bool:
    """STS fallback: detect scripted goodbye in transcript and ``try_end`` after delay.

    Default **enabled** (``1``). Set ``GOODBYE_HANGUP_ENABLE=0`` to disable.
    """
    raw = (os.getenv("GOODBYE_HANGUP_ENABLE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def parse_goodbye_hangup_delay_s() -> float:
    """Seconds to wait after a goodbye-like assistant turn before ``try_end``."""
    raw = (os.getenv("GOODBYE_HANGUP_DELAY_S") or "2").strip()
    try:
        v = float(raw)
    except ValueError:
        logger.warning("Invalid GOODBYE_HANGUP_DELAY_S={!r}; using 2.0", raw)
        return 2.0
    return max(0.5, min(v, 30.0))


_WS_RE = re.compile(r"\s+")


def _normalize_for_goodbye_match(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.casefold()
    s = _WS_RE.sub(" ", s).strip()
    return s


def register_goodbye_hangup_fallback(
    user_aggregator: Any,
    assistant_aggregator: Any,
    coordinator: CallEndCoordinator,
    *,
    markers: Sequence[str],
    enabled: bool,
    delay_s: float,
) -> Callable[[], None]:
    """If assistant text matches a terminal-script marker, schedule ``try_end`` after ``delay_s``.

    Cancels the pending hangup when the user speaks again (``on_user_turn_stopped``)
    or when another assistant turn starts. Idempotent with ``end_call`` / timer via
    ``CallEndCoordinator.try_end``. Returns a sync ``cancel()`` for disconnect cleanup.
    """
    pending: dict[str, asyncio.Task[None] | None] = {"task": None}
    normed_markers = tuple(
        _normalize_for_goodbye_match(m) for m in markers if (m or "").strip()
    )

    def cancel() -> None:
        t = pending["task"]
        if t is not None and not t.done():
            t.cancel()
        pending["task"] = None

    if not enabled or not normed_markers:

        def noop() -> None:
            return None

        return noop

    async def _delayed_try_end() -> None:
        try:
            await asyncio.sleep(delay_s)
            await coordinator.try_end("goodbye_detected")
        except asyncio.CancelledError:
            raise

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def _on_user_turn_stopped(_aggregator, _strategy, _message):
        cancel()

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def _on_assistant_turn_stopped(_aggregator, message):
        cancel()
        if getattr(message, "interrupted", False):
            return
        raw = getattr(message, "content", None) or ""
        if not str(raw).strip():
            return
        blob = _normalize_for_goodbye_match(str(raw))
        for needle in normed_markers:
            if len(needle) >= 3 and needle in blob:
                pending["task"] = asyncio.create_task(_delayed_try_end())
                logger.debug("goodbye hangup: scheduled after {:.1f}s (matched marker)", delay_s)
                return

    return cancel


def make_end_call_handler(
    coordinator: CallEndCoordinator, *, log_prefix: str = "end_call"
):
    """Build a ``FunctionCallParams`` handler that ends the call once."""

    async def _handler(params: FunctionCallParams) -> None:
        await coordinator.try_end(log_prefix)
        await params.result_callback({"status": "ended"})

    return _handler

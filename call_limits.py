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
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import FunctionCallParams

from background_tasks import spawn_background_task


def parse_max_call_minutes(override: float | None = None) -> float:
    """Return minutes for the watchdog; ``0`` means disabled.

    Default ``10``. Invalid env values disable the watchdog (log warning).
    """
    if override is not None and override > 0:
        return float(override)
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
    """Coordinates a single, prompt hangup (end_call tool + timer + goodbye marker).

    The hangup is a hard ``task.cancel()`` (``CancelFrame``), not a queued
    ``EndFrame``. The Gemini Live service defers ``EndFrame`` until it sees a
    ``turn_complete`` from the model, which never arrives after the ``end_call``
    tool — leaving ~30s of dead air before the framework's fallback timeout.
    ``CancelFrame`` is processed immediately and still flushes the final
    assistant turn into the transcript.

    For tool/goodbye-driven ends, the cancel is delayed ``hangup_delay_s`` after
    the bot finishes its closing line (fed via ``note_bot_speaking``) so the
    goodbye plays out and the hangup feels natural rather than abrupt.
    """

    def __init__(self, task: PipelineTask, *, hangup_delay_s: float = 2.0) -> None:
        self._task = task
        self._lock = asyncio.Lock()
        self._ended = False
        self._hangup_delay_s = max(0.0, hangup_delay_s)
        self._watchdog_task: asyncio.Task[None] | None = None
        self._armed = False
        self._bot_speaking = False
        self._scheduled: asyncio.Task[None] | None = None
        self._arm_reason = "end_call"

    @property
    def hangup_delay_s(self) -> float:
        return self._hangup_delay_s

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

    # ── prompt-but-natural hangup after the bot's closing line ──────────────
    def arm_hangup(self, reason: str) -> None:
        """Request a hangup once the bot finishes its current/closing line."""
        self._armed = True
        self._arm_reason = reason
        if not self._bot_speaking:
            self._schedule_hangup()

    def note_bot_speaking(self, speaking: bool) -> None:
        """Feed bot speech boundaries (from the transport) to time the hangup."""
        self._bot_speaking = speaking
        if speaking:
            # Bot is talking (again) — wait for it to go quiet before hanging up.
            self._cancel_scheduled()
        elif self._armed:
            self._schedule_hangup()

    def note_user_speaking(self) -> None:
        """Caller re-engaged — abort any pending hangup; require a fresh end_call."""
        self._armed = False
        self._cancel_scheduled()

    def _schedule_hangup(self) -> None:
        if self._ended:
            return
        if self._scheduled is not None and not self._scheduled.done():
            return
        self._scheduled = spawn_background_task(self._delayed_end(), "call_end_delayed")
        logger.debug(
            "call end: hangup scheduled in {:.1f}s ({})",
            self._hangup_delay_s,
            self._arm_reason,
        )

    def _cancel_scheduled(self) -> None:
        s = self._scheduled
        if s is not None and not s.done():
            s.cancel()
        self._scheduled = None

    async def _delayed_end(self) -> None:
        try:
            if self._hangup_delay_s > 0:
                await asyncio.sleep(self._hangup_delay_s)
            await self.try_end(self._arm_reason)
        except asyncio.CancelledError:
            raise

    async def try_end(self, reason: str) -> bool:
        """Hang up now (idempotent). Hard-cancels the pipeline task."""
        async with self._lock:
            if self._ended:
                return False
            self._ended = True
        logger.info("call end: {}", reason)
        self._cancel_watchdog_if_pending()
        try:
            await self._task.cancel()
        except Exception as exc:
            async with self._lock:
                self._ended = False
            logger.warning("call end cancel failed: {}", exc)
            return False
        return True


@dataclass(frozen=True)
class ScheduledCallLimits:
    """Result of ``schedule_max_call_duration`` — use ``watchdog_task`` to cancel early."""

    coordinator: CallEndCoordinator
    watchdog_task: asyncio.Task[None] | None


def schedule_max_call_duration(
    task: PipelineTask, minutes: float, label: str, *, hangup_delay_s: float = 2.0
) -> ScheduledCallLimits:
    """Start optional background sleep then ``try_end(label)``; return coordinator + task."""
    coordinator = CallEndCoordinator(task, hangup_delay_s=hangup_delay_s)
    if minutes <= 0:
        logger.debug("max call duration watchdog disabled (minutes={})", minutes)
        return ScheduledCallLimits(coordinator=coordinator, watchdog_task=None)

    async def _watchdog() -> None:
        try:
            await asyncio.sleep(minutes * 60.0)
            await coordinator.try_end(label)
        except asyncio.CancelledError:
            raise

    watchdog_task = spawn_background_task(_watchdog(), "max_call_duration_watchdog")
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
                pending["task"] = spawn_background_task(_delayed_try_end(), "delayed_try_end")
                logger.debug("goodbye hangup: scheduled after {:.1f}s (matched marker)", delay_s)
                return

    return cancel


def make_end_call_handler(
    coordinator: CallEndCoordinator, *, log_prefix: str = "end_call"
):
    """Build a ``FunctionCallParams`` handler that hangs up after the closing line.

    The model calls ``end_call`` mid-/end-of its goodbye turn, so we *arm* the
    coordinator rather than cutting immediately; ``BotSpeechEndGate`` triggers the
    actual hangup a short, natural delay after the bot stops speaking.
    """

    async def _handler(params: FunctionCallParams) -> None:
        coordinator.arm_hangup(log_prefix)
        await params.result_callback({"status": "ending"})

    return _handler


class BotSpeechEndGate(FrameProcessor):
    """Pass-through sensor that feeds bot/user speech boundaries to a coordinator.

    Anchors the post-goodbye hangup on the transport's ``BotStoppedSpeakingFrame``
    (audio-accurate) instead of the LLM aggregator's turn-stopped event, which
    Gemini Live does not emit promptly after the ``end_call`` tool. Place this
    immediately after ``transport.output()`` in the pipeline.
    """

    def __init__(self) -> None:
        super().__init__()
        self._coordinator: CallEndCoordinator | None = None

    def bind(self, coordinator: CallEndCoordinator) -> None:
        self._coordinator = coordinator

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        c = self._coordinator
        if c is not None:
            if isinstance(frame, BotStartedSpeakingFrame):
                c.note_bot_speaking(True)
            elif isinstance(frame, BotStoppedSpeakingFrame):
                c.note_bot_speaking(False)
            elif isinstance(frame, UserStartedSpeakingFrame):
                c.note_user_speaking()

        await self.push_frame(frame, direction)

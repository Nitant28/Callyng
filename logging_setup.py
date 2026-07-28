"""Configure loguru once at process start (non-blocking stderr sink)."""

from __future__ import annotations

import os
import sys

from loguru import logger

_configured = False


def configure_logging() -> None:
    """Replace loguru's default sink with a non-blocking, non-diagnosing one.

    Must run before other project modules emit logs. ``enqueue=True`` hands
    writes to a background thread so a full Docker/journald pipe cannot stall
    the asyncio event loop that drives live audio.
    """
    global _configured
    if _configured:
        return

    level = (os.getenv("LOG_LEVEL") or "INFO").strip().upper() or "INFO"
    serialize = (os.getenv("LOG_FORMAT") or "").strip().lower() == "json"

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        serialize=serialize,
    )
    _configured = True

"""Plivo hangup webhook: record metadata and schedule callee hangup callbacks."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import PlainTextResponse
from loguru import logger

from db import postgres as pg_db


async def _parse_plivo_payload(request: Request) -> dict[str, Any]:
    """Merge query string and form body (Plivo may use GET or POST)."""
    out: dict[str, Any] = dict(request.query_params)
    try:
        form = await request.form()
        for key, value in form.items():
            if key not in out:
                out[key] = value
    except Exception:
        pass
    return out


async def handle_plivo_hangup(request: Request) -> PlainTextResponse:
    """Acknowledge Plivo hangup; idempotent on CallUUID / session_call_id."""
    pool = getattr(request.app.state, "pool", None)
    payload = await _parse_plivo_payload(request)
    call_uuid = str(
        payload.get("CallUUID") or payload.get("call_uuid") or ""
    ).strip()
    session_call_id = str(
        payload.get("session_call_id")
        or request.query_params.get("session_call_id")
        or ""
    ).strip()

    hangup_source = str(payload.get("HangupSource") or "").strip()
    logger.info(
        "plivo-hangup CallUUID={} session_call_id={} HangupSource={} CallStatus={}",
        call_uuid or "?",
        session_call_id or "?",
        hangup_source or "?",
        payload.get("CallStatus"),
    )

    if pool is None:
        return PlainTextResponse("OK", status_code=200)

    call_log: dict | None = None
    if session_call_id:
        call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if call_log is None and call_uuid:
        call_log = await pg_db.get_call_log_by_call_sid(pool, call_uuid)
        if call_log and not session_call_id:
            session_call_id = str(call_log.get("session_call_id") or "")

    if call_log is None:
        logger.warning(
            "plivo-hangup: no call_log for CallUUID={} session_call_id={}",
            call_uuid,
            session_call_id,
        )
        return PlainTextResponse("OK", status_code=200)

    call_log = await pg_db.record_plivo_hangup(
        pool,
        session_call_id=session_call_id or str(call_log.get("session_call_id") or ""),
        call_uuid=call_uuid or None,
        payload=payload,
    )
    if call_log:
        applied = await pg_db.apply_callee_hangup_callback(pool, call_log, payload)
        if applied:
            logger.info(
                "plivo-hangup callback_scheduled session_call_id={}",
                call_log.get("session_call_id"),
            )

    return PlainTextResponse("OK", status_code=200)

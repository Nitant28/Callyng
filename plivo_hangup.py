"""Plivo hangup webhook: record metadata and schedule callee hangup callbacks."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import PlainTextResponse
from loguru import logger

from background_tasks import spawn_background_task
from db import postgres as pg_db


def _is_intentional_api_hangup(hangup_source: str) -> bool:
    """True when our stack hung up (goodbye marker / end_call), not callee drop."""
    s = hangup_source.strip().lower().replace("_", " ")
    return s in ("api", "api request")


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
        hangup_source = payload.get("HangupSource") or payload.get("hangup_source") or ""
        hangup_source = str(hangup_source).strip().lower()
        call_status = str(payload.get("CallStatus") or "").strip().lower()
        
        unanswered_statuses = ("busy", "no-answer", "cancel", "reject", "failed")
        is_unanswered = call_status in unanswered_statuses
        
        if is_unanswered:
            from call_outcomes import outcome_from_plivo_status
            base_out = outcome_from_plivo_status(call_status)
            delay = 120
            if call_log.get("campaign_id") and call_log.get("client_id"):
                camp = await pg_db.get_campaign(pool, call_log["campaign_id"], call_log["client_id"])
                if camp and camp.get("retry_delay_minutes") is not None:
                    delay = int(camp["retry_delay_minutes"])
            settled = await pg_db.settle_unanswered_call(
                pool,
                call_log,
                retry_delay_minutes=delay,
                base_outcome=base_out,
                charge_setup=True,
            )
            if settled:
                logger.info("plivo-hangup settled unanswered session={}", call_log.get("session_call_id"))
        else:
            applied = await pg_db.apply_callee_hangup_callback(pool, call_log, payload)
            if applied:
                logger.info(
                    "plivo-hangup callback_scheduled session_call_id={}",
                    call_log.get("session_call_id"),
                )
            sid = str(call_log.get("session_call_id") or session_call_id or "")
            normalized_source = pg_db._normalize_hangup_source(payload)
            api_hangup = _is_intentional_api_hangup(normalized_source)
            if sid and call_log.get("in_progress") and not api_hangup:

                async def _hangup_recover() -> None:
                    try:
                        cleared = await pg_db.mark_call_log_not_in_progress(
                            pool, sid
                        )
                        if cleared:
                            from post_call_processor import recover_abandoned_session

                            await recover_abandoned_session(pool, sid)
                    except Exception as exc:
                        logger.error("plivo-hangup recovery failed session={}: {}", sid, exc)

                spawn_background_task(_hangup_recover(), "plivo_hangup_recover")
            elif sid and call_log.get("in_progress") and api_hangup:
                logger.debug(
                    "plivo-hangup skip recover: API-initiated hangup session={}",
                    sid,
                )

    return PlainTextResponse("OK", status_code=200)

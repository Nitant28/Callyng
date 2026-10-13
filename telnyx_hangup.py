"""Telnyx webhook handler: processes call lifecycle events, records metadata, and triggers post-call workflows."""

from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from background_tasks import spawn_background_task
from call_outcomes import outcome_from_telephony_status
from db import postgres as pg_db
from telephony import (
    public_telephony_base_url,
    start_telnyx_stream,
    verify_telnyx_webhook_signature,
)

_active_streams: set[str] = set()


def _is_intentional_api_hangup(hangup_source: str) -> bool:
    """True when our stack hung up (goodbye marker / end_call), not callee drop."""
    s = hangup_source.strip().lower().replace("_", " ")
    return s in ("api", "api request", "system", "bot")


async def _parse_telnyx_payload(request: Request) -> tuple[dict[str, Any], bytes]:
    """Parse Telnyx JSON webhook payload or form fallback."""
    raw_body = await request.body()
    payload: dict[str, Any] = dict(request.query_params)
    if raw_body:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                # If wrapped in { "data": { ... } }
                payload.update(parsed)
        except Exception:
            try:
                form = await request.form()
                for key, value in form.items():
                    if key not in payload:
                        payload[key] = value
            except Exception:
                pass
    return payload, raw_body


async def handle_telnyx_webhook(request: Request) -> Any:
    """Handle inbound Telnyx Call Control / TeXML webhook events."""
    pool = getattr(request.app.state, "pool", None)
    
    # 1. Verify webhook signature if present
    signature = request.headers.get("telnyx-signature-ed25519") or request.headers.get("Telnyx-Signature-Ed25519") or ""
    timestamp = request.headers.get("telnyx-timestamp") or request.headers.get("Telnyx-Timestamp") or ""
    payload, raw_bytes = await _parse_telnyx_payload(request)
    
    if signature and timestamp:
        if not verify_telnyx_webhook_signature(raw_bytes, signature, timestamp):
            logger.warning("Telnyx webhook signature verification rejected")
            return PlainTextResponse("Invalid signature", status_code=401)

    data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload
    event_type = str(data.get("event_type") or payload.get("event_type") or payload.get("CallStatus") or "").strip()
    event_payload = data.get("payload", {}) if isinstance(data.get("payload"), dict) else data

    call_control_id = str(
        event_payload.get("call_control_id")
        or event_payload.get("call_leg_id")
        or payload.get("CallUUID")
        or payload.get("call_uuid")
        or ""
    ).strip()

    # Client state may have our encoded session_call_id
    client_state_raw = event_payload.get("client_state") or payload.get("client_state") or ""
    session_call_id = ""
    if client_state_raw:
        try:
            decoded = base64.b64decode(client_state_raw).decode("utf-8")
            session_call_id = decoded.strip()
        except Exception:
            session_call_id = str(client_state_raw).strip()

    if not session_call_id:
        session_call_id = str(
            request.query_params.get("session_call_id")
            or payload.get("session_call_id")
            or ""
        ).strip()

    hangup_cause = str(
        event_payload.get("hangup_cause")
        or event_payload.get("HangupSource")
        or event_payload.get("cause")
        or ""
    ).strip()
    
    hangup_source = str(
        event_payload.get("hangup_source")
        or event_payload.get("HangupSource")
        or "callee"
    ).strip()

    call_status = str(
        event_payload.get("call_status")
        or event_payload.get("status")
        or payload.get("CallStatus")
        or hangup_cause
        or event_type
    ).strip().lower()

    logger.info(
        "Telnyx webhook event={} call_control_id={} session_call_id={} status={} cause={}",
        event_type or "?",
        call_control_id or "?",
        session_call_id or "?",
        call_status or "?",
        hangup_cause or "?",
    )

    # Handle call.answered event: initiate bidirectional WebSocket audio stream
    if "answered" in event_type.lower() or call_status == "answered":
        logger.info(
            "Telnyx call answered: call_control_id={} session_call_id={}. Initiating audio stream...",
            call_control_id,
            session_call_id,
        )
        session = getattr(request.app.state, "session", None)
        if session and call_control_id:
            host = request.headers.get("host", "localhost")
            ws_base = public_telephony_base_url(host).replace("https://", "wss://").replace("http://", "ws://")
            ws_url = f"{ws_base}/ws"
            params: list[str] = []
            if session_call_id:
                params.append(f"call_id={urllib.parse.quote(session_call_id)}")
            if client_state_raw:
                params.append(f"body={urllib.parse.quote(client_state_raw)}")
            elif request.query_params.get("body_data"):
                params.append(f"body={urllib.parse.quote(base64.b64encode(request.query_params.get('body_data').encode()).decode())}")
            if params:
                ws_url += "?" + "&".join(params)

            if call_control_id not in _active_streams:
                _active_streams.add(call_control_id)
                spawn_background_task(
                    start_telnyx_stream(session, call_control_id, ws_url),
                    name=f"stream_{call_control_id}",
                )

    if pool is None:
        return PlainTextResponse("OK", status_code=200)

    call_log: dict | None = None
    if session_call_id:
        call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if call_log is None and call_control_id:
        call_log = await pg_db.get_call_log_by_call_sid(pool, call_control_id)
        if call_log and not session_call_id:
            session_call_id = str(call_log.get("session_call_id") or "")

    if call_log is None:
        logger.info(
            "Telnyx webhook: unlogged session_call_id={} call_control_id={} event={}",
            session_call_id,
            call_control_id,
            event_type,
        )
        return PlainTextResponse("OK", status_code=200)

    # Record webhook payload into database (idempotent)
    combined_payload = {
        "provider": "telnyx",
        "event_type": event_type,
        "hangup_source": hangup_source,
        "hangup_cause": hangup_cause,
        "call_status": call_status,
        "call_control_id": call_control_id,
        "session_call_id": session_call_id,
        "raw": event_payload,
    }

    call_log = await pg_db.record_telnyx_hangup(
        pool,
        session_call_id=session_call_id or str(call_log.get("session_call_id") or ""),
        call_sid=call_control_id or None,
        payload=combined_payload,
    )

    if call_log:
        # Determine if call ended without answering
        unanswered_causes = (
            "busy",
            "user_busy",
            "no_answer",
            "no-answer",
            "timeout",
            "call_rejected",
            "rejected",
            "reject",
            "cancel",
            "originator_cancel",
            "failed",
            "carrier_failed",
            "subscriber_absent",
            "unallocated_number",
        )
        is_hangup_event = "hangup" in event_type or bool(hangup_cause) or event_type in ("call.hangup", "completed")
        if is_hangup_event:
            _active_streams.discard(call_control_id)
        is_unanswered = any(u in call_status or u in hangup_cause.lower() for u in unanswered_causes)

        if is_hangup_event and is_unanswered:
            base_out = outcome_from_telephony_status(hangup_cause or call_status)
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
                charge_setup=False,
            )
            if settled:
                logger.info(
                    "Telnyx webhook settled unanswered session={} outcome={}",
                    call_log.get("session_call_id"),
                    base_out,
                )
        elif is_hangup_event:
            # Answered call completed
            skip_callback = False
            sid = str(call_log.get("session_call_id") or session_call_id or "")
            try:
                from call_transfer import has_transfer_flag
                skip_callback = bool(sid) and await has_transfer_flag(sid)
            except Exception:
                skip_callback = False

            if not skip_callback:
                call_data = pg_db.parse_call_data(call_log.get("call_data"))
                skip_callback = bool(call_data.get("transferred"))

            if skip_callback:
                logger.info(
                    "Telnyx webhook skip callback: transferred session={}",
                    call_log.get("session_call_id"),
                )
            else:
                applied = await pg_db.apply_callee_hangup_callback(pool, call_log, combined_payload)
                if applied:
                    logger.info(
                        "Telnyx webhook callback scheduled session_call_id={}",
                        call_log.get("session_call_id"),
                    )

            normalized_source = pg_db._normalize_hangup_source(combined_payload)
            api_hangup = _is_intentional_api_hangup(normalized_source)
            if sid and call_log.get("in_progress") and not api_hangup:
                async def _hangup_recover() -> None:
                    try:
                        cleared = await pg_db.mark_call_log_not_in_progress(pool, sid)
                        if cleared:
                            from post_call_processor import recover_abandoned_session
                            await recover_abandoned_session(pool, sid)
                    except Exception as exc:
                        logger.error("Telnyx webhook recovery failed session={}: {}", sid, exc)

                spawn_background_task(_hangup_recover(), "telnyx_hangup_recover")

    return PlainTextResponse("OK", status_code=200)


# Backward-compatible handler alias
async def handle_plivo_hangup(request: Request) -> PlainTextResponse:
    """Wrapper calling canonical handle_telnyx_webhook."""
    resp = await handle_telnyx_webhook(request)
    if isinstance(resp, PlainTextResponse):
        return resp
    return PlainTextResponse("OK", status_code=200)

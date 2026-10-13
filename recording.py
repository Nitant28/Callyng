"""Call recording management for Telnyx telephony and media storage."""

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

import aiohttp
import boto3
from botocore.config import Config
from fastapi import Request
from fastapi.responses import PlainTextResponse
from loguru import logger

import db.postgres as pg_db
from telephony import _telnyx_credentials, public_telephony_base_url


# ---------------------------------------------------------------------------
# R2 / S3 helpers (kept for legacy keys & cloud storage)
# ---------------------------------------------------------------------------

def _r2_client():
    account_id = (os.environ.get("R2_ACCOUNT_ID") or "").strip().rstrip("/")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_presigned_url(object_key: str, expires_in: int = 3600) -> str:
    client = _r2_client()
    bucket_name = os.environ.get("R2_BUCKET_NAME")
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expires_in,
    )


# ---------------------------------------------------------------------------
# Recording URL resolution helpers
# ---------------------------------------------------------------------------

def resolve_recording_url(recording_key: str, expires_in: int = 3600) -> str:
    """Given a stored recording_key, return a playable URL.

    Handles formats:
    - telnyx:<full-url>  → returns the Telnyx media URL
    - plivo:<full-url>   → legacy support
    - recordings/...     → legacy R2 key, generates presigned URL
    - http:// or https://→ direct URL
    """
    if not recording_key:
        return ""
    if recording_key.startswith("telnyx:"):
        return recording_key[len("telnyx:"):]
    if recording_key.startswith("plivo:"):
        return recording_key[len("plivo:"):]
    if recording_key.startswith(("http://", "https://")):
        return recording_key
    # Legacy R2 key
    try:
        return generate_presigned_url(recording_key, expires_in)
    except Exception as exc:
        logger.warning("Failed to generate presigned URL for recording key {}: {}", recording_key, exc)
        return ""


# Compatibility alias
generate_plivo_recording_url = resolve_recording_url


# ---------------------------------------------------------------------------
# Telnyx Record API — start recording on an active call
# ---------------------------------------------------------------------------

async def start_telnyx_recording(
    session: aiohttp.ClientSession,
    call_control_id: str,
    session_call_id: str,
    *,
    host: str = "",
) -> bool:
    """Fire Telnyx Call Control Record Start API."""
    api_key, _, _, _ = _telnyx_credentials()
    if not api_key or not call_control_id:
        return False

    url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/record_start"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "format": "mp3",
        "channels": "dual",
        "play_beep": False,
    }
    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in (200, 201, 202):
                logger.info(
                    "Telnyx recording started for call_control_id={} session_call_id={}",
                    call_control_id,
                    session_call_id,
                )
                return True
            body = await resp.text()
            logger.warning("Telnyx Record API returned ({}) for {}: {}", resp.status, call_control_id, body)
            return False
    except Exception as exc:
        logger.warning("Telnyx Record API error for {}: {}", call_control_id, exc)
        return False


# Compatibility alias
start_plivo_recording = start_telnyx_recording


# ---------------------------------------------------------------------------
# Telnyx recording webhook handler
# ---------------------------------------------------------------------------

async def handle_telnyx_recording(request: Request) -> PlainTextResponse:
    """Webhook: processes Telnyx recording saved events."""
    pool = getattr(request.app.state, "pool", None)
    raw_body = await request.body()
    payload: dict[str, Any] = dict(request.query_params)
    if raw_body:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                payload.update(parsed)
        except Exception:
            pass

    data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload
    event_payload = data.get("payload", {}) if isinstance(data.get("payload"), dict) else data

    call_control_id = str(
        event_payload.get("call_control_id")
        or event_payload.get("call_leg_id")
        or payload.get("CallUUID")
        or payload.get("call_uuid")
        or ""
    ).strip()

    record_url = str(
        event_payload.get("recording_urls", {}).get("mp3")
        or event_payload.get("public_recording_urls", {}).get("mp3")
        or event_payload.get("recording_url")
        or payload.get("RecordUrl")
        or payload.get("record_url")
        or ""
    ).strip()

    session_call_id = str(
        request.query_params.get("session_call_id")
        or payload.get("session_call_id")
        or ""
    ).strip()

    if not pool:
        return PlainTextResponse("OK", status_code=200)

    call_log = None
    if session_call_id:
        call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if not call_log and call_control_id:
        call_log = await pg_db.get_call_log_by_call_sid(pool, call_control_id)

    if not call_log:
        logger.warning(
            "telnyx-recording: no call_log for call_control_id={} session_call_id={}",
            call_control_id,
            session_call_id,
        )
        return PlainTextResponse("OK", status_code=200)

    if not record_url:
        logger.warning("telnyx-recording: empty record_url for session_call_id={}", session_call_id)
        return PlainTextResponse("OK", status_code=200)

    scid = str(call_log["session_call_id"])
    stored_key = f"telnyx:{record_url}"

    try:
        await pg_db.update_call_log_recording_url(pool, scid, stored_key)
        logger.info("Recording saved: session_call_id={} telnyx_url={}", scid, record_url)
    except Exception as exc:
        logger.error("Failed to save recording URL for session={}: {}", scid, exc)

    return PlainTextResponse("OK", status_code=200)


# Compatibility alias
handle_plivo_recording = handle_telnyx_recording

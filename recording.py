import json
import os
import urllib.parse
from loguru import logger
import aiohttp
from fastapi import Request
from fastapi.responses import PlainTextResponse
import boto3
from botocore.config import Config

from plivo_hangup import _parse_plivo_payload
from telephony import public_telephony_base_url, _plivo_auth
import db.postgres as pg_db


# ---------------------------------------------------------------------------
# R2 helpers (kept for legacy keys & optional future use)
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
# Plivo recording URL helpers
# ---------------------------------------------------------------------------

def generate_plivo_recording_url(recording_url: str, expires_in: int = 3600) -> str:
    """Return a Plivo recording URL with Basic Auth embedded for direct playback.

    Plivo media URLs require authentication. We embed the credentials directly
    so the browser / frontend can fetch the MP3 without an extra proxy hop.
    """
    auth_id, auth_token = _plivo_auth()
    parsed = urllib.parse.urlparse(recording_url)
    authed = parsed._replace(
        netloc=f"{auth_id}:{auth_token}@{parsed.hostname}"
        + (f":{parsed.port}" if parsed.port else "")
    )
    return urllib.parse.urlunparse(authed)


def resolve_recording_url(recording_key: str, expires_in: int = 3600) -> str:
    """Given a stored recording_key, return a playable URL.

    Handles three formats:
    - plivo:<full-plivo-url>  → authenticates with Plivo creds
    - recordings/...          → legacy R2 key, generates presigned URL
    - local:<filename>        → not handled here (caller should serve file)
    """
    if recording_key.startswith("plivo:"):
        plivo_url = recording_key[len("plivo:"):]
        return generate_plivo_recording_url(plivo_url, expires_in)
    # Legacy R2 key
    return generate_presigned_url(recording_key, expires_in)


# ---------------------------------------------------------------------------
# Plivo Record API — start recording on an active call
# ---------------------------------------------------------------------------

async def start_plivo_recording(
    session: aiohttp.ClientSession,
    call_uuid: str,
    session_call_id: str,
    *,
    host: str = "",
) -> bool:
    """Fire Plivo Record API. Returns True if accepted (200/202)."""
    auth_id, auth_token = _plivo_auth()
    url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/{call_uuid}/Record/"
    base = public_telephony_base_url(host)
    callback = f"{base}/plivo-recording?session_call_id={urllib.parse.quote(session_call_id)}"
    data = {
        "time_limit": 3600,
        "file_format": "mp3",
        "callback_url": callback,
        "callback_method": "POST",
    }
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    async with session.post(url, json=data, auth=auth) as resp:
        if resp.status in (200, 202):
            logger.info("Recording started for call_uuid={} session_call_id={}", call_uuid, session_call_id)
            return True
        body = await resp.text()
        logger.error("Record API failed ({}) for {}: {}", resp.status, call_uuid, body)
        return False


# ---------------------------------------------------------------------------
# Plivo recording webhook — called when recording is ready
# ---------------------------------------------------------------------------

async def handle_plivo_recording(request: Request) -> PlainTextResponse:
    """Webhook: Plivo POSTs here when recording file is ready.

    Instead of downloading and re-uploading, we store the Plivo-hosted
    recording URL directly. Plivo retains recordings for 90 days.
    """
    pool = getattr(request.app.state, "pool", None)
    payload = await _parse_plivo_payload(request)

    # Plivo's Record API delivers its callback as a single form field "response"
    # containing a JSON object with snake_case keys (record_url, call_uuid,
    # recording_duration). Other Plivo webhooks send flat top-level params
    # (RecordUrl, CallUUID, ...). Merge the JSON envelope so both formats work.
    record_data = dict(payload)
    raw_response = payload.get("response")
    if raw_response:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                record_data.update(parsed)
        except (ValueError, TypeError):
            pass

    session_call_id = (
        record_data.get("session_call_id")
        or request.query_params.get("session_call_id")
        or ""
    )
    call_uuid = record_data.get("CallUUID") or record_data.get("call_uuid") or ""
    record_url = record_data.get("RecordUrl") or record_data.get("record_url") or ""
    recording_duration = (
        record_data.get("RecordingDuration")
        or record_data.get("recording_duration")
        or "0"
    )

    # 1. Look up call_log
    call_log = None
    if session_call_id and pool:
        call_log = await pg_db.get_call_log_by_session(pool, session_call_id)
    if not call_log and call_uuid and pool:
        call_log = await pg_db.get_call_log_by_call_sid(pool, call_uuid)

    if not call_log:
        logger.warning("plivo-recording: no call_log for CallUUID={} session_call_id={}",
                       call_uuid, session_call_id)
        return PlainTextResponse("OK", status_code=200)

    if not record_url:
        logger.warning("plivo-recording: empty RecordUrl for session_call_id={}", session_call_id)
        return PlainTextResponse("OK", status_code=200)

    scid = str(call_log["session_call_id"])

    # 2. Store the Plivo recording URL directly (prefixed with "plivo:")
    stored_key = f"plivo:{record_url}"

    try:
        await pg_db.update_call_log_recording_url(pool, scid, stored_key)
    except Exception as exc:
        logger.error("Failed to save recording URL for session={}: {}", scid, exc)
        return PlainTextResponse("OK", status_code=200)

    logger.info("Recording saved: session_call_id={} plivo_url={} duration={}s",
                scid, record_url, recording_duration)
    return PlainTextResponse("OK", status_code=200)



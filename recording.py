import asyncio
import os
import urllib.parse
from pathlib import Path
from loguru import logger
import aiohttp
from fastapi import Request
from fastapi.responses import PlainTextResponse
import boto3
from botocore.config import Config

from plivo_hangup import _parse_plivo_payload
from telephony import public_telephony_base_url, _plivo_auth
import db.postgres as pg_db


def _r2_client():
    account_id = os.environ.get("R2_ACCOUNT_ID")
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


def upload_recording(audio_bytes: bytes, object_key: str) -> None:
    client = _r2_client()
    bucket_name = os.environ.get("R2_BUCKET_NAME")
    client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
    )


def generate_presigned_url(object_key: str, expires_in: int = 3600) -> str:
    client = _r2_client()
    bucket_name = os.environ.get("R2_BUCKET_NAME")
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expires_in,
    )


async def start_plivo_recording(
    session: aiohttp.ClientSession,
    call_uuid: str,
    session_call_id: str,
    *,
    host: str = "",
) -> bool:
    """Fire Plivo Record API. Returns True if accepted (202)."""
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
        if resp.status == 202:
            logger.info("Recording started for call_uuid={} session_call_id={}", call_uuid, session_call_id)
            return True
        body = await resp.text()
        logger.error("Record API failed ({}) for {}: {}", resp.status, call_uuid, body)
        return False


async def handle_plivo_recording(request: Request) -> PlainTextResponse:
    """Webhook: Plivo POSTs here when recording file is ready."""
    pool = getattr(request.app.state, "pool", None)
    payload = await _parse_plivo_payload(request)

    session_call_id = (
        payload.get("session_call_id")
        or request.query_params.get("session_call_id")
        or ""
    )
    call_uuid = payload.get("CallUUID") or payload.get("call_uuid") or ""
    record_url = payload.get("RecordUrl") or ""
    recording_id = payload.get("RecordingID") or ""
    recording_duration = payload.get("RecordingDuration") or "0"

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

    # 2. Download from Plivo
    audio_bytes = await _download_recording(request.app.state.session, record_url)
    if not audio_bytes:
        return PlainTextResponse("OK", status_code=200)

    # 3. Upload to storage (R2 or local)
    client_id = str(call_log["client_id"])
    scid = str(call_log["session_call_id"])
    object_key = f"recordings/{client_id}/{scid}.mp3"

    storage = os.getenv("RECORDING_STORAGE", "r2").lower()
    if storage == "local":
        _save_local(audio_bytes, scid)
        stored_key = f"local:{scid}.mp3"
    else:
        upload_recording(audio_bytes, object_key)
        stored_key = object_key

    # 4. Update call_logs.recording_url
    await pg_db.update_call_log_recording_url(pool, scid, stored_key)

    # 5. (Optional) Delete from Plivo to free their storage
    # await _delete_plivo_recording(session, recording_id)

    logger.info("Recording stored: session_call_id={} key={} duration={}s",
                scid, stored_key, recording_duration)
    return PlainTextResponse("OK", status_code=200)


async def _download_recording(
    session: aiohttp.ClientSession,
    record_url: str,
) -> bytes | None:
    """Download recording from Plivo with Basic Auth."""
    if not record_url:
        return None
    auth_id, auth_token = _plivo_auth()
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    try:
        async with session.get(record_url, auth=auth) as resp:
            if resp.status == 200:
                return await resp.read()
            logger.error("Failed to download recording from {}: {}", record_url, resp.status)
    except Exception as exc:
        logger.error("Recording download error: {}", exc)
    return None


def _save_local(audio_bytes: bytes, session_call_id: str) -> None:
    """Save recording to local filesystem (dev mode)."""
    path = Path("./data/recordings")
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{session_call_id}.mp3").write_bytes(audio_bytes)

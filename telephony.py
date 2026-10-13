"""Canonical Telnyx Telephony Service for AkashVani & AI Receptionist.

Handles outbound call origination, call control, webhooks, signature verification,
TeXML streaming XML generation, and account balance queries.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import aiohttp
from loguru import logger


def _telnyx_credentials() -> tuple[str, str, str, str]:
    """Return (api_key, connection_id, phone_number, public_key) from env."""
    api_key = (os.getenv("TELNYX_API_KEY") or "").strip()
    connection_id = (os.getenv("TELNYX_CONNECTION_ID") or "").strip()
    phone_number = (os.getenv("TELNYX_PHONE_NUMBER") or "").strip()
    public_key = (os.getenv("TELNYX_PUBLIC_KEY") or "").strip()
    return api_key, connection_id, phone_number, public_key


def public_telephony_base_url(host: str = "") -> str:
    """Public base URL reachable by Telnyx webhooks (ngrok or production domain)."""
    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    if ngrok:
        return ngrok
    if host and not host.startswith(("localhost", "127.0.0.1")):
        return f"https://{host.split(':')[0]}"
    return "http://localhost:7860"


def normalize_e164(phone: str) -> str:
    """Normalize a phone number to standard E.164 with leading +."""
    compact = re.sub(r"[\s().-]", "", (phone or "").strip())
    if not compact:
        return ""
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if not compact.startswith("+"):
        if compact.startswith("91") and len(compact) == 12:
            compact = "+" + compact
        elif len(compact) == 10 and compact[0] in "6789":
            compact = "+91" + compact
        elif compact.startswith("1") and len(compact) == 11:
            compact = "+" + compact
        else:
            compact = "+" + compact
    return compact


# Provider-neutral alias
normalize_phone_number = normalize_e164
normalize_plivo_number = normalize_e164  # backward compatibility alias


def build_hangup_url(session_call_id: str, *, host: str = "") -> str:
    """Telnyx webhook callback URL for hangup and status events."""
    base = public_telephony_base_url(host)
    q = urllib.parse.quote(session_call_id or "")
    return f"{base}/telnyx-webhook?session_call_id={q}"


def build_transfer_xml_url(session_call_id: str, *, host: str = "") -> str:
    """Telnyx transfer webhook URL."""
    base = public_telephony_base_url(host)
    q = urllib.parse.quote(session_call_id or "")
    return f"{base}/telnyx-webhook?action=transfer&session_call_id={q}"


async def fetch_telnyx_balance(session: aiohttp.ClientSession) -> Decimal:
    """Query Telnyx Account Balance API (GET /v2/balance) and return available balance in USD."""
    api_key, _, _, _ = _telnyx_credentials()
    if not api_key:
        raise RuntimeError("TELNYX_API_KEY must be set to fetch balance")

    url = "https://api.telnyx.com/v2/balance"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"Telnyx balance API error ({resp.status}): {body}")
        data = await resp.json()
    
    # Payload format: { "data": { "balance": "100.00", "available_credit": "100.00", "currency": "USD" } }
    raw = data.get("data", {}).get("balance") or data.get("data", {}).get("available_credit") or "0.00"
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError) as exc:
        raise RuntimeError(f"Invalid Telnyx balance: {raw!r}") from exc


# Compatibility alias for legacy balance callers
fetch_plivo_cash_credits = fetch_telnyx_balance


def telnyx_error_is_insufficient_balance(status: int, error_body: str) -> bool:
    """Check if Telnyx returned 402 or an insufficient funds / credit error."""
    if status in (402, 403):
        return True
    low = (error_body or "").lower()
    markers = (
        "insufficient",
        "balance",
        "funds",
        "credit",
        "payment required",
        "quota",
        "unpaid",
    )
    return any(m in low for m in markers)


# Compatibility alias
plivo_error_is_insufficient_balance = telnyx_error_is_insufficient_balance


async def make_telnyx_call(
    session: aiohttp.ClientSession,
    to_number: str,
    from_number: str | None = None,
    answer_url: str | None = None,
    *,
    hangup_url: str | None = None,
    webhook_url: str | None = None,
    client_state: str | None = None,
    custom_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Initiate an outbound call via Telnyx Call Control API (v2/calls)."""
    api_key, connection_id, default_from, _ = _telnyx_credentials()
    if not api_key:
        raise RuntimeError("TELNYX_API_KEY must be set in environment")

    caller = normalize_e164(from_number or default_from)
    dest = normalize_e164(to_number)

    if not dest:
        raise ValueError("Destination phone number (to_number) cannot be empty")

    url = "https://api.telnyx.com/v2/calls"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload: dict[str, Any] = {
        "to": dest,
        "from": caller,
    }

    if connection_id:
        payload["connection_id"] = connection_id
    chosen_webhook = webhook_url or hangup_url or answer_url
    if chosen_webhook:
        payload["webhook_url"] = chosen_webhook
    if client_state:
        # Telnyx client_state must be base64 encoded
        payload["client_state"] = base64.b64encode(client_state.encode("utf-8")).decode("utf-8")
    if custom_headers:
        payload["custom_headers"] = custom_headers

    logger.info(
        "Initiating Telnyx outbound call to {} from {} (connection_id={})",
        dest,
        caller,
        connection_id,
    )

    async with session.post(
        url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        body = await resp.text()
        if resp.status not in (200, 201, 202):
            if telnyx_error_is_insufficient_balance(resp.status, body):
                logger.error("Telnyx dial rejected — account balance exhausted (402/403)")
            raise RuntimeError(f"Telnyx dial error ({resp.status}): {body}")

        try:
            data = json.loads(body)
            # Normalize returned call_control_id / call_leg_id
            call_data = data.get("data", {})
            call_control_id = call_data.get("call_control_id") or call_data.get("call_leg_id") or call_data.get("id") or "unknown"
            return {
                "request_uuid": call_control_id,
                "call_control_id": call_control_id,
                "call_leg_id": call_data.get("call_leg_id"),
                "call_session_id": call_data.get("call_session_id"),
                "status": "queued",
                "raw": data,
            }
        except Exception:
            return {"status": resp.status, "raw": body}


# Compatibility alias
make_plivo_call = make_telnyx_call


async def hangup_telnyx_call(
    session: aiohttp.ClientSession,
    call_control_id: str,
) -> dict[str, Any]:
    """Hang up an active Telnyx Call Control call."""
    api_key, _, _, _ = _telnyx_credentials()
    if not api_key or not call_control_id:
        return {"status": "skipped"}

    url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/hangup"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with session.post(url, json={}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        body = await resp.text()
        logger.info("Telnyx call hangup call_control_id={} status={}", call_control_id, resp.status)
        return {"status": resp.status, "body": body}


async def transfer_telnyx_call(
    session: aiohttp.ClientSession,
    call_control_id: str,
    to_number: str,
    *,
    aleg_url: str | None = None,
) -> dict[str, Any]:
    """Transfer an active Telnyx call to another destination phone number."""
    api_key, _, default_from, _ = _telnyx_credentials()
    if not api_key or not call_control_id:
        raise RuntimeError("Telnyx transfer requires TELNYX_API_KEY and call_control_id")

    dest = normalize_e164(to_number)
    url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transfer"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "to": dest,
    }
    if aleg_url:
        payload["webhook_url"] = aleg_url

    logger.info("Telnyx transfer call_control_id={} to={}", call_control_id, dest)
    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        body = await resp.text()
        if resp.status not in (200, 201, 202):
            raise RuntimeError(f"Telnyx transfer error ({resp.status}): {body}")
        try:
            return json.loads(body)
        except Exception:
            return {"status": resp.status, "body": body}


# Compatibility alias
transfer_plivo_call = transfer_telnyx_call


async def start_telnyx_stream(
    session: aiohttp.ClientSession,
    call_control_id: str,
    stream_url: str,
    *,
    stream_track: str = "both_tracks",
) -> dict[str, Any]:
    """Start bidirectional audio streaming via Telnyx Call Control API."""
    api_key, _, _, _ = _telnyx_credentials()
    if not api_key or not call_control_id:
        return {}
    url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/streaming_start"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "stream_url": stream_url,
        "stream_track": stream_track,
        "enable_dialogflow": False,
    }
    logger.info("Starting Telnyx stream for call_control_id={} to ws={}", call_control_id, stream_url)
    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        body = await resp.text()
        logger.info("Telnyx start stream call_control_id={} status={} body={}", call_control_id, resp.status, body)
        return {"status": resp.status, "body": body}


async def stop_telnyx_stream(
    session: aiohttp.ClientSession,
    call_control_id: str,
    stream_id: str | None = None,
) -> None:
    """Stop audio streaming on a Telnyx Call Control call."""
    api_key, _, _, _ = _telnyx_credentials()
    if not api_key or not call_control_id:
        return
    url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/streaming_stop"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with session.post(url, json={}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        logger.info("Telnyx stop stream call_control_id={} status={}", call_control_id, resp.status)


# Compatibility alias
stop_plivo_stream = stop_telnyx_stream


def build_texml_stream_xml(ws_url: str) -> str:
    """Generate Telnyx TeXML XML response establishing bidirectional WebSocket audio stream with Pipecat."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" bidirectionalMode="rtp" contentType="audio/x-mulaw;rate=8000" />
    </Connect>
</Response>"""


def verify_telnyx_webhook_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    public_key: str | None = None,
) -> bool:
    """Verify Telnyx webhook signature using Telnyx Public Key (Ed25519 signature)."""
    key = public_key or os.getenv("TELNYX_PUBLIC_KEY", "").strip()
    if not key:
        # If public key is not configured in dev, fallback log
        logger.warning("TELNYX_PUBLIC_KEY not configured; skipping signature check")
        return True

    try:
        from nacl.signing import VerifyKey
        from nacl.encoding import Base64Encoder

        signed_payload = f"{timestamp}|".encode("utf-8") + payload
        verify_key = VerifyKey(key.encode("utf-8"), encoder=Base64Encoder)
        verify_key.verify(signed_payload, base64.b64decode(signature))
        return True
    except Exception as exc:
        try:
            # Cryptography fallback if nacl is not present
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            raw_key = base64.b64decode(key)
            pub_key = Ed25519PublicKey.from_public_bytes(raw_key)
            signed_payload = f"{timestamp}|".encode("utf-8") + payload
            pub_key.verify(base64.b64decode(signature), signed_payload)
            return True
        except Exception as inner_exc:
            logger.warning("Telnyx webhook signature verification failed: {} / {}", exc, inner_exc)
            return False


def create_telnyx_serializer(call_data: Any) -> Any:
    """Safely build TelnyxFrameSerializer from CallData or dict according to Pipecat 1.7+ API."""
    from pipecat.serializers.telnyx import TelnyxFrameSerializer

    if isinstance(call_data, dict):
        stream_id = str(call_data.get("stream_id") or "")
        call_control_id = str(call_data.get("call_id") or "")
        outbound_encoding = str(call_data.get("outbound_encoding") or "PCMU")
    else:
        stream_id = str(getattr(call_data, "stream_id", "") or "")
        call_control_id = str(getattr(call_data, "call_id", "") or "")
        outbound_encoding = str(getattr(call_data, "outbound_encoding", "PCMU") or "PCMU")

    api_key = (os.getenv("TELNYX_API_KEY") or "").strip()
    can_auto_hangup = bool(api_key and call_control_id)
    params = TelnyxFrameSerializer.InputParams(auto_hang_up=can_auto_hangup)

    return TelnyxFrameSerializer(
        stream_id=stream_id,
        outbound_encoding=outbound_encoding,
        inbound_encoding=outbound_encoding,
        call_control_id=call_control_id or None,
        api_key=api_key or None,
        params=params,
    )


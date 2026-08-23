"""Plivo outbound call helper (shared by server and dialer)."""

from __future__ import annotations

import os
import urllib.parse
from decimal import Decimal, InvalidOperation

import aiohttp
from loguru import logger


def _plivo_auth() -> tuple[str, str]:
    auth_id = (os.getenv("PLIVO_AUTH_ID") or "").strip()
    auth_token = (os.getenv("PLIVO_AUTH_TOKEN") or "").strip()
    if not auth_id or not auth_token:
        raise RuntimeError("PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN must be set")
    return auth_id, auth_token


async def fetch_plivo_cash_credits(session: aiohttp.ClientSession) -> Decimal:
    """Return Plivo prepaid balance in USD (``cash_credits``)."""
    auth_id, auth_token = _plivo_auth()
    url = f"https://api.plivo.com/v1/Account/{auth_id}/"
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    async with session.get(url, auth=auth) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"Plivo account API error ({resp.status}): {body}")
        data = await resp.json()
    raw = data.get("cash_credits")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError) as exc:
        raise RuntimeError(f"Invalid Plivo cash_credits: {raw!r}") from exc


def plivo_error_is_insufficient_balance(status: int, error_body: str) -> bool:
    """True when Plivo rejected the dial due to no account funds."""
    if status == 402:
        return True
    low = (error_body or "").lower()
    markers = (
        "insufficient",
        "not enough",
        "low balance",
        "cash credit",
        "no funds",
        "out of funds",
        "balance is low",
    )
    return any(m in low for m in markers)


def public_telephony_base_url(host: str = "") -> str:
    """Public base URL Plivo can reach (ngrok or non-localhost host)."""
    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    if ngrok:
        return ngrok
    if host and not host.startswith(("localhost", "127.0.0.1")):
        return f"https://{host.split(':')[0]}"
    return "http://localhost:7860"


def build_hangup_url(session_call_id: str, *, host: str = "") -> str:
    """Hangup webhook URL with our session id for reliable call_log lookup."""
    base = public_telephony_base_url(host)
    q = urllib.parse.quote(session_call_id)
    return f"{base}/plivo-hangup?session_call_id={q}"


def build_transfer_xml_url(session_call_id: str, *, host: str = "") -> str:
    """HTTPS URL Plivo fetches for Dial XML (destination is looked up in Redis)."""
    base = public_telephony_base_url(host)
    q = urllib.parse.quote(session_call_id or "")
    return f"{base}/plivo-transfer-xml?session_call_id={q}"


async def transfer_plivo_call(
    session: aiohttp.ClientSession,
    call_uuid: str,
    to_number: str,
    *,
    aleg_url: str,
) -> dict:
    """Cold-transfer an in-progress Plivo call via aleg Dial XML."""
    auth_id, auth_token = _plivo_auth()
    uuid = (call_uuid or "").strip()
    if not uuid:
        raise RuntimeError("Plivo transfer requires call_uuid")
    # Transfer is POST on the Call resource itself — there is no /Transfer/ suffix.
    url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/{uuid}/"
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    payload = {
        "legs": "aleg",
        "aleg_url": aleg_url,
        "aleg_method": "POST",
    }
    timeout = aiohttp.ClientTimeout(total=20)
    logger.info("Plivo transfer uuid={} to={} aleg_url={}", uuid, to_number, aleg_url)
    async with session.post(url, json=payload, auth=auth, timeout=timeout) as resp:
        body = await resp.text()
        logger.info("Plivo transfer response status={} body={}", resp.status, body[:500])
        if resp.status not in (200, 202):
            raise RuntimeError(f"Plivo transfer error ({resp.status}): {body}")
        if resp.content_type and "json" in resp.content_type:
            try:
                return await resp.json()
            except Exception:
                pass
        return {"status": resp.status, "body": body}


async def stop_plivo_stream(
    session: aiohttp.ClientSession,
    call_uuid: str,
    stream_id: str,
) -> None:
    """Stop audio streaming so Transfer XML (Dial) can execute."""
    auth_id, auth_token = _plivo_auth()
    uuid = (call_uuid or "").strip()
    sid = (stream_id or "").strip()
    if not uuid or not sid:
        logger.warning("stop_plivo_stream skipped: missing call_uuid or stream_id")
        return
    url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/{uuid}/Stream/{sid}/"
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    timeout = aiohttp.ClientTimeout(total=10)
    async with session.delete(url, auth=auth, timeout=timeout) as resp:
        body = await resp.text()
        logger.info(
            "Plivo stop stream uuid={} stream={} status={} body={}",
            uuid,
            sid,
            resp.status,
            body[:300],
        )


def normalize_plivo_number(number: str) -> str:
    """Ensure E.164 with leading + (Plivo expects +countrycode...)."""
    n = (number or "").strip()
    if not n:
        return n
    digits = "".join(ch for ch in n if ch.isdigit())
    if not digits:
        return n
    return f"+{digits}"


async def make_plivo_call(
    session: aiohttp.ClientSession,
    to_number: str,
    from_number: str,
    answer_url: str,
    *,
    hangup_url: str | None = None,
    hangup_method: str = "POST",
) -> dict:
    auth_id, auth_token = _plivo_auth()
    url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/"
    auth = aiohttp.BasicAuth(auth_id, auth_token)
    data = {
        "to": normalize_plivo_number(to_number),
        "from": normalize_plivo_number(from_number),
        "answer_url": answer_url,
        "answer_method": "GET",
    }
    if hangup_url:
        data["hangup_url"] = hangup_url
        data["hangup_method"] = hangup_method
    async with session.post(url, json=data, auth=auth) as resp:
        if resp.status != 201:
            error = await resp.text()
            if plivo_error_is_insufficient_balance(resp.status, error):
                logger.error("Plivo dial rejected — account balance exhausted")
            raise Exception(f"Plivo error ({resp.status}): {error}")
        return await resp.json()

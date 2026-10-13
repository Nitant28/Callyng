"""Unit tests for Telnyx Telephony Provider and Webhook Verification."""

import pytest
import os
import base64
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import aiohttp
from telephony import (
    normalize_e164,
    normalize_phone_number,
    public_telephony_base_url,
    build_hangup_url,
    build_transfer_xml_url,
    build_texml_stream_xml,
    make_telnyx_call,
    hangup_telnyx_call,
    transfer_telnyx_call,
    stop_telnyx_stream,
    fetch_telnyx_balance,
    telnyx_error_is_insufficient_balance,
    verify_telnyx_webhook_signature,
)
from call_outcomes import outcome_from_telephony_status


def test_normalize_e164():
    assert normalize_e164("+1 (415) 555-1234") == "+14155551234"
    assert normalize_e164("9876543210") == "+919876543210"
    assert normalize_e164("+919876543210") == "+919876543210"
    assert normalize_e164("0014155551234") == "+14155551234"


def test_public_telephony_base_url():
    with patch.dict(os.environ, {"NGROK_URL": "https://api.example.com"}):
        assert public_telephony_base_url() == "https://api.example.com"

    with patch.dict(os.environ, {"NGROK_URL": ""}):
        assert public_telephony_base_url("app.aakashvani.ai:443") == "https://app.aakashvani.ai"
        assert public_telephony_base_url("localhost:7860") == "http://localhost:7860"


def test_build_texml_stream_xml():
    xml = build_texml_stream_xml("wss://api.example.com/ws?call_id=123")
    assert "<Stream" in xml
    assert 'url="wss://api.example.com/ws?call_id=123"' in xml
    assert 'contentType="audio/x-mulaw;rate=8000"' in xml


def test_outcome_from_telephony_status():
    assert outcome_from_telephony_status("busy") == "Busy"
    assert outcome_from_telephony_status("user_busy") == "Busy"
    assert outcome_from_telephony_status("no-answer") == "No_Answer"
    assert outcome_from_telephony_status("timeout") == "No_Answer"
    assert outcome_from_telephony_status("call_rejected") == "Rejected"
    assert outcome_from_telephony_status("failed") == "Carrier_Failed"
    assert outcome_from_telephony_status("unknown_xyz") == "Unknown"


def test_telnyx_error_is_insufficient_balance():
    assert telnyx_error_is_insufficient_balance(402, "Payment required")
    assert telnyx_error_is_insufficient_balance(403, "Forbidden")
    assert telnyx_error_is_insufficient_balance(500, "Account insufficient balance")
    assert not telnyx_error_is_insufficient_balance(200, "OK")


@pytest.mark.asyncio
async def test_make_telnyx_call():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='{"data": {"call_control_id": "v2:12345", "call_leg_id": "leg_123"}}')

    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post

    with patch.dict(os.environ, {
        "TELNYX_API_KEY": "KEY_123",
        "TELNYX_CONNECTION_ID": "CONN_456",
        "TELNYX_PHONE_NUMBER": "+15550001",
    }):
        res = await make_telnyx_call(
            mock_session,
            to_number="+919876543210",
            answer_url="https://api.example.com/answer",
        )
        assert res["call_control_id"] == "v2:12345"
        mock_session.post.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_telnyx_balance():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"data": {"balance": "150.75", "currency": "USD"}})

    mock_get = MagicMock()
    mock_get.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_get

    with patch.dict(os.environ, {"TELNYX_API_KEY": "KEY_123"}):
        bal = await fetch_telnyx_balance(mock_session)
        assert bal == Decimal("150.75")

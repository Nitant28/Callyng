"""Unit tests for test_call.py helpers."""

from __future__ import annotations

from uuid import UUID

import pytest

from test_call import (
    SANDBOX_BOT_CASCADED,
    SANDBOX_BOT_STS,
    SANDBOX_CAMPAIGN_ID,
    sandbox_bot_id_for_route,
    synthetic_lead_phone,
)
from script_runtime import parse_post_call_snapshot


def test_synthetic_lead_phone_format():
    phone = synthetic_lead_phone()
    assert phone.startswith("+cli")
    assert len(phone) == len("+cli") + 12
    assert synthetic_lead_phone() != synthetic_lead_phone()


def test_sandbox_bot_id_for_route_sts():
    assert sandbox_bot_id_for_route("sts") == SANDBOX_BOT_STS


def test_sandbox_bot_id_for_route_cascaded():
    assert sandbox_bot_id_for_route("cascaded") == SANDBOX_BOT_CASCADED


def test_sandbox_bot_id_for_route_invalid():
    with pytest.raises(ValueError, match="Invalid route"):
        sandbox_bot_id_for_route("invalid")


def test_sandbox_campaign_uuid():
    assert SANDBOX_CAMPAIGN_ID == UUID("00000000-0000-4000-8000-000000000006")


def test_parse_post_call_snapshot_from_call_data_shape():
    call_data = {
        "post_call_snapshot": {
            "extraction_schema": {"mode": "fields", "fields": []},
            "script_config_id": "abc",
            "version": 1,
        }
    }
    snap = parse_post_call_snapshot(call_data)
    assert snap is not None
    assert snap["script_config_id"] == "abc"

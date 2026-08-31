"""Unit tests for WhatsApp follow-up eligibility and payload contract (no live Meta/n8n)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from integrations.n8n.payload import build_lead_qualified_payload
from messages.eligibility import (
    conversation_window_open,
    decide_send,
    is_successful_send_status,
    parse_whatsapp_opt_in,
)


def test_interested_lead_payload_includes_client_and_idempotency():
    client_id = uuid4()
    lead_id = uuid4()
    payload = build_lead_qualified_payload(
        client_id=client_id,
        lead={
            "id": lead_id,
            "name": "Rahul",
            "phone": "9876543210",
            "lead_type": "warm",
            "metadata": {"email": "r@example.com"},
        },
        session_call_id="sess_1",
        duration_seconds=60,
        extraction={"intent_status": "Interested", "summary": "Wants demo"},
        campaign={"id": uuid4(), "name": "Camp"},
        outcome="Interested",
        client={"name": "Prowave", "industry": "real_estate"},
    )
    assert payload["client"]["id"] == str(client_id)
    assert payload["client"]["name"] == "Prowave"
    assert payload["client"]["industry"] == "real_estate"
    assert payload["lead"]["phone"] == "+919876543210"
    assert payload["lead"]["whatsapp_opt_in"] is True
    assert payload["follow_up"]["action"] == "send"
    assert payload["follow_up"]["idempotency_key"] == f"n8n_sess_1:{lead_id}_wa_1"


def test_missing_phone_skips_follow_up_action():
    payload = build_lead_qualified_payload(
        client_id=uuid4(),
        lead={"id": uuid4(), "name": "NoPhone", "phone": "", "metadata": {}},
        session_call_id="sess_2",
        duration_seconds=10,
        extraction={"intent_status": "Interested"},
        campaign={"id": uuid4(), "name": "C"},
        outcome="Interested",
        client={"name": "X", "industry": None},
    )
    assert payload["lead"]["phone"] is None
    assert payload["follow_up"]["action"] == "skip"
    assert payload["follow_up"]["skip_reason"] == "missing_phone"


def test_opt_out_skips_follow_up():
    assert parse_whatsapp_opt_in({"whatsapp_opt_out": True}) is False
    payload = build_lead_qualified_payload(
        client_id=uuid4(),
        lead={
            "id": uuid4(),
            "name": "Out",
            "phone": "+919876543210",
            "metadata": {"whatsapp_opt_in": False},
        },
        session_call_id="sess_3",
        duration_seconds=10,
        extraction={"intent_status": "Interested"},
        campaign={"id": uuid4(), "name": "C"},
        outcome="Interested",
    )
    assert payload["lead"]["whatsapp_opt_in"] is False
    assert payload["follow_up"]["action"] == "skip"
    assert payload["follow_up"]["skip_reason"] == "whatsapp_opt_out"


def test_conversation_window_open_path():
    now = datetime.now(timezone.utc)
    assert conversation_window_open(now - timedelta(hours=2), now=now) is True
    decision = decide_send(
        to_phone="+919876543210",
        last_inbound_at=now - timedelta(hours=1),
        text="Hello again",
    )
    assert decision.ok is True
    assert decision.message_type == "text"
    assert decision.conversation_window_open is True


def test_conversation_window_closed_requires_template():
    now = datetime.now(timezone.utc)
    closed = decide_send(
        to_phone="+919876543210",
        last_inbound_at=now - timedelta(hours=30),
        text="Hello freeform",
    )
    assert closed.ok is False
    assert closed.reason == "conversation_window_closed_template_required"

    with_template = decide_send(
        to_phone="+919876543210",
        last_inbound_at=None,
        text="Hello",
        template_name="follow_up_interested",
    )
    assert with_template.ok is True
    assert with_template.message_type == "template"


def test_force_message_type_and_success_status():
    d = decide_send(
        to_phone="+919876543210",
        text="Hi",
        force_message_type="text",
        last_inbound_at=None,
    )
    assert d.ok and d.message_type == "text"
    assert is_successful_send_status("sent")
    assert is_successful_send_status("delivered")
    assert not is_successful_send_status("failed")


def test_invalid_phone_rejected():
    d = decide_send(to_phone="not-a-number", text="Hi")
    assert d.ok is False
    assert d.reason == "missing_or_invalid_phone"

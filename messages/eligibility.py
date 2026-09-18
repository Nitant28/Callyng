"""WhatsApp follow-up eligibility helpers (no network I/O).

Used by the messages send path and documented for Mega_Workflow IF branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from lead_upload.normaliser import normalise_phone

# Meta Cloud customer-care window is 24 hours after the last customer message.
CONVERSATION_WINDOW = timedelta(hours=24)

_SUCCESS_STATUSES = frozenset({"sent", "delivered", "read", "accepted"})


@dataclass(frozen=True)
class SendDecision:
    """Canonical decision for text vs template (and whether to send at all)."""

    ok: bool
    message_type: str | None  # "text" | "template" | None
    reason: str | None = None
    phone_e164: str | None = None
    conversation_window_open: bool = False


def parse_whatsapp_opt_in(metadata: dict[str, Any] | None) -> bool:
    """Require explicit opt-in. Missing key = not opted in (fail closed)."""
    meta = metadata or {}
    if "whatsapp_opt_in" in meta:
        val = meta.get("whatsapp_opt_in")
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().casefold() in ("1", "true", "yes", "y")
        return bool(val)
    opt_out = meta.get("whatsapp_opt_out")
    if opt_out is True:
        return False
    if str(opt_out or "").strip().casefold() in ("1", "true", "yes", "y"):
        return False
    # No explicit consent recorded — do not send.
    return False


def conversation_window_open(
    last_inbound_at: datetime | None,
    *,
    now: datetime | None = None,
    window: timedelta = CONVERSATION_WINDOW,
) -> bool:
    if last_inbound_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    ts = last_inbound_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (current - ts) <= window


def decide_send(
    *,
    to_phone: str | None,
    whatsapp_opt_in: bool = True,
    last_inbound_at: datetime | None = None,
    template_name: str | None = None,
    text: str | None = None,
    force_message_type: str | None = None,
) -> SendDecision:
    """Decide whether to send and whether text or template is appropriate.

    Rules:
    - Missing/invalid phone → skip
    - Opt-out → skip
    - If force_message_type provided, honour it when content exists
    - Else: window open + text → text; otherwise require template_name
    """
    phone = normalise_phone(str(to_phone or "").strip()) if to_phone else None
    if not phone:
        # Keep raw if normaliser rejects but caller sent E.164-looking value
        raw = (to_phone or "").strip()
        if raw.startswith("+") and len(raw) >= 10:
            phone = raw
        else:
            return SendDecision(ok=False, message_type=None, reason="missing_or_invalid_phone")

    if not whatsapp_opt_in:
        return SendDecision(ok=False, message_type=None, reason="whatsapp_opt_out", phone_e164=phone)

    window_open = conversation_window_open(last_inbound_at)
    forced = (force_message_type or "").strip().casefold() or None

    if forced == "text":
        if not (text or "").strip():
            return SendDecision(
                ok=False,
                message_type=None,
                reason="text_required",
                phone_e164=phone,
                conversation_window_open=window_open,
            )
        return SendDecision(
            ok=True,
            message_type="text",
            phone_e164=phone,
            conversation_window_open=window_open,
        )

    if forced == "template":
        if not (template_name or "").strip():
            return SendDecision(
                ok=False,
                message_type=None,
                reason="template_required",
                phone_e164=phone,
                conversation_window_open=window_open,
            )
        return SendDecision(
            ok=True,
            message_type="template",
            phone_e164=phone,
            conversation_window_open=window_open,
        )

    if window_open and (text or "").strip():
        return SendDecision(
            ok=True,
            message_type="text",
            phone_e164=phone,
            conversation_window_open=True,
        )

    if (template_name or "").strip():
        return SendDecision(
            ok=True,
            message_type="template",
            phone_e164=phone,
            conversation_window_open=window_open,
        )

    if (text or "").strip() and not window_open:
        return SendDecision(
            ok=False,
            message_type=None,
            reason="conversation_window_closed_template_required",
            phone_e164=phone,
            conversation_window_open=False,
        )

    return SendDecision(
        ok=False,
        message_type=None,
        reason="text_or_template_required",
        phone_e164=phone,
        conversation_window_open=window_open,
    )


def is_successful_send_status(status: str | None) -> bool:
    return (status or "").strip().casefold() in _SUCCESS_STATUSES

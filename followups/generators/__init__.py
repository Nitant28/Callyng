"""Deterministic, code-only message generators used when AI output is unusable."""

from followups.generators.email import EmailContent, build_initial_email
from followups.generators.whatsapp import (
    build_inbound_reply,
    build_initial_followup,
    classify_inbound_intent,
)

__all__ = [
    "EmailContent",
    "build_inbound_reply",
    "build_initial_email",
    "build_initial_followup",
    "classify_inbound_intent",
]

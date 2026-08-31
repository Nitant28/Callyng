"""AI-first, code-guaranteed message resolution.

Every caller that needs customer-facing copy goes through this module. AI output
is preferred but always validated; anything unusable is replaced by a
deterministic generator. These functions never raise and never return an empty
message, so an AI outage degrades quality rather than breaking delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from followups.context import LeadContext
from followups.generators.email import (
    EmailContent,
    build_initial_email,
    build_minimal_email,
)
from followups.generators.whatsapp import (
    build_inbound_reply,
    build_initial_followup,
    build_minimal_message,
    classify_inbound_intent,
)
from followups.validation import validate_email, validate_message

SOURCE_AI = "ai"
SOURCE_FALLBACK = "fallback"


@dataclass(frozen=True)
class ResolvedMessage:
    """A message that is guaranteed to be sendable."""

    text: str
    source: str
    reason: str | None = None
    intent: str | None = None

    @property
    def ai_generated(self) -> bool:
        return self.source == SOURCE_AI

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "reason": self.reason,
            "intent": self.intent,
            "ai_generated": self.ai_generated,
        }


@dataclass(frozen=True)
class ResolvedEmail:
    subject: str
    body: str
    source: str
    reason: str | None = None

    @property
    def ai_generated(self) -> bool:
        return self.source == SOURCE_AI

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "body": self.body,
            "source": self.source,
            "reason": self.reason,
            "ai_generated": self.ai_generated,
        }


def _safe(builder, ctx: LeadContext, *args) -> str:
    try:
        return builder(ctx, *args)
    except Exception:  # pragma: no cover - defensive: generators must never break sending
        logger.exception("deterministic generator failed lead={}", ctx.lead_id)
        return build_minimal_message(ctx)


def resolve_initial_whatsapp(ctx: LeadContext, ai_output: Any = None) -> ResolvedMessage:
    """First WhatsApp follow-up after an interested call."""
    result = validate_message(ai_output) if ai_output is not None else None
    if result and result.ok and result.text:
        return ResolvedMessage(text=result.text, source=SOURCE_AI)

    reason = result.reason if result else "no_ai_output"
    return ResolvedMessage(
        text=_safe(build_initial_followup, ctx),
        source=SOURCE_FALLBACK,
        reason=reason,
    )


def resolve_inbound_reply(
    ctx: LeadContext,
    inbound_text: str | None,
    ai_output: Any = None,
) -> ResolvedMessage:
    """Reply to a customer WhatsApp message."""
    intent = classify_inbound_intent(inbound_text)
    result = validate_message(ai_output, inbound_text=inbound_text) if ai_output is not None else None
    if result and result.ok and result.text:
        return ResolvedMessage(text=result.text, source=SOURCE_AI, intent=intent)

    reason = result.reason if result else "no_ai_output"
    return ResolvedMessage(
        text=_safe(build_inbound_reply, ctx, inbound_text),
        source=SOURCE_FALLBACK,
        reason=reason,
        intent=intent,
    )


def resolve_initial_email(ctx: LeadContext, ai_output: Any = None) -> ResolvedEmail:
    """First follow-up email. Subject and body are accepted or rejected together."""
    reason = "no_ai_output"
    if ai_output is not None:
        subject, body = validate_email(ai_output)
        if subject.ok and body.ok and subject.text and body.text:
            return ResolvedEmail(subject=subject.text, body=body.text, source=SOURCE_AI)
        reason = subject.reason if not subject.ok else body.reason

    try:
        content = build_initial_email(ctx)
    except Exception:  # pragma: no cover - defensive
        logger.exception("deterministic email generator failed lead={}", ctx.lead_id)
        content = build_minimal_email(ctx)

    return ResolvedEmail(
        subject=content.subject,
        body=content.body,
        source=SOURCE_FALLBACK,
        reason=reason,
    )


def build_fallback_bundle(ctx: LeadContext, *, inbound_text: str | None = None) -> dict[str, Any]:
    """Pre-computed deterministic copy handed to n8n alongside the lead context.

    n8n prefers its own AI output, but when that fails its fallback becomes
    "use the text the backend already provided" - a path with nothing left to fail.
    """
    email = resolve_initial_email(ctx)
    bundle: dict[str, Any] = {
        "generated_by": "aakashvani-backend",
        "whatsapp": {"message": _safe(build_initial_followup, ctx)},
        "email": {"subject": email.subject, "body": email.body},
    }
    if inbound_text is not None:
        reply = resolve_inbound_reply(ctx, inbound_text)
        bundle["reply"] = {"message": reply.text, "intent": reply.intent}
    return bundle


def to_email_content(resolved: ResolvedEmail) -> EmailContent:
    return EmailContent(subject=resolved.subject, body=resolved.body)

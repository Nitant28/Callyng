"""Deterministic follow-up email generator (plain text, Gmail-node friendly)."""

from __future__ import annotations

from dataclasses import dataclass

from followups.context import LeadContext
from followups.generators._text import clamp, format_budget, greeting
from followups.validation import MAX_EMAIL_BODY_CHARS, MAX_EMAIL_SUBJECT_CHARS


@dataclass(frozen=True)
class EmailContent:
    subject: str
    body: str


def _subject(ctx: LeadContext) -> str:
    if ctx.bhk_preference and ctx.locality:
        return f"Your {ctx.bhk_preference} search in {ctx.locality} \u2014 next steps"
    if ctx.locality:
        return f"Following up on your property search in {ctx.locality}"
    if ctx.client_name:
        return f"Following up on your call with {ctx.client_name}"
    return "Following up on your recent call"


def _recap_lines(ctx: LeadContext) -> list[str]:
    lines: list[str] = []
    if ctx.property_type:
        lines.append(f"- Property type: {ctx.property_type}")
    if ctx.bhk_preference:
        lines.append(f"- Configuration: {ctx.bhk_preference}")
    if ctx.location_preference:
        lines.append(f"- Preferred location: {ctx.location_preference}")
    elif ctx.city:
        lines.append(f"- City: {ctx.city}")
    budget = format_budget(ctx.budget)
    if budget:
        lines.append(f"- Budget: {budget}")
    if ctx.callback_time:
        lines.append(f"- Preferred time to talk: {ctx.callback_time}")
    return lines


def build_initial_email(ctx: LeadContext) -> EmailContent:
    """Compose the first follow-up email from verified lead context only."""
    company = ctx.client_name or "our team"
    blocks: list[str] = [greeting(ctx.first_name)]

    blocks.append(
        f"Thank you for taking the time to speak with {company} earlier. "
        "I wanted to follow up in writing so you have everything in one place."
    )

    recap = _recap_lines(ctx)
    if recap:
        blocks.append("Here's what you shared with us:\n" + "\n".join(recap))

    if ctx.summary:
        blocks.append(f"Notes from the call:\n{ctx.summary}")

    if recap or ctx.summary:
        blocks.append(
            "Our team is putting together options that match these requirements and will "
            "share them with you shortly."
        )
    else:
        blocks.append(
            "Our team is ready to help you with the next steps as soon as you let us know "
            "what you're looking for."
        )

    blocks.append(
        "If you'd like to move faster, simply reply to this email or message us on WhatsApp "
        "and we'll pick it up straight away."
    )

    blocks.append(f"Warm regards,\n{company}")

    return EmailContent(
        subject=clamp(_subject(ctx), MAX_EMAIL_SUBJECT_CHARS),
        body=clamp("\n\n".join(blocks), MAX_EMAIL_BODY_CHARS),
    )


def build_minimal_email(ctx: LeadContext) -> EmailContent:
    """Last-resort email used only if the generator itself raises."""
    company = ctx.client_name or "our team"
    return EmailContent(
        subject="Following up on your recent call",
        body=(
            f"{greeting(ctx.first_name)}\n\n"
            f"Thank you for speaking with {company}. A member of our team will be in touch "
            "shortly with the next steps.\n\n"
            "You can reply to this email at any time.\n\n"
            f"Warm regards,\n{company}"
        ),
    )

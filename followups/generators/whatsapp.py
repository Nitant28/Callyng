"""Deterministic WhatsApp message generators.

These run when AI output is missing or rejected. They compose a professional
message from verified lead context only, and never state a fact we do not hold.
"""

from __future__ import annotations

import re

from followups.context import LeadContext
from followups.generators._text import (
    clamp,
    format_budget,
    inline_greeting,
    join_natural,
)
from followups.validation import MAX_WHATSAPP_CHARS

INTENT_OPT_OUT = "opt_out"
INTENT_IDENTITY = "identity"
INTENT_PRICING = "pricing"
INTENT_SITE_VISIT = "site_visit"
INTENT_CALLBACK = "callback"
INTENT_AVAILABILITY = "availability"
INTENT_PROPERTY_SEARCH = "property_search"
INTENT_LOCATION = "location"
INTENT_THANKS = "thanks"
INTENT_GREETING = "greeting"
INTENT_AFFIRMATIVE = "affirmative"
INTENT_NEGATIVE = "negative"
INTENT_UNKNOWN = "unknown"

_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        INTENT_OPT_OUT,
        (
            "stop", "unsubscribe", "opt out", "do not contact", "dont contact",
            "don't contact", "do not message", "dont message", "remove me",
            "band karo", "mat karo", "not interested at all", "leave me alone",
        ),
    ),
    (
        INTENT_IDENTITY,
        (
            "who is this", "who's this", "whos this", "who are you", "who r u",
            "who dis", "which company", "what company", "aap kaun", "kaun ho",
            "kon ho", "kaun bol", "kon bol", "your name", "introduce yourself",
        ),
    ),
    (
        INTENT_PRICING,
        (
            "price", "pricing", "rate", "cost", "how much", "kitna", "kitne",
            "budget", "emi", "loan", "down payment", "per sqft", "per sq ft",
            "psf", "charges", "expensive", "discount", "offer price",
        ),
    ),
    (
        INTENT_SITE_VISIT,
        (
            "site visit", "site-visit", "visit", "viewing", "tour", "dekhna",
            "dekhne", "see the property", "come and see", "appointment",
        ),
    ),
    (
        INTENT_CALLBACK,
        (
            "call me", "call back", "callback", "give me a call", "phone karo",
            "baat karni", "baat karo", "talk to someone", "speak to someone",
            "real person", "human", "agent", "representative", "executive",
        ),
    ),
    (
        INTENT_AVAILABILITY,
        (
            "available", "availability", "ready to move", "ready-to-move",
            "possession", "inventory", "in stock", "options", "khali", "vacant",
        ),
    ),
    (
        INTENT_PROPERTY_SEARCH,
        (
            "property", "flat", "apartment", "villa", "plot", "house", "bhk",
            "ghar", "makan", "project", "looking for", "interested in", "want to buy",
            "want to rent", "need a", "show me",
        ),
    ),
    (
        INTENT_LOCATION,
        ("location", "which area", "what area", "locality", "address", "kahan", "kaha", "nearby", "near by"),
    ),
    (
        INTENT_THANKS,
        ("thanks", "thank you", "thankyou", "thnx", "tysm", "dhanyavad", "shukriya"),
    ),
    (
        INTENT_GREETING,
        (
            "good morning", "good afternoon", "good evening", "namaste",
            "namaskar", "hello", "hey there",
        ),
    ),
    (
        INTENT_NEGATIVE,
        ("not interested", "no thanks", "no thank you", "nahi chahiye", "later", "busy right now"),
    ),
)

_WORDS: tuple[tuple[str, frozenset[str]], ...] = (
    (INTENT_GREETING, frozenset({"hi", "hii", "hiii", "hey", "helo", "hlo", "yo"})),
    (INTENT_THANKS, frozenset({"ty", "thx"})),
    (INTENT_AFFIRMATIVE, frozenset({"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "haan", "han", "ha", "theek", "thik"})),
    (INTENT_NEGATIVE, frozenset({"no", "nope", "nahi", "nahin"})),
)


def classify_inbound_intent(text: str | None) -> str:
    """Deterministically bucket a customer message into a fallback branch."""
    if not text or not str(text).strip():
        return INTENT_UNKNOWN
    normalised = re.sub(r"[^a-z0-9\s']", " ", str(text).casefold())
    normalised = re.sub(r"\s+", " ", normalised).strip()
    if not normalised:
        return INTENT_UNKNOWN
    padded = f" {normalised} "

    for intent, phrases in _PHRASES:
        for phrase in phrases:
            if f" {phrase} " in padded or padded.strip() == phrase:
                return intent

    tokens = set(normalised.split())
    for intent, words in _WORDS:
        if tokens & words:
            return intent

    return INTENT_UNKNOWN


def _preference_clause(ctx: LeadContext) -> str:
    """Describe what the customer told us, using only verified fields."""
    parts: list[str] = []
    if ctx.bhk_preference and ctx.locality:
        parts.append(f"a {ctx.bhk_preference} in {ctx.locality}")
    elif ctx.bhk_preference:
        parts.append(f"a {ctx.bhk_preference}")
    elif ctx.property_type and ctx.locality:
        parts.append(f"a {ctx.property_type} in {ctx.locality}")
    elif ctx.property_type:
        parts.append(f"a {ctx.property_type}")
    elif ctx.locality:
        parts.append(f"options in {ctx.locality}")

    budget = format_budget(ctx.budget)
    if budget:
        parts.append(f"a budget of around {budget}")
    return join_natural(parts)


def _team(ctx: LeadContext) -> str:
    return ctx.client_name or "our team"


def build_initial_followup(ctx: LeadContext) -> str:
    """First WhatsApp touch after an interested call."""
    lines: list[str] = []
    opener = inline_greeting(ctx.first_name)
    team = ctx.client_name or "our team"
    lines.append(f"{opener}, thank you for speaking with {team}.")

    clause = _preference_clause(ctx)
    if clause:
        lines.append(f"You mentioned you're looking for {clause}.")
    else:
        lines.append("I wanted to follow up on your conversation with our assistant.")

    if ctx.callback_time:
        lines.append(
            f"You said {ctx.callback_time} suits you better for a call, so we'll plan around that."
        )

    lines.append(
        "I can help you shortlist suitable options and take the next steps whenever you're ready \u2014 "
        "just reply here."
    )
    if ctx.client_name:
        lines.append(f"\u2014 {ctx.client_name}")

    return clamp("\n\n".join(lines), MAX_WHATSAPP_CHARS)


def _reply_for_intent(ctx: LeadContext, intent: str) -> str:
    name = ctx.first_name
    hello = inline_greeting(name)
    team = _team(ctx)
    clause = _preference_clause(ctx)
    about = f" about {clause}" if clause else ""

    if intent == INTENT_OPT_OUT:
        return (
            f"{hello}, understood \u2014 I've noted your request and you won't receive any further "
            f"follow-ups from {team}. Thank you for your time."
        )

    if intent == INTENT_IDENTITY:
        intro = f"this is {ctx.client_name}" if ctx.client_name else "we're the team"
        return (
            f"{hello}, {intro} \u2014 we spoke with you recently over a call{about}. "
            "I'm here on WhatsApp to help you with the next steps whenever it suits you."
        )

    if intent == INTENT_PRICING:
        detail = f" for {clause}" if clause else ""
        return (
            f"{hello}, thanks for asking. Pricing depends on the exact project and configuration, "
            f"so I'd rather get you accurate current numbers{detail} than an estimate. "
            f"I'll have a specialist from {team} confirm them and share the details here. "
            "Would a call today or tomorrow work better for you?"
        )

    if intent == INTENT_SITE_VISIT:
        return (
            f"{hello}, we can certainly arrange a visit. Which day and time suit you best? "
            f"I'll check availability with {team} and confirm the details here."
        )

    if intent == INTENT_CALLBACK:
        when = f" You'd mentioned {ctx.callback_time} works for you." if ctx.callback_time else ""
        return (
            f"{hello}, of course. I'll arrange for someone from {team} to call you on this number."
            f"{when} What time works best?"
        )

    if intent == INTENT_AVAILABILITY:
        detail = f" for {clause}" if clause else ""
        return (
            f"{hello}, good question. Availability changes quickly, so I'll get the current status"
            f"{detail} confirmed by {team} and update you here shortly."
        )

    if intent == INTENT_PROPERTY_SEARCH:
        recap = f" You'd mentioned {clause}." if clause else ""
        return (
            f"{hello}, happy to help with that.{recap} Could you confirm the area and configuration "
            "you'd like to focus on, and I'll line up suitable options for you?"
        )

    if intent == INTENT_LOCATION:
        focus = f" We're currently helping buyers in {ctx.locality}." if ctx.locality else ""
        return (
            f"{hello}, happy to help.{focus} Let me know the area you have in mind and "
            "I'll check what's suitable there."
        )

    if intent == INTENT_THANKS:
        return (
            f"{hello}, you're very welcome! I'm here if anything else comes up \u2014 "
            "just message me on this chat."
        )

    if intent == INTENT_GREETING:
        recap = f" You'd spoken with us{about}." if clause else ""
        return (
            f"{hello}, good to hear from you!{recap} "
            "How can I help you today?"
        )

    if intent == INTENT_AFFIRMATIVE:
        return (
            f"{hello}, great. I'll take this forward and share the next steps here shortly. "
            "If there's anything specific you'd like me to check first, just let me know."
        )

    if intent == INTENT_NEGATIVE:
        return (
            f"{hello}, understood \u2014 thanks for letting us know. "
            "If things change, just message here and we'll pick it up from where we left off."
        )

    return (
        f"{hello}, thanks for your message. I want to make sure I get this right, so I'm checking "
        f"with a specialist from {team} and will reply here shortly. "
        "In the meantime, feel free to add any details about what you're looking for."
    )


def build_inbound_reply(ctx: LeadContext, inbound_text: str | None) -> str:
    """Context-aware reply to a customer WhatsApp message."""
    intent = classify_inbound_intent(inbound_text)
    return clamp(_reply_for_intent(ctx, intent), MAX_WHATSAPP_CHARS)


def build_minimal_message(ctx: LeadContext) -> str:
    """Last-resort message used only if a generator itself raises."""
    hello = inline_greeting(ctx.first_name)
    team = _team(ctx)
    return clamp(
        f"{hello}, thanks for getting in touch with {team}. "
        "Someone from our team will continue this conversation with you here shortly.",
        MAX_WHATSAPP_CHARS,
    )

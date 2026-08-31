"""Phase 1: deterministic fallback, AI validation and first-contact template tests.

These are pure-function tests: no database, no network, no n8n.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from followups.context import CONTINUE_CHAT, LeadContext
from followups.fallback import (
    SOURCE_AI,
    SOURCE_FALLBACK,
    build_fallback_bundle,
    resolve_inbound_reply,
    resolve_initial_email,
    resolve_initial_whatsapp,
)
from followups.generators._text import format_budget, indian_grouping
from followups.generators.whatsapp import (
    INTENT_AVAILABILITY,
    INTENT_CALLBACK,
    INTENT_GREETING,
    INTENT_IDENTITY,
    INTENT_OPT_OUT,
    INTENT_PRICING,
    INTENT_PROPERTY_SEARCH,
    INTENT_SITE_VISIT,
    INTENT_THANKS,
    INTENT_UNKNOWN,
    build_initial_followup,
    classify_inbound_intent,
)
from followups.templates import (
    MODE_BLOCKED,
    MODE_TEMPLATE,
    MODE_TEXT,
    FirstContactTemplate,
    TemplateVariable,
    parse_first_contact_template,
    plan_first_contact,
    select_template_config,
)
from followups.validation import extract_text, validate_email, validate_message

FULL_CTX = LeadContext(
    lead_id=str(uuid4()),
    name="Nitant Singh",
    phone="+917397867643",
    email="lead@example.com",
    client_name="Dev Client",
    client_industry="real_estate",
    campaign_name="Aakashvani Test",
    city="Pune",
    bhk_preference="2 BHK",
    location_preference="Baner",
    budget="8000000",
    summary="Customer is interested in a 2 BHK property in Pune.",
)

SPARSE_CTX = LeadContext(phone="+917397867643")


# ── Lead context ────────────────────────────────────────────────────────────


def test_context_normalises_placeholder_values():
    ctx = LeadContext.from_lead_row(
        {"id": "1", "name": "  ", "phone": "+91739", "metadata": {"lead_city": "null"}},
        extraction={"bhk_preference": "N/A", "summary": "undefined"},
    )
    assert ctx.name is None
    assert ctx.city is None
    assert ctx.bhk_preference is None
    assert ctx.summary is None


def test_context_from_payload_reads_nested_blocks():
    payload = {
        "client_id": "c1",
        "flow_type": CONTINUE_CHAT,
        "lead": {"id": "l1", "name": "Asha Rao", "phone": "+919999999999", "metadata": {"lead_city": "Pune"}},
        "client": {"name": "Acme Realty", "industry": "real_estate"},
        "campaign": {"id": "camp1", "name": "Q3 Push"},
        "extraction": {"bhk_preference": "3 BHK", "location_preference": "Wakad"},
    }
    ctx = LeadContext.from_payload(payload)
    assert ctx.first_name == "Asha"
    assert ctx.client_name == "Acme Realty"
    assert ctx.locality == "Wakad"
    assert ctx.is_continue_chat is True


def test_context_locality_falls_back_to_city():
    assert LeadContext(city="Pune").locality == "Pune"
    assert LeadContext(city="Pune", location_preference="Baner").locality == "Baner"


# ── Budget formatting ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(800, "800"), (80000, "80,000"), (8000000, "80,00,000"), (12500000, "1,25,00,000")],
)
def test_indian_grouping(amount, expected):
    assert indian_grouping(amount) == expected


def test_format_budget_adds_symbol_for_bare_numbers():
    assert format_budget("8000000") == "\u20b980,00,000"


def test_format_budget_preserves_customer_phrasing():
    assert format_budget("80 lakh") == "80 lakh"
    assert format_budget("1.2 Cr") == "1.2 Cr"


def test_format_budget_ignores_blank_and_zero():
    assert format_budget(None) is None
    assert format_budget("") is None
    assert format_budget("0") is None


# ── Deterministic initial follow-up ─────────────────────────────────────────


def test_initial_followup_uses_verified_context():
    message = build_initial_followup(FULL_CTX)
    assert "Nitant" in message
    assert "2 BHK" in message
    assert "Baner" in message
    assert "\u20b980,00,000" in message
    assert "Dev Client" in message


def test_initial_followup_survives_empty_context():
    message = build_initial_followup(SPARSE_CTX)
    assert message.startswith("Hi")
    assert len(message) > 40
    assert "None" not in message
    assert "{" not in message


def test_initial_followup_never_invents_missing_fields():
    ctx = LeadContext(name="Ravi", client_name="Acme")
    message = build_initial_followup(ctx)
    for invented in ("BHK", "budget", "\u20b9", "Pune"):
        assert invented not in message


def test_initial_followup_is_not_a_test_message():
    message = build_initial_followup(FULL_CTX).casefold()
    for banned in ("test message", "this is a test", "lorem"):
        assert banned not in message


# ── Inbound intent classification ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hi", INTENT_GREETING),
        ("Hello there", INTENT_GREETING),
        ("namaste", INTENT_GREETING),
        ("hi who is this?", INTENT_IDENTITY),
        ("who are you", INTENT_IDENTITY),
        ("aap kaun ho", INTENT_IDENTITY),
        ("what is the price?", INTENT_PRICING),
        ("kitna hai rate", INTENT_PRICING),
        ("how much for 2bhk", INTENT_PRICING),
        ("can we do a site visit", INTENT_SITE_VISIT),
        ("please call me", INTENT_CALLBACK),
        ("I want to talk to someone", INTENT_CALLBACK),
        ("is it ready to move", INTENT_AVAILABILITY),
        ("looking for a flat in wakad", INTENT_PROPERTY_SEARCH),
        ("thank you", INTENT_THANKS),
        ("stop", INTENT_OPT_OUT),
        ("please unsubscribe me", INTENT_OPT_OUT),
        ("asdkjhasd", INTENT_UNKNOWN),
        ("", INTENT_UNKNOWN),
        (None, INTENT_UNKNOWN),
    ],
)
def test_classify_inbound_intent(text, expected):
    assert classify_inbound_intent(text) == expected


def test_greeting_words_are_matched_on_boundaries_not_substrings():
    assert classify_inbound_intent("which project is this") != INTENT_GREETING


# ── Inbound reply fallback is context aware ─────────────────────────────────


def test_identity_reply_introduces_the_client():
    reply = resolve_inbound_reply(FULL_CTX, "hi who is this?")
    assert reply.source == SOURCE_FALLBACK
    assert reply.intent == INTENT_IDENTITY
    assert "Dev Client" in reply.text


def test_pricing_reply_refuses_to_quote_a_number():
    reply = resolve_inbound_reply(FULL_CTX, "what's the price?")
    assert reply.intent == INTENT_PRICING
    assert "\u20b9" not in reply.text.replace("\u20b980,00,000", "")


def test_opt_out_reply_confirms_removal():
    reply = resolve_inbound_reply(FULL_CTX, "stop")
    assert reply.intent == INTENT_OPT_OUT
    assert "further" in reply.text.casefold()


def test_distinct_intents_produce_distinct_replies():
    texts = ["hi", "who is this", "what is the price", "site visit", "call me", "stop"]
    replies = {resolve_inbound_reply(FULL_CTX, t).text for t in texts}
    assert len(replies) == len(texts)


def test_inbound_reply_works_without_any_lead_context():
    reply = resolve_inbound_reply(SPARSE_CTX, "hello")
    assert reply.text
    assert "None" not in reply.text


# ── AI output extraction and validation ────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        {"message": "Hello Nitant, happy to help you further."},
        {"output": {"message": "Hello Nitant, happy to help you further."}},
        '{"message": "Hello Nitant, happy to help you further."}',
        '```json\n{"message": "Hello Nitant, happy to help you further."}\n```',
        [{"message": "Hello Nitant, happy to help you further."}],
        "Hello Nitant, happy to help you further.",
    ],
)
def test_extract_text_handles_every_shape_n8n_produces(raw):
    assert extract_text(raw) == "Hello Nitant, happy to help you further."


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (None, "missing"),
        ("", "unusable_shape"),
        ("   ", "unusable_shape"),
        ("undefined", "literal_junk"),
        ("null", "literal_junk"),
        ({}, "unusable_shape"),
        ({"message": ""}, "unusable_shape"),
        ("short", "too_short"),
        ("x" * 2000, "too_long"),
        ("Hi {name}, thanks for your interest in our project.", "placeholder_leftover"),
        ("Hi {{ lead.name }}, thanks for your interest today.", "placeholder_leftover"),
        ("Sorry, the Gemini model is currently unavailable right now.", "banned_content"),
        ("Error in sub-node Google Gemini Chat Model1 occurred", "banned_content"),
        ("As an AI language model I cannot help with that request.", "banned_content"),
        ("NodeApiError: request failed after three attempts", "banned_content"),
    ],
)
def test_validate_message_rejects_unusable_output(candidate, reason):
    result = validate_message(candidate)
    assert result.ok is False
    assert result.reason == reason


def test_validate_message_accepts_clean_copy():
    result = validate_message("Hi Nitant, thanks for your time on the call earlier today.")
    assert result.ok is True
    assert result.text.startswith("Hi Nitant")


def test_validate_message_rejects_echo_of_customer_message():
    inbound = "hi who is this?"
    result = validate_message(inbound, inbound_text=inbound, min_chars=1)
    assert result.ok is False
    assert result.reason == "echoes_inbound"


def test_validate_message_collapses_whitespace():
    result = validate_message("Hi   Nitant,\n\n\n\nthanks for your time today.")
    assert result.ok is True
    assert "   " not in result.text
    assert "\n\n\n" not in result.text


def test_validate_email_requires_both_parts():
    subject, body = validate_email({"subject": "Following up", "body": ""})
    assert subject.ok is True
    assert body.ok is False


# ── Resolution: AI preferred, fallback guaranteed ───────────────────────────


def test_resolve_prefers_valid_ai_output():
    resolved = resolve_initial_whatsapp(
        FULL_CTX, {"message": "Hi Nitant, lovely speaking with you about Baner earlier."}
    )
    assert resolved.source == SOURCE_AI
    assert resolved.ai_generated is True
    assert resolved.reason is None


@pytest.mark.parametrize(
    "ai_output",
    [None, {}, "", "undefined", {"message": None}, {"wrong_key": "value"}, "Error: quota exceeded"],
)
def test_resolve_falls_back_for_every_kind_of_ai_failure(ai_output):
    resolved = resolve_initial_whatsapp(FULL_CTX, ai_output)
    assert resolved.source == SOURCE_FALLBACK
    assert resolved.ai_generated is False
    assert resolved.reason
    assert "Nitant" in resolved.text


def test_resolved_message_never_leaks_the_failure_reason_to_the_customer():
    resolved = resolve_initial_whatsapp(FULL_CTX, "Gemini rate limit exceeded")
    assert resolved.reason == "banned_content"
    assert "gemini" not in resolved.text.casefold()
    assert "rate limit" not in resolved.text.casefold()


def test_resolve_email_prefers_ai_then_falls_back():
    good = resolve_initial_email(FULL_CTX, {"subject": "Your Baner shortlist", "body": "Hi Nitant, here it is."})
    assert good.source == SOURCE_AI

    bad = resolve_initial_email(FULL_CTX, {"subject": "Hi", "body": None})
    assert bad.source == SOURCE_FALLBACK
    assert "Nitant" in bad.body
    assert bad.subject


def test_fallback_email_contains_only_verified_context():
    email = resolve_initial_email(SPARSE_CTX)
    assert email.source == SOURCE_FALLBACK
    for invented in ("BHK", "Pune", "\u20b9"):
        assert invented not in email.body


def test_fallback_bundle_has_everything_n8n_needs():
    bundle = build_fallback_bundle(FULL_CTX, inbound_text="what is the price?")
    assert bundle["whatsapp"]["message"]
    assert bundle["email"]["subject"]
    assert bundle["email"]["body"]
    assert bundle["reply"]["message"]
    assert bundle["reply"]["intent"] == INTENT_PRICING


def test_fallback_bundle_omits_reply_for_initial_followup():
    assert "reply" not in build_fallback_bundle(FULL_CTX)


# ── First-contact template configuration ───────────────────────────────────


def test_unconfigured_template_blocks_first_contact():
    plan = plan_first_contact(FirstContactTemplate(), FULL_CTX, conversation_window_open=False)
    assert plan.mode == MODE_BLOCKED
    assert plan.reason == "first_contact_template_not_configured"
    assert plan.can_send is False
    assert plan.template_name is None


def test_open_window_allows_free_form_text():
    plan = plan_first_contact(FirstContactTemplate(), FULL_CTX, conversation_window_open=True)
    assert plan.mode == MODE_TEXT
    assert plan.can_send is True


def test_usable_template_is_preferred_even_if_window_open():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="lead_followup_v1",
        language_code="en",
        variables=(TemplateVariable(index=1, source="first_name", fallback="there"),),
    )
    plan = plan_first_contact(template, FULL_CTX, conversation_window_open=True)
    assert plan.mode == MODE_TEMPLATE
    assert plan.template_name == "lead_followup_v1"
    assert plan.can_send is True


def test_unapproved_template_is_blocked():
    template = FirstContactTemplate(enabled=True, approved=False, template_name="lead_followup_v1")
    plan = plan_first_contact(template, FULL_CTX, conversation_window_open=False)
    assert plan.mode == MODE_BLOCKED
    assert plan.reason == "first_contact_template_not_approved"


def test_disabled_template_is_blocked():
    template = FirstContactTemplate(enabled=False, approved=True, template_name="lead_followup_v1")
    plan = plan_first_contact(template, FULL_CTX, conversation_window_open=False)
    assert plan.reason == "first_contact_template_disabled"


def test_approved_template_builds_meta_components():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="lead_followup_v1",
        language_code="en_US",
        phone_number_id="1184950391375570",
        variables=(
            TemplateVariable(index=1, source="first_name", fallback="there"),
            TemplateVariable(index=2, source="client_name"),
        ),
    )
    plan = plan_first_contact(template, FULL_CTX, conversation_window_open=False)
    assert plan.mode == MODE_TEMPLATE
    assert plan.template_name == "lead_followup_v1"
    assert plan.language_code == "en_US"
    assert plan.parameters == ("Nitant", "Dev Client")
    assert plan.components[0]["type"] == "body"
    assert plan.components[0]["parameters"][0] == {"type": "text", "text": "Nitant"}


def test_variable_fallback_fills_missing_context():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="lead_followup_v1",
        variables=(TemplateVariable(index=1, source="first_name", fallback="there"),),
    )
    plan = plan_first_contact(template, SPARSE_CTX, conversation_window_open=False)
    assert plan.mode == MODE_TEMPLATE
    assert plan.parameters == ("there",)


def test_unresolvable_variable_blocks_rather_than_sending_blank():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="lead_followup_v1",
        variables=(TemplateVariable(index=1, source="bhk_preference"),),
    )
    plan = plan_first_contact(template, SPARSE_CTX, conversation_window_open=False)
    assert plan.mode == MODE_BLOCKED
    assert plan.reason == "unresolved_variable:1:bhk_preference"


def test_unknown_variable_source_is_reported():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="lead_followup_v1",
        variables=(TemplateVariable(index=1, source="favourite_colour"),),
    )
    plan = plan_first_contact(template, FULL_CTX, conversation_window_open=False)
    assert plan.mode == MODE_BLOCKED
    assert plan.reason == "unknown_variable_source:favourite_colour"


def test_template_parameters_are_single_line():
    template = FirstContactTemplate(
        enabled=True,
        approved=True,
        template_name="t",
        variables=(TemplateVariable(index=1, source="summary"),),
    )
    ctx = LeadContext(summary="Line one.\nLine two.\t\tSpaced   out.")
    plan = plan_first_contact(template, ctx, conversation_window_open=False)
    assert "\n" not in plan.parameters[0]
    assert "\t" not in plan.parameters[0]
    assert "   " not in plan.parameters[0]


def test_parse_first_contact_template_from_integration_configuration():
    template = parse_first_contact_template(
        {
            "phone_number_id": "999",
            "first_contact_template": {
                "enabled": "true",
                "approved": True,
                "template_name": "lead_followup_v1",
                "language_code": "en_US",
                "variables": [
                    {"index": 2, "source": "client_name"},
                    {"index": 1, "source": "first_name", "fallback": "there"},
                ],
            },
        }
    )
    assert template.is_usable is True
    assert template.phone_number_id == "999"
    assert [v.index for v in template.variables] == [1, 2]


def test_parse_missing_configuration_is_not_usable():
    assert parse_first_contact_template(None).is_usable is False
    assert parse_first_contact_template({}).is_usable is False
    assert parse_first_contact_template({"first_contact_template": "nope"}).is_usable is False


def test_select_template_prefers_a_usable_integration():
    rows = [
        {"enabled": True, "configuration": {"first_contact_template": {"template_name": "draft"}}},
        {
            "enabled": True,
            "configuration": {
                "first_contact_template": {
                    "enabled": True,
                    "approved": True,
                    "template_name": "approved_one",
                }
            },
        },
    ]
    assert select_template_config(rows).template_name == "approved_one"


def test_select_template_handles_no_integrations():
    assert select_template_config([]).is_usable is False
    assert select_template_config(None).is_usable is False


# ── Conversation window helper used by the planner ─────────────────────────


def test_conversation_window_open_matches_meta_rule():
    from messages.eligibility import conversation_window_open

    now = datetime.now(timezone.utc)
    assert conversation_window_open(now - timedelta(hours=23)) is True
    assert conversation_window_open(now - timedelta(hours=25)) is False
    assert conversation_window_open(None) is False

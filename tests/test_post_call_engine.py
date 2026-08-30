"""Unit tests for Step 6 post-call snapshot consumption."""

from __future__ import annotations

import json

from post_call_extract import (
    apply_normalization_rules,
    build_extraction_system_prompt,
    filter_short_interrupted_turns,
    format_transcript_for_extraction,
    merge_consecutive_turns,
    normalize_post_call_extraction,
)
from sts_scripts.pyramid_extraction import PYRAMID_EXTRACTION_SCHEMA
from post_call_processor import _lead_transition
from script_runtime import parse_post_call_snapshot


def test_parse_post_call_snapshot_from_dict():
    call_data = {
        "post_call_snapshot": {
            "extraction_schema": {"mode": "fields", "fields": []},
            "version": 1,
        }
    }
    snap = parse_post_call_snapshot(call_data)
    assert snap is not None
    assert snap["version"] == 1


def test_parse_post_call_snapshot_from_json_string():
    inner = {"extraction_schema": {"mode": "summary"}, "version": 2}
    call_data = json.dumps({"post_call_snapshot": inner})
    snap = parse_post_call_snapshot(call_data)
    assert snap is not None
    assert snap["extraction_schema"]["mode"] == "summary"


def test_parse_post_call_snapshot_missing_schema():
    assert parse_post_call_snapshot({"post_call_snapshot": {}}) is None
    assert parse_post_call_snapshot(None) is None


def test_normalize_post_call_extraction_legacy_site_visit():
    parsed = {"site_visit_agreed": True, "intent_status": "Unknown"}
    out = normalize_post_call_extraction(parsed, normalization_rules=None)
    assert out["intent_status"] == "Interested"


def test_apply_normalization_rules_custom_intent():
    rules = [
        {
            "when": {"field": "site_visit_agreed", "truthy": True},
            "and_intent_in": ["", "Unknown"],
            "set": {"intent_status": "Interested"},
        }
    ]
    out = apply_normalization_rules(
        {"site_visit_agreed": True, "intent_status": "Unknown"}, rules
    )
    assert out["intent_status"] == "Interested"


def test_lead_transition_respects_snapshot_retry_set():
    snapshot = {
        "outcome_terminal": ["Done"],
        "outcome_retry": ["NoAnswer"],
        "outcome_callback": ["CallBack"],
    }
    status, next_at, sched_cb, fire = _lead_transition(
        "NoAnswer",
        attempts=1,
        max_attempts=3,
        retry_delay_minutes=60,
        extraction={},
        post_call_snapshot=snapshot,
    )
    assert status == "callback_scheduled"
    assert next_at is not None
    assert sched_cb is not None
    assert fire is False


def test_outcome_to_event_with_snapshot_map():
    from n8n_webhook import outcome_to_event

    assert outcome_to_event("Interested", event_map={"Interested": "custom_qualified"}) == (
        "custom_qualified"
    )


def test_outcome_to_event_without_map_unchanged():
    from n8n_webhook import outcome_to_event

    assert outcome_to_event("Interested") == "lead_qualified"
    assert outcome_to_event("Busy") == "lead_failed"


HINDI_STT_CONFLICT_TRANSCRIPT = [
    {
        "role": "assistant",
        "content": "जी। बस जानना था, क्या आप अभी Pune में कोई घर या flat देख रहे हैं?",
    },
    {"role": "user", "content": "और देख रहा हूं।"},
    {"role": "assistant", "content": "अच्छा सत्यम जी... आप क्या प्रॉपर्टी देख रहे हो? Two या three BHK?"},
    {"role": "user", "content": "सर, मैं टीवी बेच रहा हूं।"},
    {"role": "assistant", "content": "ठीक है,"},
    {
        "role": "assistant",
        "content": "ठीक है Satyam जी, मैंने आपकी बानेर, कोंढवा और कात्रज में 3 BHK की आवश्यकता नोट कर ली है। हमारे sales executive आपको जल्द कॉल करेंगे। धन्यवाद!",
    },
]


def test_merge_consecutive_turns_combines_assistant_fragments():
    raw = [
        {"role": "assistant", "content": "ठीक है,"},
        {"role": "assistant", "content": "Pune में कोई specific location?"},
        {"role": "user", "content": "बानेर"},
    ]
    merged = merge_consecutive_turns(raw)
    assert len(merged) == 2
    assert "ठीक है," in merged[0]["content"]
    assert "Pune में" in merged[0]["content"]


def test_filter_short_interrupted_assistant_turns():
    raw = [
        {"role": "assistant", "content": "ठीक है,", "interrupted": True},
        {"role": "assistant", "content": "Longer assistant response here."},
    ]
    filtered = filter_short_interrupted_turns(raw)
    assert len(filtered) == 1
    assert "Longer assistant" in filtered[0]["content"]


def test_format_transcript_for_extraction_labels_roles():
    text = format_transcript_for_extraction(HINDI_STT_CONFLICT_TRANSCRIPT)
    assert "ASSISTANT (authoritative" in text
    assert "USER (may contain speech-to-text errors" in text
    assert "3 BHK" in text
    assert "टीवी" in text


def test_build_extraction_system_prompt_includes_global_preamble():
    prompt = build_extraction_system_prompt(PYRAMID_EXTRACTION_SCHEMA)
    assert "Transcript reliability (critical)" in prompt
    assert "role=assistant text is the bot's own generated speech" in prompt
    # STT conflict is now only in PYRAMID_EXTRACTION_RULES, not the global preamble


def test_pyramid_rules_fix_wrong_requirement_when_fields_present():
    from sts_scripts.pyramid_extraction import PYRAMID_NORMALIZATION_RULES

    parsed = {
        "intent_status": "Wrong_Requirement",
        "bhk_preference": "3BHK",
        "location_preference": "Baner",
        "caller_notes": "Asked about selling a TV instead of property purchase",
    }
    out = normalize_post_call_extraction(
        parsed, normalization_rules=PYRAMID_NORMALIZATION_RULES
    )
    assert out["intent_status"] == "Interested"
    assert out["bhk_preference"] == "3BHK"
    assert out["location_preference"] == "Baner"
    assert out["caller_notes"] is None


def test_reconcile_callback_from_assistant_confirmation():
    from sts_scripts.pyramid_extraction import PYRAMID_NORMALIZATION_RULES
    parsed = {"intent_status": "Busy", "callback_time": "8:20"}
    out = normalize_post_call_extraction(
        parsed, normalization_rules=PYRAMID_NORMALIZATION_RULES
    )
    assert out["intent_status"] == "Callback_Requested"
    assert out.get("callback_time") == "8:20"


def test_normalize_without_rules_never_reads_transcript():
    parsed = {
        "intent_status": "Wrong_Requirement",
        "bhk_preference": None,
        "location_preference": None,
        "caller_notes": "Selling TV",
    }
    out = normalize_post_call_extraction(parsed, normalization_rules=[])
    assert out["intent_status"] == "Wrong_Requirement"
    assert out["bhk_preference"] is None


def test_resolve_lead_retry_or_failed():
    from db.postgres import resolve_lead_retry_or_failed

    status, next_at, outcome1 = resolve_lead_retry_or_failed(2, 3, 120, base_outcome="Busy")
    assert status == "callback_scheduled"
    assert next_at is not None
    assert outcome1 == "Busy"
    status2, next_at2, outcome2 = resolve_lead_retry_or_failed(3, 3, 120)
    assert status2 == "failed"
    assert next_at2 is None
    assert outcome2 == "Max_Attempts_Reached"

"""Unit tests for Step 6 post-call snapshot consumption."""

from __future__ import annotations

import json

from post_call_extract import (
    apply_normalization_rules,
    normalize_post_call_extraction,
)
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
    assert status == "pending"
    assert next_at is not None
    assert sched_cb is None
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

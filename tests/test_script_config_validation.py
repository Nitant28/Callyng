"""Unit tests for script_config validation."""

from __future__ import annotations

import pytest

from api.script_config_validation import (
    build_config_snapshot,
    default_template,
    validate_outcome_mapping,
    validate_script_config_payload,
    validate_script_id,
)


def test_validate_script_id_rejects_invalid():
    with pytest.raises(ValueError, match="script_id"):
        validate_script_id("Bad-Name")


def test_validate_outcome_mapping_complete():
    schema = {
        "mode": "fields",
        "fields": [
            {
                "key": "intent_status",
                "type": "enum",
                "values": ["Interested", "Busy"],
            }
        ],
    }
    validate_outcome_mapping(
        schema,
        outcome_terminal=["Interested"],
        outcome_retry=["Busy"],
        outcome_callback=[],
    )


def test_validate_outcome_mapping_missing_intent_value():
    schema = {
        "mode": "fields",
        "fields": [
            {
                "key": "intent_status",
                "type": "enum",
                "values": ["Interested", "Busy", "Unknown"],
            }
        ],
    }
    with pytest.raises(ValueError, match="not mapped"):
        validate_outcome_mapping(
            schema,
            outcome_terminal=["Interested"],
            outcome_retry=["Busy"],
            outcome_callback=[],
        )


def test_validate_outcome_mapping_skipped_for_summary():
    validate_outcome_mapping(
        {"mode": "summary", "summary_prompt": "Summarize"},
        outcome_terminal=[],
        outcome_retry=[],
        outcome_callback=[],
    )


def test_default_template_sts():
    tpl = default_template("sts")
    assert tpl["route"] == "sts"
    assert tpl["extraction_schema"]["mode"] == "fields"
    assert "intent_status" in str(tpl["extraction_schema"])


def test_build_config_snapshot_omits_id():
    row = {
        "id": "uuid",
        "created_at": "now",
        "script_id": "my_bot",
        "route": "sts",
        "version": 2,
        "extraction_schema": {"mode": "summary", "summary_prompt": "x"},
    }
    snap = build_config_snapshot(row)
    assert "id" not in snap
    assert snap["script_id"] == "my_bot"
    assert snap["version"] == 2


def test_validate_script_config_payload_invalid_overlap():
    data = default_template("sts")
    data["outcome_terminal"] = ["Interested", "Busy"]
    data["outcome_retry"] = []
    with pytest.raises(ValueError, match="not mapped|overlap"):
        validate_script_config_payload(data, partial=False)

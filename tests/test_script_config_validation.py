"""Unit tests for script_config validation."""

from __future__ import annotations

import json

import pytest

from api.script_config_validation import (
    build_config_snapshot,
    default_template,
    normalize_route,
    normalize_script_config_payload,
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


def test_normalize_route_maps_legacy_cascade():
    assert normalize_route("cascade") == "cascaded"
    assert normalize_route("CASCADE") == "cascaded"
    assert normalize_route("sts") == "sts"


def test_validate_script_config_rejects_double_stringified_extraction_schema():
    data = default_template("sts")
    inner = json.dumps({"mode": "summary", "summary_prompt": "Summarize"})
    data["extraction_schema"] = json.dumps(inner)
    with pytest.raises(ValueError, match="double-stringified"):
        validate_script_config_payload(data, partial=False)


def test_validate_script_config_parses_json_string_extraction_schema():
    data = default_template("sts")
    schema = data["extraction_schema"]
    data["extraction_schema"] = json.dumps(schema)
    validate_script_config_payload(data, partial=False)
    assert isinstance(data["extraction_schema"], dict)
    assert data["extraction_schema"]["mode"] == "fields"


def test_normalize_script_config_payload_route_alias():
    payload = normalize_script_config_payload({"route": "cascade"})
    assert payload["route"] == "cascaded"

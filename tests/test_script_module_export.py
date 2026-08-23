"""Unit tests for script_module_export."""

from __future__ import annotations

from api.script_config_validation import validate_script_config_payload
from script_module_export import export_cascade_module, export_sts_module
from script_prefetch import build_lead_dict, render_script_config


def test_export_sts_pyramid_hi_valid():
    payload = export_sts_module("pyramid_hi")
    assert payload["script_id"] == "pyramid_hi"
    validate_script_config_payload(payload, partial=False)


def test_export_sts_pyramid_mr_valid():
    payload = export_sts_module("pyramid_mr")
    assert payload["route"] == "sts"
    validate_script_config_payload(payload, partial=False)


def test_export_sts_pyramid_bilingual_uses_module_stem():
    payload = export_sts_module("pyramid_bilingual")
    assert payload["script_id"] == "pyramid_bilingual"
    validate_script_config_payload(payload, partial=False)


def test_export_cascade_prowave_valid_and_has_tools():
    payload = export_cascade_module("prowave")
    assert payload["route"] == "cascaded"
    assert payload["cascade_live_tools"]
    assert payload["transfer_enabled"] is False
    assert payload["live_tools_enabled"] is True
    validate_script_config_payload(payload, partial=False)


def test_exported_payload_render_round_trip():
    payload = export_sts_module("pyramid_hi")
    row = {
        "id": "00000000-0000-4000-8000-000000009999",
        "version": 1,
        **payload,
    }
    lead_dict = build_lead_dict(
        {"name": "Satyam", "phone": "+919999999999", "metadata": {"city": "Pune"}},
        {"city": "Pune"},
    )
    rendered = render_script_config(row, lead_dict, expected_route="sts")
    assert rendered["script_id"] == "pyramid_hi"
    assert rendered["system_instruction"]

"""Unit tests for cascade catalog validation."""

from __future__ import annotations

import pytest

from api.script_config_validation import (
    default_template,
    validate_cascade_config,
    validate_script_config_payload,
)

_MIN_EXTRACTION = {
    "mode": "fields",
    "fields": [{"name": "intent_status", "type": "enum", "values": ["Interested", "Busy"]}],
}

_CASCADE_BASE = {
    "script_id": "test_cascade",
    "route": "cascaded",
    "system_instruction_template": "Hello",
    "extraction_schema": _MIN_EXTRACTION,
    "cascade_stt_provider": "sarvam",
    "cascade_stt_model": "saaras:v3",
    "cascade_llm_provider": "groq",
    "cascade_llm_model": "openai/gpt-oss-120b",
    "cascade_tts_provider": "cartesia",
    "cascade_tts_model": "sonic-3.5",
    "cascade_tts_voice": "",
    "cascade_stt_settings": {},
    "cascade_llm_settings": {},
    "cascade_tts_settings": {},
}


def test_sts_payload_with_cascade_defaults_still_validates():
    payload = default_template("sts")
    payload["cascade_tts_voice"] = "sonic-3"
    validate_script_config_payload(payload, partial=False)


def test_sts_payload_with_legacy_cascade_models_still_validates():
    """D2: STS rows with pre-migration cascade defaults must not block save."""
    payload = default_template("sts")
    payload["cascade_stt_model"] = "nova-2"
    payload["cascade_tts_model"] = "eleven_turbo_v2_5"
    validate_script_config_payload(payload, partial=False)


def test_blank_provider_accepted():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_provider"] = ""
    validate_cascade_config(data)


def test_bad_provider_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_provider"] = "unknown-vendor"
    with pytest.raises(ValueError, match="Unknown stt provider"):
        validate_cascade_config(data)


def test_google_stt_rejected_on_cascade():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_provider"] = "google"
    with pytest.raises(ValueError, match="Unknown stt provider"):
        validate_cascade_config(data)


def test_bad_model_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_llm_model"] = "not-a-model"
    with pytest.raises(ValueError, match="Unknown llm model"):
        validate_cascade_config(data)


def test_unknown_settings_key_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_tts_settings"] = {"speed": 1.0}
    with pytest.raises(ValueError, match="unknown keys"):
        validate_cascade_config(data)


def test_sonic_35_rejects_speed_setting():
    data = dict(_CASCADE_BASE)
    data["cascade_tts_settings"] = {"generation_config.speed": 1.1}
    with pytest.raises(ValueError, match="unknown keys"):
        validate_cascade_config(data)


def test_eleven_v3_rejects_speed_setting():
    data = dict(_CASCADE_BASE)
    data["cascade_tts_provider"] = "elevenlabs"
    data["cascade_tts_model"] = "eleven_v3"
    data["cascade_tts_settings"] = {"speed": 1.0}
    with pytest.raises(ValueError, match="unknown keys"):
        validate_cascade_config(data)


def test_out_of_range_number_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_llm_settings"] = {"temperature": 99}
    with pytest.raises(ValueError, match="above maximum"):
        validate_cascade_config(data)


def test_elevenlabs_filter_background_audio_true_accepted():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_provider"] = "elevenlabs"
    data["cascade_stt_model"] = "scribe_v2_realtime"
    data["cascade_stt_settings"] = {"language": "hi", "filter_background_audio": True}
    validate_cascade_config(data)


def test_elevenlabs_filter_background_audio_string_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_provider"] = "elevenlabs"
    data["cascade_stt_model"] = "scribe_v2_realtime"
    data["cascade_stt_settings"] = {"language": "hi", "filter_background_audio": "yes"}
    with pytest.raises(ValueError, match="must be a boolean"):
        validate_cascade_config(data)


def test_sarvam_rejects_filter_background_audio():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_settings"] = {"filter_background_audio": True}
    with pytest.raises(ValueError, match="unknown keys"):
        validate_cascade_config(data)


def test_google_safety_settings_json_accepted():
    data = dict(_CASCADE_BASE)
    data["cascade_llm_provider"] = "google"
    data["cascade_llm_model"] = "gemini-3.6-flash"
    data["cascade_llm_settings"] = {
        "safety_settings": '[{"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}]'
    }
    validate_cascade_config(data)


def test_groq_rejects_safety_settings():
    data = dict(_CASCADE_BASE)
    data["cascade_llm_settings"] = {"safety_settings": "[]"}
    with pytest.raises(ValueError, match="unknown keys"):
        validate_cascade_config(data)


def test_transfer_enabled_invalid_number_rejected():
    data = dict(_CASCADE_BASE)
    data["transfer_enabled"] = True
    data["transfer_number"] = "not-a-number"
    with pytest.raises(ValueError, match="transfer_number"):
        validate_cascade_config(data)


def test_transfer_enabled_normalizes_to_e164():
    data = dict(_CASCADE_BASE)
    data["transfer_enabled"] = True
    data["transfer_number"] = "9876543210"
    validate_cascade_config(data)
    assert data["transfer_number"] == "+919876543210"


def test_transfer_disabled_garbage_number_ignored():
    data = dict(_CASCADE_BASE)
    data["transfer_enabled"] = False
    data["transfer_number"] = "garbage"
    validate_cascade_config(data)


def test_live_tools_enabled_empty_list_rejected():
    data = dict(_CASCADE_BASE)
    data["live_tools_enabled"] = True
    data["cascade_live_tools"] = []
    with pytest.raises(ValueError, match="cascade_live_tools"):
        validate_cascade_config(data)


def test_live_tools_enabled_requires_name_and_description():
    data = dict(_CASCADE_BASE)
    data["live_tools_enabled"] = True
    data["cascade_live_tools"] = [{"name": "push_lead_data"}]
    with pytest.raises(ValueError, match="description"):
        validate_cascade_config(data)


def test_sts_payload_ignores_transfer_and_live_tools_rules():
    payload = default_template("sts")
    payload["transfer_enabled"] = True
    payload["transfer_number"] = "nope"
    payload["live_tools_enabled"] = True
    payload["cascade_live_tools"] = []
    validate_script_config_payload(payload, partial=False)


def test_bad_select_value_rejected():
    data = dict(_CASCADE_BASE)
    data["cascade_stt_settings"] = {"language": "xx-XX"}
    with pytest.raises(ValueError, match="not in"):
        validate_cascade_config(data)

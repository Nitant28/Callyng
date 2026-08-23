"""Unit tests for CascadeRuntime provider wiring."""

from __future__ import annotations

import script_runtime as sr
from providers import catalog


def test_prefetch_carries_providers_models_and_settings():
    prefetch = {
        "source": "script_config",
        "route": "cascaded",
        "script_id": "prowave_db",
        "version": 2,
        "system_prompt": "Cascade hello",
        "cascade_stt_provider": "deepgram",
        "cascade_stt_model": "nova-3",
        "cascade_stt_settings": {"language": "hi"},
        "cascade_llm_provider": "openai",
        "cascade_llm_model": "gpt-4o-mini",
        "cascade_llm_settings": {"temperature": 0.3},
        "cascade_tts_provider": "cartesia",
        "cascade_tts_model": "sonic-3.5",
        "cascade_tts_voice": "voice-uuid",
        "cascade_tts_settings": {"language": "hi"},
        "cascade_live_tools": [],
        "extraction_schema": {"fields": {}},
    }
    runtime = sr._cascade_from_prefetch(prefetch)
    assert runtime.stt_provider == "deepgram"
    assert runtime.stt_model == "nova-3"
    assert runtime.stt_settings == {"language": "hi"}
    assert runtime.llm_provider == "openai"
    assert runtime.llm_model == "gpt-4o-mini"
    assert runtime.llm_settings == {"temperature": 0.3}
    assert runtime.tts_provider == "cartesia"
    assert runtime.tts_model == "sonic-3.5"
    assert runtime.tts_voice == "voice-uuid"
    assert runtime.tts_settings == {"language": "hi"}
    assert runtime.live_tools_enabled is False
    assert runtime.transfer_enabled is False
    assert runtime.transfer_number == ""


def test_prefetch_carries_call_action_toggles():
    prefetch = {
        "source": "script_config",
        "route": "cascaded",
        "script_id": "xfer",
        "system_prompt": "hi",
        "cascade_live_tools": [
            {"name": "push_lead_data", "description": "save", "properties": {"x": {"type": "string"}}}
        ],
        "live_tools_enabled": True,
        "transfer_enabled": True,
        "transfer_number": "+919876543210",
        "extraction_schema": {},
    }
    runtime = sr._cascade_from_prefetch(prefetch)
    assert runtime.live_tools_enabled is True
    assert runtime.transfer_enabled is True
    assert runtime.transfer_number == "+919876543210"
    assert runtime.push_lead_data_schema is not None


def test_sonic3_as_voice_collapses_to_empty():
    prefetch = {
        "source": "script_config",
        "route": "cascaded",
        "script_id": "legacy",
        "system_prompt": "hi",
        "cascade_tts_provider": "cartesia",
        "cascade_tts_model": "sonic-3",
        "cascade_tts_voice": "sonic-3",
        "cascade_live_tools": [],
        "extraction_schema": {},
    }
    runtime = sr._cascade_from_prefetch(prefetch)
    assert runtime.tts_voice == ""


def test_module_path_gets_catalog_defaults():
    body = {"_pg": {"script_id": "prowave"}, "lead_name": "Sir"}
    runtime = sr.resolve_cascade_runtime(body)
    assert runtime.source == "module"
    assert runtime.stt_provider == catalog.default_provider("stt")
    assert runtime.llm_provider == catalog.default_provider("llm")
    assert runtime.tts_provider == catalog.default_provider("tts")
    assert runtime.stt_settings == {}
    assert runtime.llm_settings == {}
    assert runtime.tts_settings == {}
    assert runtime.tts_voice == ""
    assert runtime.live_tools_enabled is False
    assert runtime.transfer_enabled is False
    assert runtime.transfer_number == ""

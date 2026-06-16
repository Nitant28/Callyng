"""Unit tests for script_prefetch (no Postgres required)."""

from __future__ import annotations

import asyncio

import pytest

import script_prefetch as sp


@pytest.fixture(autouse=True)
def _clear_prefetch_registry():
    sp.PREFETCHED_CONFIGS.clear()
    yield
    sp.PREFETCHED_CONFIGS.clear()


def test_build_lead_dict_filters_metadata_keys():
    lead = {"name": "Satyam", "phone": "+919123866924"}
    meta = {
        "city": "Pune",
        "bhk": "2BHK",
        "City": "ignored",
        "../x": "bad",
        "9bad": "bad",
    }
    d = sp.build_lead_dict(lead, meta)
    assert d["lead_name"] == "Satyam"
    assert d["lead_phone"] == "+919123866924"
    assert d["lead_city"] == "Pune"
    assert d["bhk"] == "2BHK"
    assert "City" not in d
    assert "../x" not in d
    assert "9bad" not in d


def test_render_script_config_substitutes_templates():
    row = {
        "id": "00000000-0000-4000-8000-000000000099",
        "script_id": "pyramid_mr",
        "route": "sts",
        "version": 2,
        "system_instruction_template": "Hello $lead_name from $lead_city",
        "bootstrap_messages_json": [
            {"role": "user", "content": "Connected. Greet $lead_name."},
        ],
        "goodbye_markers": ["bye"],
        "gemini_model": "models/gemini-3.1-flash-live-preview",
        "gemini_voice": "Aoede",
        "gemini_language": "hi-IN",
        "gemini_temperature": 0.5,
        "vad_start_sensitivity": "HIGH",
        "vad_end_sensitivity": "LOW",
        "vad_silence_duration_ms": 800,
        "vad_prefix_padding_ms": 300,
        "cascade_stt_provider": "sarvam",
        "cascade_stt_model": "saarika:v2.5",
        "cascade_llm_provider": "groq",
        "cascade_llm_model": "llama-3.3-70b-versatile",
        "cascade_tts_provider": "cartesia",
        "cascade_tts_voice": "sonic-3",
        "cascade_live_tools": [],
        "extraction_schema": {"fields": {}},
        "lead_schema": {"fields": []},
        "normalization_rules": [],
        "outcome_event_map": {},
        "outcome_terminal": ["Interested"],
        "outcome_retry": ["Busy"],
        "outcome_callback": ["Callback_Requested"],
    }
    lead_dict = {"lead_name": "Asha", "lead_city": "Mumbai", "lead_phone": "+911"}
    cfg = sp.render_script_config(row, lead_dict, expected_route="sts")
    assert cfg["source"] == "script_config"
    assert cfg["system_instruction"] == "Hello Asha from Mumbai"
    assert cfg["system_prompt"] == "Hello Asha from Mumbai"
    assert cfg["bootstrap_messages"][0]["content"] == "Connected. Greet Asha."
    assert cfg["version"] == 2


def test_render_script_config_route_mismatch_raises():
    row = {"route": "cascaded", "system_instruction_template": "x"}
    with pytest.raises(ValueError, match="does not match"):
        sp.render_script_config(row, {}, expected_route="sts")


def test_sweep_stale_prefetched_configs():
    sp.register_prefetched_config("call-live", {"route": "sts"})
    sp.register_prefetched_config("call-done", {"route": "sts"})
    sp.register_prefetched_config("call-orphan", {"route": "sts"})

    class _Pool:
        async def fetch(self, _sql, keys):
            assert "call-live" in keys
            return [{"session_call_id": "call-done"}]

    async def _run():
        return await sp.sweep_stale_prefetched_configs(_Pool())

    n = asyncio.run(_run())
    assert n == 1
    assert "call-live" in sp.PREFETCHED_CONFIGS
    assert "call-done" not in sp.PREFETCHED_CONFIGS
    assert "call-orphan" in sp.PREFETCHED_CONFIGS


def test_register_and_pop_prefetched_config():
    sp.register_prefetched_config("sid-1", {"route": "sts"})
    assert sp.pop_prefetched_config("sid-1") == {"route": "sts"}
    assert sp.pop_prefetched_config("sid-1") is None

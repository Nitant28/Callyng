"""Unit tests for script_runtime (3-tier resolution)."""

from __future__ import annotations


from google.genai.types import EndSensitivity, StartSensitivity
from pipecat.transcriptions.language import Language

import script_runtime as sr


def _sts_prefetch(**overrides) -> dict:
    base = {
        "source": "script_config",
        "route": "sts",
        "script_id": "test_sts",
        "version": 3,
        "system_instruction": "Hello $lead_name",
        "bootstrap_messages": [{"role": "user", "content": "Greet $lead_name"}],
        "goodbye_markers": ["bye"],
        "gemini_model": "models/gemini-3.1-flash-live-preview",
        "gemini_voice": "Aoede",
        "gemini_language": "mr-IN",
        "gemini_temperature": 0.5,
        "vad_start_sensitivity": "HIGH",
        "vad_end_sensitivity": "LOW",
        "vad_silence_duration_ms": 800,
        "vad_prefix_padding_ms": 300,
        "extraction_schema": {"fields": {}},
    }
    base.update(overrides)
    return base


def test_parse_gemini_language():
    assert sr.parse_gemini_language("mr-IN") == Language.MR_IN
    assert sr.parse_gemini_language("hi_IN") == Language.HI_IN
    assert sr.parse_gemini_language("unknown") == Language.HI_IN


def test_build_gemini_vad():
    vad = sr.build_gemini_vad(
        {
            "vad_start_sensitivity": "HIGH",
            "vad_end_sensitivity": "LOW",
            "vad_silence_duration_ms": 900,
            "vad_prefix_padding_ms": 400,
        }
    )
    assert vad.start_sensitivity == StartSensitivity.START_SENSITIVITY_HIGH
    assert vad.end_sensitivity == EndSensitivity.END_SENSITIVITY_LOW
    assert vad.silence_duration_ms == 900
    assert vad.prefix_padding_ms == 400


def test_build_push_lead_data_schema():
    tools = [
        {
            "name": "push_lead_data",
            "description": "Save lead data",
            "properties": {
                "intent_status": {"type": "string", "description": "status"},
            },
            "required": ["intent_status"],
        }
    ]
    schema = sr.build_push_lead_data_schema(tools)
    assert schema is not None
    assert schema.name == "push_lead_data"
    assert schema.required == ["intent_status"]


def test_resolve_sts_runtime_prefetch_hit():
    body = {
        "_session_call_id": "call-1",
        "_prefetched_config": _sts_prefetch(system_instruction="Hi Rama"),
        "lead_name": "Rama",
    }
    runtime = sr.resolve_sts_runtime(body)
    assert runtime.source == "script_config"
    assert runtime.script_id == "test_sts"
    assert runtime.system_instruction == "Hi Rama"
    assert runtime.gemini_language == Language.MR_IN


def test_resolve_sts_runtime_prefetch_miss_module_fallback():
    body = {
        "_pg": {"script_id": "pyramid_mr"},
        "lead_name": "Test",
        "phone_number": "+911",
    }
    runtime = sr.resolve_sts_runtime(body)
    assert runtime.source == "module"
    assert runtime.script_id == "pyramid_mr"
    assert runtime.system_instruction
    assert "Diya" in runtime.system_instruction or "diya" in runtime.system_instruction.lower()


def test_resolve_sts_runtime_wrong_route_falls_back_to_module():
    body = {
        "_session_call_id": "call-2",
        "_prefetched_config": _sts_prefetch(route="cascaded", system_instruction="wrong"),
        "_pg": {"script_id": "pyramid_mr"},
        "lead_name": "Test",
    }
    runtime = sr.resolve_sts_runtime(body)
    assert runtime.source == "module"
    assert runtime.script_id == "pyramid_mr"


def test_prefetched_config_is_one_shot_per_ws_body():
    prefetch = _sts_prefetch(system_instruction="Once")
    body = {
        "_session_call_id": "call-3",
        "_prefetched_config": prefetch,
        "lead_name": "A",
    }
    first = sr.resolve_sts_runtime(body)
    assert first.source == "script_config"
    body["_pg"] = {"script_id": "pyramid_mr"}
    body.pop("_prefetched_config", None)
    second = sr.resolve_sts_runtime(body)
    assert second.source == "module"


def test_resolve_cascade_runtime_prefetch_hit():
    body = {
        "_session_call_id": "call-c",
        "_prefetched_config": {
            "source": "script_config",
            "route": "cascaded",
            "script_id": "prowave_db",
            "version": 1,
            "system_prompt": "Cascade hello",
            "cascade_stt_model": "saarika:v2.5",
            "cascade_llm_model": "llama-3.3-70b-versatile",
            "cascade_tts_voice": "voice-123",
            "cascade_live_tools": [],
            "extraction_schema": {"fields": {}},
        },
    }
    runtime = sr.resolve_cascade_runtime(body)
    assert runtime.source == "script_config"
    assert runtime.system_prompt == "Cascade hello"
    assert runtime.tts_voice == "voice-123"


def test_resolve_cascade_runtime_module_fallback():
    body = {"_pg": {"script_id": "prowave"}, "lead_name": "Sir"}
    runtime = sr.resolve_cascade_runtime(body)
    assert runtime.source == "module"
    assert runtime.script_id == "prowave"
    assert runtime.push_lead_data_schema is None


def test_build_post_call_snapshot_from_prefetch():
    prefetch = {
        "script_config_id": "00000000-0000-4000-8000-000000000099",
        "version": 4,
        "extraction_schema": {"mode": "fields", "fields": [{"name": "intent_status"}]},
        "normalization_rules": [{"field": "x"}],
        "outcome_event_map": {"Interested": "lead_qualified"},
        "outcome_terminal": ["Interested"],
        "outcome_retry": ["Busy"],
        "outcome_callback": ["Callback_Requested"],
    }
    wrapper = sr.build_post_call_snapshot_from_prefetch(prefetch)
    snap = wrapper["post_call_snapshot"]
    assert snap["script_config_id"] == "00000000-0000-4000-8000-000000000099"
    assert snap["version"] == 4
    assert snap["normalization_rules"] == [{"field": "x"}]
    assert snap["outcome_event_map"] == {"Interested": "lead_qualified"}


def test_build_post_call_snapshot_from_prefetch_override():
    prefetch = {
        "script_config_id": "abc",
        "version": 1,
        "extraction_schema": {"mode": "fields", "fields": []},
    }
    override = {"mode": "summary", "summary_prompt": "summarize"}
    wrapper = sr.build_post_call_snapshot_from_prefetch(
        prefetch, extraction_override=override
    )
    assert wrapper["post_call_snapshot"]["extraction_schema"] == override


def test_build_post_call_snapshot_from_runtime_module_defaults():
    runtime = sr.StsRuntime(
        script_id="pyramid_mr",
        source="module",
        system_instruction="x",
        bootstrap_messages=[],
        goodbye_markers=(),
        gemini_model="m",
        gemini_voice="v",
        gemini_language=Language.HI_IN,
        gemini_vad=sr.build_gemini_vad({}),
        gemini_temperature=0.5,
        extraction_schema={"mode": "fields", "fields": []},
    )
    snap = sr.build_post_call_snapshot_from_runtime(runtime)["post_call_snapshot"]
    assert snap["script_config_id"] is None
    assert snap["version"] is None
    assert snap["outcome_terminal"] == sr.DEFAULT_OUTCOME_TERMINAL
    assert snap["outcome_retry"] == sr.DEFAULT_OUTCOME_RETRY

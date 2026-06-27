"""Export module-based scripts into script_configs payloads."""

from __future__ import annotations

import importlib
from typing import Any

from google.genai.types import EndSensitivity, StartSensitivity
from pipecat.transcriptions.language import Language

from api.script_config_validation import validate_script_config_payload
from lead_context import LeadContext
from n8n_webhook import outcome_to_event
from script_runtime import (
    DEFAULT_OUTCOME_CALLBACK,
    DEFAULT_OUTCOME_RETRY,
    DEFAULT_OUTCOME_TERMINAL,
    _CASCADE_SCRIPT_ATTRS,
    _STS_SCRIPT_ATTRS,
)
from sts_scripts.lead_schema_pyramid import PYRAMID_LEAD_SCHEMA

TEMPLATE_CTX = LeadContext(
    lead_name="{lead_name}",
    lead_phone="{lead_phone}",
    lead_city="{lead_city}",
)


def _language_to_bcp47(lang: Language) -> str:
    mapping = {
        Language.HI_IN: "hi-IN",
        Language.MR_IN: "mr-IN",
        Language.EN_IN: "en-IN",
        Language.EN_US: "en-US",
        Language.EN_GB: "en-GB",
        Language.TA_IN: "ta-IN",
        Language.TE_IN: "te-IN",
        Language.KN_IN: "kn-IN",
        Language.BN_IN: "bn-IN",
        Language.GU_IN: "gu-IN",
        Language.PA_IN: "pa-IN",
    }
    return mapping.get(lang, "hi-IN")


def _start_label(value: StartSensitivity) -> str:
    return "HIGH" if value == StartSensitivity.START_SENSITIVITY_HIGH else "LOW"


def _end_label(value: EndSensitivity) -> str:
    return "HIGH" if value == EndSensitivity.END_SENSITIVITY_HIGH else "LOW"


def _default_normalization_rules() -> list[dict[str, Any]]:
    from sts_scripts.pyramid_extraction import PYRAMID_NORMALIZATION_RULES
    return PYRAMID_NORMALIZATION_RULES


def _default_outcome_event_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for value in DEFAULT_OUTCOME_TERMINAL + DEFAULT_OUTCOME_CALLBACK + DEFAULT_OUTCOME_RETRY:
        evt = outcome_to_event(value)
        if evt:
            out[value] = evt
    return out



def _base_payload(route: str, module_stem: str) -> dict[str, Any]:
    return {
        "script_id": module_stem,
        "route": route,
        "lead_schema": dict(PYRAMID_LEAD_SCHEMA),
        "normalization_rules": _default_normalization_rules(),
        "outcome_event_map": _default_outcome_event_map(),
        "outcome_terminal": list(DEFAULT_OUTCOME_TERMINAL),
        "outcome_retry": list(DEFAULT_OUTCOME_RETRY),
        "outcome_callback": list(DEFAULT_OUTCOME_CALLBACK),
        "active": True,
    }


def export_sts_module(module_stem: str) -> dict[str, Any]:
    mod = importlib.import_module(f"sts_scripts.{module_stem}")
    missing = [a for a in _STS_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(f"STS script {module_stem} missing attrs: {', '.join(missing)}")

    vad = mod.GEMINI_VAD
    payload = _base_payload("sts", module_stem)
    payload.update(
        {
            "system_instruction_template": mod.build_system_instruction(TEMPLATE_CTX),
            "bootstrap_messages_json": list(mod.build_bootstrap_messages(TEMPLATE_CTX)),
            "goodbye_markers": list(getattr(mod, "GOODBYE_HANGUP_MARKERS", ()) or []),
            "gemini_model": str(mod.GEMINI_MODEL),
            "gemini_voice": str(mod.GEMINI_VOICE),
            "gemini_language": _language_to_bcp47(mod.GEMINI_LANGUAGE),
            "gemini_temperature": float(mod.GEMINI_TEMPERATURE),
            "vad_start_sensitivity": _start_label(vad.start_sensitivity),
            "vad_end_sensitivity": _end_label(vad.end_sensitivity),
            "vad_silence_duration_ms": int(vad.silence_duration_ms or 800),
            "vad_prefix_padding_ms": int(vad.prefix_padding_ms or 300),
            "cascade_stt_provider": "sarvam",
            "cascade_stt_model": "saarika:v2.5",
            "cascade_llm_provider": "groq",
            "cascade_llm_model": "llama-3.3-70b-versatile",
            "cascade_tts_provider": "cartesia",
            "cascade_tts_voice": "sonic-3",
            "cascade_live_tools": [],
            "extraction_schema": dict(mod.EXTRACTION_SCHEMA),
            "lead_schema": dict(getattr(mod, "LEAD_SCHEMA", PYRAMID_LEAD_SCHEMA)),
        }
    )
    validate_script_config_payload(payload, partial=False)
    return payload


def export_cascade_module(module_stem: str) -> dict[str, Any]:
    mod = importlib.import_module(f"cascade_scripts.{module_stem}")
    missing = [a for a in _CASCADE_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(
            f"Cascade script {module_stem} missing attrs: {', '.join(missing)}"
        )

    payload = _base_payload("cascaded", module_stem)
    payload.update(
        {
            "system_instruction_template": mod.build_system_prompt(TEMPLATE_CTX),
            "bootstrap_messages_json": [],
            "goodbye_markers": [],
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
            "cascade_live_tools": list(getattr(mod, "CASCADE_LIVE_TOOLS", [])),
            "extraction_schema": dict(mod.EXTRACTION_SCHEMA),
            "lead_schema": dict(getattr(mod, "LEAD_SCHEMA", PYRAMID_LEAD_SCHEMA)),
        }
    )
    validate_script_config_payload(payload, partial=False)
    return payload


def export_module(route: str, module_stem: str) -> dict[str, Any]:
    if route == "sts":
        return export_sts_module(module_stem)
    if route == "cascaded":
        return export_cascade_module(module_stem)
    raise ValueError(f"Unsupported route: {route!r}")

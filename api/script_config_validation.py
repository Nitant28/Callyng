"""Validation, templates, and revision snapshots for script_configs admin API."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from post_call_extract import validate_extraction_schema as _validate_extraction_schema_base

_SCRIPT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VALID_ROUTES = frozenset({"sts", "cascaded"})
_LEGACY_ROUTE_ALIASES = {"cascade": "cascaded"}
_VALID_FIELD_TYPES = frozenset({"string", "enum", "boolean", "datetime"})

_JSON_DICT_FIELDS = ("extraction_schema", "lead_schema", "outcome_event_map")
_JSON_LIST_FIELDS = (
    "bootstrap_messages_json",
    "goodbye_markers",
    "cascade_live_tools",
    "normalization_rules",
    "outcome_terminal",
    "outcome_retry",
    "outcome_callback",
    "outcome_bot_follow_up",
)

_SNAPSHOT_COLUMNS = (
    "script_id",
    "route",
    "gemini_model",
    "gemini_voice",
    "gemini_language",
    "gemini_temperature",
    "vad_start_sensitivity",
    "vad_end_sensitivity",
    "vad_silence_duration_ms",
    "vad_prefix_padding_ms",
    "system_instruction_template",
    "bootstrap_messages_json",
    "goodbye_markers",
    "cascade_stt_provider",
    "cascade_stt_model",
    "cascade_llm_provider",
    "cascade_llm_model",
    "cascade_tts_provider",
    "cascade_tts_voice",
    "cascade_live_tools",
    "extraction_schema",
    "lead_schema",
    "normalization_rules",
    "outcome_terminal",
    "outcome_retry",
    "outcome_callback",
    "outcome_bot_follow_up",
    "active",
    "version",
)

_DEFAULT_OUTCOME_TERMINAL = ["Interested", "Not_Interested"]
_DEFAULT_OUTCOME_RETRY = ["Busy", "Unknown", "Wrong_Requirement"]
_DEFAULT_OUTCOME_CALLBACK = ["Callback_Requested", "Early_Disconnect"]

_DEFAULT_EXTRACTION_SCHEMA: dict[str, Any] = {
    "mode": "fields",
    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": [
                "Interested",
                "Not_Interested",
                "Busy",
                "Callback_Requested",
                "Wrong_Requirement",
                "Unknown",
            ],
            "required": True,
            "description": "Call outcome intent.",
        },
        {
            "key": "caller_notes",
            "type": "string",
            "required": False,
            "description": "Other useful facts, or the literal NULL.",
        },
    ],
    "extraction_rules": (
        "Infer only what the transcript supports. "
        "Reply with ONE JSON object matching the field keys."
    ),
}


def validate_script_id(script_id: str) -> None:
    if not _SCRIPT_ID_RE.fullmatch(script_id or ""):
        raise ValueError(
            "script_id must match ^[a-z][a-z0-9_]*$ (lowercase snake_case)"
        )


def normalize_route(route: str) -> str:
    """Map legacy route aliases (e.g. cascade) to canonical DB values."""
    key = (route or "").strip().lower()
    return _LEGACY_ROUTE_ALIASES.get(key, key)


def _ensure_json_dict(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{field_name} must be a dict, invalid JSON string"
            ) from exc
        if isinstance(parsed, str):
            raise ValueError(
                f"{field_name} appears double-stringified; pass a dict, not a JSON-encoded string"
            )
        if not isinstance(parsed, dict):
            raise ValueError(
                f"{field_name} must be a dict, got {type(parsed).__name__}"
            )
        return parsed
    raise ValueError(f"{field_name} must be a dict, got {type(value).__name__}")


def _ensure_json_list(value: Any, field_name: str) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{field_name} must be a list, invalid JSON string"
            ) from exc
        if isinstance(parsed, str):
            raise ValueError(
                f"{field_name} appears double-stringified; pass a list, not a JSON-encoded string"
            )
        if not isinstance(parsed, list):
            raise ValueError(
                f"{field_name} must be a list, got {type(parsed).__name__}"
            )
        return parsed
    raise ValueError(f"{field_name} must be a list, got {type(value).__name__}")


def normalize_script_config_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize route aliases and coerce JSON fields before validation/DB write."""
    out = dict(data)
    if "route" in out and out["route"] is not None:
        out["route"] = normalize_route(str(out["route"]))
    for field in _JSON_DICT_FIELDS:
        if field in out and out[field] is not None:
            out[field] = _ensure_json_dict(out[field], field)
    for field in _JSON_LIST_FIELDS:
        if field in out and out[field] is not None:
            out[field] = _ensure_json_list(out[field], field)
    return out


def validate_route(route: str) -> None:
    if normalize_route(route) not in _VALID_ROUTES:
        raise ValueError(f"route must be one of {sorted(_VALID_ROUTES)!r}")


def validate_extraction_schema(schema: dict[str, Any]) -> None:
    """Raise ValueError if schema structure or fields are invalid."""
    _validate_extraction_schema_base(schema)
    mode = schema.get("mode")
    if mode not in ("fields", "both"):
        return

    fields = schema.get("fields")
    if not isinstance(fields, list):
        return

    seen_keys: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("each extraction_schema.fields entry must be a dict")
        key = field.get("key")
        if not key or not isinstance(key, str):
            raise ValueError("each field must have a string 'key'")
        if key in seen_keys:
            raise ValueError(f"duplicate field key: {key!r}")
        seen_keys.add(key)

        ftype = field.get("type", "string")
        if ftype not in _VALID_FIELD_TYPES:
            raise ValueError(
                f"field {key!r} type must be one of {sorted(_VALID_FIELD_TYPES)!r}"
            )
        if ftype == "enum":
            values = field.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(f"enum field {key!r} must have non-empty 'values'")


def _intent_status_values(extraction_schema: dict[str, Any]) -> list[str]:
    fields = extraction_schema.get("fields") or []
    for field in fields:
        if isinstance(field, dict) and field.get("key") == "intent_status":
            values = field.get("values")
            if isinstance(values, list) and values:
                return [str(v) for v in values]
            raise ValueError(
                "extraction_schema must include intent_status enum with non-empty values"
            )
    raise ValueError(
        "extraction_schema.fields must include intent_status for non-summary mode"
    )


def validate_outcome_mapping(
    extraction_schema: dict[str, Any],
    outcome_terminal: list[Any],
    outcome_retry: list[Any],
    outcome_callback: list[Any],
    outcome_bot_follow_up: list[Any],
) -> None:
    """Ensure intent_status enum values map exactly once across outcome buckets."""
    if extraction_schema.get("mode") == "summary":
        return

    intent_values = _intent_status_values(extraction_schema)
    terminal = [str(v) for v in (outcome_terminal or [])]
    retry = [str(v) for v in (outcome_retry or [])]
    callback = [str(v) for v in (outcome_callback or [])]
    bot_follow_up = [str(v) for v in (outcome_bot_follow_up or [])]

    for label, bucket in (
        ("outcome_terminal", terminal),
        ("outcome_retry", retry),
        ("outcome_callback", callback),
        ("outcome_bot_follow_up", bot_follow_up),
    ):
        if len(bucket) != len(set(bucket)):
            raise ValueError(f"{label} contains duplicate values")

    terminal_set = set(terminal)
    retry_set = set(retry)
    callback_set = set(callback)
    bot_follow_up_set = set(bot_follow_up)

    if (
        terminal_set & retry_set
        or terminal_set & callback_set
        or terminal_set & bot_follow_up_set
        or retry_set & callback_set
        or retry_set & bot_follow_up_set
        or callback_set & bot_follow_up_set
    ):
        raise ValueError(
            "outcome_terminal, outcome_retry, outcome_callback, and "
            "outcome_bot_follow_up must not overlap"
        )

    bucket_union = terminal_set | retry_set | callback_set | bot_follow_up_set
    intent_set = set(intent_values)

    missing = intent_set - bucket_union
    if missing:
        raise ValueError(
            f"intent_status values not mapped to any outcome bucket: {sorted(missing)}"
        )

    extra = bucket_union - intent_set
    if extra:
        raise ValueError(
            f"outcome bucket values not in intent_status enum: {sorted(extra)}"
        )

    for value in intent_values:
        count = (
            (1 if value in terminal_set else 0)
            + (1 if value in retry_set else 0)
            + (1 if value in callback_set else 0)
            + (1 if value in bot_follow_up_set else 0)
        )
        if count != 1:
            raise ValueError(
                f"intent_status value {value!r} must appear in exactly one outcome bucket"
            )


def validate_script_config_payload(data: dict[str, Any], *, partial: bool = False) -> None:
    """Validate create or merged patch payload before DB write."""
    normalized = normalize_script_config_payload(data)
    data.clear()
    data.update(normalized)

    if not partial or "script_id" in data:
        validate_script_id(str(data.get("script_id") or ""))
    if not partial or "route" in data:
        validate_route(str(data.get("route") or ""))

    schema = data.get("extraction_schema")
    if schema is not None:
        validate_extraction_schema(schema)
        validate_outcome_mapping(
            schema,
            data.get("outcome_terminal") or _DEFAULT_OUTCOME_TERMINAL,
            data.get("outcome_retry") or _DEFAULT_OUTCOME_RETRY,
            data.get("outcome_callback") or _DEFAULT_OUTCOME_CALLBACK,
            data.get("outcome_bot_follow_up") or [],
        )
    elif not partial:
        raise ValueError("extraction_schema is required")


def build_config_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Build revision snapshot from a script_configs row or merged dict."""
    snap: dict[str, Any] = {}
    for col in _SNAPSHOT_COLUMNS:
        if col in row:
            snap[col] = row[col]
    return snap


def default_template(route: str) -> dict[str, Any]:
    """Return a create-ready template body for the given route."""
    validate_route(route)
    
    from lead_context import LeadContext
    from sts_scripts.pyramid_bilingual import (
        GEMINI_MODEL, GEMINI_VOICE, GEMINI_LANGUAGE, GEMINI_TEMPERATURE,
        GEMINI_VAD, GOODBYE_HANGUP_MARKERS,
        build_bootstrap_messages, build_system_instruction,
    )
    from sts_scripts.pyramid_extraction import PYRAMID_EXTRACTION_SCHEMA, PYRAMID_NORMALIZATION_RULES

    ctx = LeadContext(
        lead_name="{lead_name}",
        lead_phone="{lead_phone}",
        lead_city="{lead_city}"
    )

    base: dict[str, Any] = {
        "script_id": "pyramid_bilingual",
        "route": route,
        "gemini_model": GEMINI_MODEL,
        "gemini_voice": GEMINI_VOICE,
        "gemini_language": GEMINI_LANGUAGE.value if hasattr(GEMINI_LANGUAGE, "value") else str(GEMINI_LANGUAGE),
        "gemini_temperature": GEMINI_TEMPERATURE,
        "vad_start_sensitivity": GEMINI_VAD.start_sensitivity.name.replace("START_SENSITIVITY_", ""),
        "vad_end_sensitivity": GEMINI_VAD.end_sensitivity.name.replace("END_SENSITIVITY_", ""),
        "vad_silence_duration_ms": GEMINI_VAD.silence_duration_ms,
        "vad_prefix_padding_ms": GEMINI_VAD.prefix_padding_ms,
        "system_instruction_template": build_system_instruction(ctx),
        "bootstrap_messages_json": build_bootstrap_messages(ctx),
        "goodbye_markers": list(GOODBYE_HANGUP_MARKERS),
        "cascade_stt_provider": "sarvam",
        "cascade_stt_model": "saarika:v2.5",
        "cascade_llm_provider": "groq",
        "cascade_llm_model": "llama-3.3-70b-versatile",
        "cascade_tts_provider": "cartesia",
        "cascade_tts_voice": "sonic-3",
        "cascade_live_tools": [],
        "extraction_schema": deepcopy(PYRAMID_EXTRACTION_SCHEMA),
        "lead_schema": {"fields": []},
        "normalization_rules": PYRAMID_NORMALIZATION_RULES,
        "outcome_event_map": {
            "Interested": "lead_qualified",
            "Not_Interested": "lead_not_interested",
            "Callback_Requested": "lead_callback",
        },
        "outcome_terminal": list(_DEFAULT_OUTCOME_TERMINAL),
        "outcome_retry": list(_DEFAULT_OUTCOME_RETRY),
        "outcome_callback": list(_DEFAULT_OUTCOME_CALLBACK),
        "outcome_bot_follow_up": list(_DEFAULT_OUTCOME_BOT_FOLLOW_UP),
        "active": True,
    }

    if route == "cascaded":
        base["system_instruction_template"] = (
            "You are a voice agent calling {lead_name}. "
            "Use short responses. Project: example property in {lead_city}."
        )

    return base

"""Validation, templates, and revision snapshots for script_configs admin API."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lead_upload.normaliser import normalise_phone
from post_call_extract import validate_extraction_schema as _validate_extraction_schema_base
from providers import catalog

_SCRIPT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VALID_ROUTES = frozenset({"sts", "cascaded"})
_LEGACY_ROUTE_ALIASES = {"cascade": "cascaded"}
_VALID_FIELD_TYPES = frozenset({"string", "enum", "boolean", "datetime"})

_JSON_DICT_FIELDS = (
    "extraction_schema",
    "lead_schema",
    "outcome_event_map",
    "cascade_stt_settings",
    "cascade_llm_settings",
    "cascade_tts_settings",
)
_JSON_LIST_FIELDS = (
    "bootstrap_messages_json",
    "goodbye_markers",
    "cascade_live_tools",
    "normalization_rules",
    "outcome_terminal",
    "outcome_retry",
    "outcome_callback",
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
    "cascade_tts_model",
    "cascade_stt_settings",
    "cascade_llm_settings",
    "cascade_tts_settings",
    "cascade_live_tools",
    "transfer_enabled",
    "transfer_number",
    "live_tools_enabled",
    "extraction_schema",
    "lead_schema",
    "normalization_rules",
    "outcome_event_map",
    "outcome_terminal",
    "outcome_retry",
    "outcome_callback",
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
            "description": "Other useful facts, or null.",
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
) -> None:
    """Ensure intent_status enum values map exactly once across outcome buckets."""
    if extraction_schema.get("mode") == "summary":
        return

    intent_values = _intent_status_values(extraction_schema)
    terminal = [str(v) for v in (outcome_terminal or [])]
    retry = [str(v) for v in (outcome_retry or [])]
    callback = [str(v) for v in (outcome_callback or [])]

    for label, bucket in (
        ("outcome_terminal", terminal),
        ("outcome_retry", retry),
        ("outcome_callback", callback),
    ):
        if len(bucket) != len(set(bucket)):
            raise ValueError(f"{label} contains duplicate values")

    terminal_set = set(terminal)
    retry_set = set(retry)
    callback_set = set(callback)

    if terminal_set & retry_set or terminal_set & callback_set or retry_set & callback_set:
        raise ValueError(
            "outcome_terminal, outcome_retry, and outcome_callback must not overlap"
        )

    bucket_union = terminal_set | retry_set | callback_set
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
        )
        if count != 1:
            raise ValueError(
                f"intent_status value {value!r} must appear in exactly one outcome bucket"
            )


def _validate_cascade_field_value(field: catalog.Field, value: Any, *, role: str, model: str) -> Any:
    label = f"cascade_{role}_settings.{field.key}"
    if field.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{label}: must be a boolean for model {model!r}")
        return value
    if field.type == "number":
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: must be a number for model {model!r}") from exc
        if field.min is not None and num < field.min:
            raise ValueError(
                f"{label}: {num} is below minimum {field.min} for model {model!r}"
            )
        if field.max is not None and num > field.max:
            raise ValueError(
                f"{label}: {num} is above maximum {field.max} for model {model!r}"
            )
        return num
    if field.type == "select":
        text = str(value)
        if field.options is not None and text not in field.options:
            raise ValueError(
                f"{label}: {text!r} not in {list(field.options)} for model {model!r}"
            )
        return text
    if field.required and (value is None or str(value).strip() == ""):
        raise ValueError(f"{label}: is required for model {model!r}")
    return value


def _validate_cascade_role_settings(
    *,
    kind: catalog.Kind,
    provider: str,
    model: str,
    settings: dict[str, Any],
) -> None:
    mspec = catalog.get_model(kind, provider, model)
    allowed = mspec.field_keys
    unknown = sorted(set(settings.keys()) - allowed)
    if unknown:
        raise ValueError(
            f"cascade_{kind}_settings: unknown keys {unknown} for model {model!r}"
        )
    field_map = {f.key: f for f in mspec.fields}
    for key, value in settings.items():
        field = field_map.get(key)
        if field is None:
            continue
        _validate_cascade_field_value(field, value, role=kind, model=model)
        if field.required and (value is None or str(value).strip() == ""):
            raise ValueError(
                f"cascade_{kind}_settings.{key}: is required for model {model!r}"
            )


def validate_cascade_config(data: dict[str, Any]) -> None:
    """Validate cascade provider/model/settings when route is cascaded."""
    if normalize_route(str(data.get("route") or "")) != "cascaded":
        return

    roles: tuple[tuple[catalog.Kind, str, str, str], ...] = (
        ("stt", "cascade_stt_provider", "cascade_stt_model", "cascade_stt_settings"),
        ("llm", "cascade_llm_provider", "cascade_llm_model", "cascade_llm_settings"),
        ("tts", "cascade_tts_provider", "cascade_tts_model", "cascade_tts_settings"),
    )
    for kind, provider_key, model_key, settings_key in roles:
        raw_provider = str(data.get(provider_key) or "").strip()
        raw_model = str(data.get(model_key) or "").strip()
        provider = raw_provider or catalog.default_provider(kind)
        model = raw_model or catalog.default_model(kind, provider)

        if raw_provider:
            catalog.get_provider(kind, raw_provider)
        if raw_model:
            catalog.get_model(kind, provider, raw_model)

        settings = data.get(settings_key)
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise ValueError(f"{settings_key} must be a JSON object")
        _validate_cascade_role_settings(
            kind=kind,
            provider=provider,
            model=model,
            settings=settings,
        )

    _validate_cascade_call_actions(data)


def _as_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return bool(val)
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _validate_cascade_call_actions(data: dict[str, Any]) -> None:
    if _as_bool(data.get("transfer_enabled")):
        e164 = normalise_phone(str(data.get("transfer_number") or ""))
        if not e164:
            raise ValueError(
                "transfer_number must be a valid phone number when transfer_enabled is true"
            )
        data["transfer_number"] = e164
    if _as_bool(data.get("live_tools_enabled")):
        tools = data.get("cascade_live_tools")
        if not isinstance(tools, list) or not tools:
            raise ValueError(
                "cascade_live_tools must be a non-empty list when live_tools_enabled is true"
            )
        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                raise ValueError(f"cascade_live_tools[{i}] must be an object")
            name = str(tool.get("name") or "").strip()
            description = str(tool.get("description") or "").strip()
            if not name:
                raise ValueError(f"cascade_live_tools[{i}].name is required")
            if not description:
                raise ValueError(f"cascade_live_tools[{i}].description is required")
            props = tool.get("properties")
            if props is not None and not isinstance(props, dict):
                raise ValueError(
                    f"cascade_live_tools[{i}].properties must be an object"
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

    validate_cascade_config(data)

    schema = data.get("extraction_schema")
    if schema is not None:
        validate_extraction_schema(schema)
        validate_outcome_mapping(
            schema,
            data.get("outcome_terminal") or _DEFAULT_OUTCOME_TERMINAL,
            data.get("outcome_retry") or _DEFAULT_OUTCOME_RETRY,
            data.get("outcome_callback") or _DEFAULT_OUTCOME_CALLBACK,
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
        "cascade_stt_model": "saaras:v3",
        "cascade_llm_provider": "groq",
        "cascade_llm_model": "openai/gpt-oss-120b",
        "cascade_tts_provider": "cartesia",
        "cascade_tts_voice": "",
        "cascade_tts_model": "sonic-3.5",
        "cascade_stt_settings": {},
        "cascade_llm_settings": {},
        "cascade_tts_settings": {},
        "cascade_live_tools": [],
        "transfer_enabled": False,
        "transfer_number": None,
        "live_tools_enabled": False,
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
        "active": True,
    }

    if route == "cascaded":
        from cascade_scripts.cms_default import (
            DEFAULT_CASCADE_BOOTSTRAP,
            DEFAULT_CASCADE_SYSTEM_INSTRUCTION,
            default_cascade_live_tools,
        )

        base["script_id"] = "cascade_outbound"
        base["system_instruction_template"] = DEFAULT_CASCADE_SYSTEM_INSTRUCTION
        base["bootstrap_messages_json"] = [dict(m) for m in DEFAULT_CASCADE_BOOTSTRAP]
        base.update(catalog.default_cascade_boilerplate())
        base["live_tools_enabled"] = True
        base["cascade_live_tools"] = default_cascade_live_tools()
        base["transfer_enabled"] = False
        base["transfer_number"] = None

    return base

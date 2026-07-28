"""3-tier script resolution: prefetch → _pg.script_id → env module."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from google.genai.types import EndSensitivity, StartSensitivity
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.google.gemini_live.llm import GeminiVADParams
from pipecat.transcriptions.language import Language

from lead_context import LeadContext
from background_tasks import spawn_background_task


def _log_prompt_summary(system_instruction: str, bootstrap_messages: list) -> None:
    """Info-level size/hash only; full bodies at debug to avoid event-loop stalls."""
    try:
        text = system_instruction or ""
        digest = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8]
        logger.info(
            "[prompt] system_instruction len={} hash={}",
            len(text),
            digest,
        )
        logger.debug("[prompt] system_instruction for call ->\n{}", text)
        for idx, msg in enumerate(bootstrap_messages or []):
            content = msg.get("content") if isinstance(msg, dict) else str(msg)
            content_s = content if isinstance(content, str) else str(content)
            logger.info(
                "[prompt] bootstrap[{}] len={}",
                idx,
                len(content_s),
            )
            logger.debug("[prompt] bootstrap[{}] -> {}", idx, content_s)
    except Exception:
        logger.debug("[prompt] Failed to log bootstrap messages", exc_info=True)

_STS_SCRIPT_ATTRS = (
    "build_system_instruction",
    "build_bootstrap_messages",
    "GOODBYE_HANGUP_MARKERS",
    "GEMINI_MODEL",
    "GEMINI_VOICE",
    "GEMINI_LANGUAGE",
    "GEMINI_VAD",
    "GEMINI_TEMPERATURE",
    "EXTRACTION_SCHEMA",
)

_CASCADE_SCRIPT_ATTRS = (
    "build_system_prompt",
    "EXTRACTION_SCHEMA",
)

_DEFAULT_CASCADE_STT_MODEL = "saarika:v2.5"
_DEFAULT_CASCADE_LLM_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_CASCADE_TTS_VOICE_ENV = "CARTESIA_VOICE_ID"

_BCP47_TO_LANGUAGE: dict[str, Language] = {
    "hi-in": Language.HI_IN,
    "mr-in": Language.MR_IN,
    "en-in": Language.EN_IN,
    "en-us": Language.EN_US,
    "en-gb": Language.EN_GB,
    "ta-in": Language.TA_IN,
    "te-in": Language.TE_IN,
    "kn-in": Language.KN_IN,
    "bn-in": Language.BN_IN,
    "gu-in": Language.GU_IN,
    "pa-in": Language.PA_IN,
}

_START_SENSITIVITY = {
    "HIGH": StartSensitivity.START_SENSITIVITY_HIGH,
    "LOW": StartSensitivity.START_SENSITIVITY_LOW,
}

_END_SENSITIVITY = {
    "HIGH": EndSensitivity.END_SENSITIVITY_HIGH,
    "LOW": EndSensitivity.END_SENSITIVITY_LOW,
}

DEFAULT_OUTCOME_TERMINAL = ["Interested", "Not_Interested"]
DEFAULT_OUTCOME_RETRY = ["Busy", "Unknown", "Wrong_Requirement"]
DEFAULT_OUTCOME_CALLBACK = ["Callback_Requested", "Early_Disconnect"]


@dataclass(frozen=True)
class PostCallSnapshot:
    script_config_id: str | None
    version: int | None
    extraction_schema: dict[str, Any]
    normalization_rules: list[Any]
    outcome_event_map: dict[str, str]
    outcome_terminal: list[str]
    outcome_retry: list[str]
    outcome_callback: list[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PostCallSnapshot:
        version = raw.get("version")
        return cls(
            script_config_id=raw.get("script_config_id"),
            version=int(version) if version is not None else None,
            extraction_schema=dict(raw.get("extraction_schema") or {}),
            normalization_rules=list(raw.get("normalization_rules") or []),
            outcome_event_map={
                str(k): str(v)
                for k, v in (raw.get("outcome_event_map") or {}).items()
            },
            outcome_terminal=list(raw.get("outcome_terminal") or DEFAULT_OUTCOME_TERMINAL),
            outcome_retry=list(raw.get("outcome_retry") or DEFAULT_OUTCOME_RETRY),
            outcome_callback=list(raw.get("outcome_callback") or DEFAULT_OUTCOME_CALLBACK),
        )


def parse_post_call_snapshot(call_data: Any) -> dict[str, Any] | None:
    """Extract ``post_call_snapshot`` from ``call_logs.call_data``."""
    if call_data is None:
        return None
    if isinstance(call_data, str):
        try:
            call_data = json.loads(call_data)
        except json.JSONDecodeError:
            return None
    if not isinstance(call_data, dict):
        return None
    snap = call_data.get("post_call_snapshot")
    if not isinstance(snap, dict):
        return None
    if not snap.get("extraction_schema"):
        return None
    return snap


def get_default_post_call_snapshot(extraction_schema: dict[str, Any]) -> dict[str, Any]:
    """Snapshot-shaped dict from live schema only (fallback when row has no snapshot)."""
    return build_post_call_snapshot(extraction_schema=extraction_schema)[
        "post_call_snapshot"
    ]


def outcome_buckets(
    snapshot: dict[str, Any] | None,
) -> tuple[set[str], set[str], set[str]]:
    """Return (terminal, retry, callback) outcome sets from snapshot or defaults."""
    if snapshot:
        terminal = set(snapshot.get("outcome_terminal") or DEFAULT_OUTCOME_TERMINAL)
        retry = set(snapshot.get("outcome_retry") or DEFAULT_OUTCOME_RETRY)
        callback = set(snapshot.get("outcome_callback") or DEFAULT_OUTCOME_CALLBACK)
    else:
        terminal = set(DEFAULT_OUTCOME_TERMINAL)
        retry = set(DEFAULT_OUTCOME_RETRY)
        callback = set(DEFAULT_OUTCOME_CALLBACK)
    return terminal, retry, callback


@dataclass(frozen=True)
class StsRuntime:
    script_id: str
    source: str
    system_instruction: str
    bootstrap_messages: list[dict[str, Any]]
    goodbye_markers: tuple[str, ...]
    gemini_model: str
    gemini_voice: str
    gemini_language: Language
    gemini_vad: GeminiVADParams
    gemini_temperature: float
    extraction_schema: dict[str, Any]
    gemini_enable_affective_dialog: bool = False
    module_name: str = ""


@dataclass(frozen=True)
class CascadeRuntime:
    script_id: str
    source: str
    system_prompt: str
    extraction_schema: dict[str, Any]
    stt_model: str
    llm_model: str
    tts_voice: str
    push_lead_data_schema: FunctionSchema | None
    module_name: str = ""


def parse_gemini_language(code: str) -> Language:
    key = (code or "").strip().lower().replace("_", "-")
    return _BCP47_TO_LANGUAGE.get(key, Language.HI_IN)


def _safe_int(val: Any, default: int, *, field: str) -> int:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid {}={!r}; using default {}", field, val, default
        )
        return default


def _safe_float(val: Any, default: float, *, field: str) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid {}={!r}; using default {}", field, val, default
        )
        return default


def build_gemini_vad(config: dict[str, Any]) -> GeminiVADParams:
    start_key = str(config.get("vad_start_sensitivity") or "HIGH").upper()
    end_key = str(config.get("vad_end_sensitivity") or "LOW").upper()
    return GeminiVADParams(
        start_sensitivity=_START_SENSITIVITY.get(
            start_key, StartSensitivity.START_SENSITIVITY_HIGH
        ),
        end_sensitivity=_END_SENSITIVITY.get(
            end_key, EndSensitivity.END_SENSITIVITY_LOW
        ),
        silence_duration_ms=_safe_int(
            config.get("vad_silence_duration_ms") or 800,
            800,
            field="vad_silence_duration_ms",
        ),
        prefix_padding_ms=_safe_int(
            config.get("vad_prefix_padding_ms") or 300,
            300,
            field="vad_prefix_padding_ms",
        ),
    )


def build_push_lead_data_schema(tools: list[Any]) -> FunctionSchema | None:
    if not isinstance(tools, list):
        return None
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("name") != "push_lead_data":
            continue
        properties = tool.get("properties")
        if not isinstance(properties, dict):
            continue
        required = tool.get("required")
        if not isinstance(required, list):
            required = []
        description = str(
            tool.get("description")
            or "Call this before ending every call to save lead qualification data."
        )
        return FunctionSchema(
            name="push_lead_data",
            description=description,
            properties=properties,
            required=required,
        )
    return None


def _coerce_extraction_override(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def build_post_call_snapshot(
    *,
    extraction_schema: dict[str, Any],
    script_config_id: str | None = None,
    version: int | None = None,
    normalization_rules: list[Any] | None = None,
    outcome_event_map: dict[str, Any] | None = None,
    outcome_terminal: list[str] | None = None,
    outcome_retry: list[str] | None = None,
    outcome_callback: list[str] | None = None,
) -> dict[str, Any]:
    """Wrapper dict for ``call_logs.call_data`` JSONB merge."""
    return {
        "post_call_snapshot": {
            "script_config_id": script_config_id,
            "version": version,
            "extraction_schema": extraction_schema,
            "normalization_rules": list(normalization_rules or []),
            "outcome_event_map": dict(outcome_event_map or {}),
            "outcome_terminal": list(outcome_terminal or DEFAULT_OUTCOME_TERMINAL),
            "outcome_retry": list(outcome_retry or DEFAULT_OUTCOME_RETRY),
            "outcome_callback": list(outcome_callback or DEFAULT_OUTCOME_CALLBACK),
        }
    }


def build_post_call_snapshot_from_prefetch(
    prefetch: dict[str, Any],
    extraction_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    override = _coerce_extraction_override(extraction_override)
    extraction = (
        override
        if override is not None
        else dict(prefetch.get("extraction_schema") or {})
    )
    script_config_id = prefetch.get("script_config_id")
    version = prefetch.get("version")
    return build_post_call_snapshot(
        script_config_id=str(script_config_id) if script_config_id else None,
        version=int(version) if version is not None else None,
        extraction_schema=extraction,
        normalization_rules=list(prefetch.get("normalization_rules") or []),
        outcome_event_map=dict(prefetch.get("outcome_event_map") or {}),
        outcome_terminal=list(prefetch.get("outcome_terminal") or DEFAULT_OUTCOME_TERMINAL),
        outcome_retry=list(prefetch.get("outcome_retry") or DEFAULT_OUTCOME_RETRY),
        outcome_callback=list(prefetch.get("outcome_callback") or DEFAULT_OUTCOME_CALLBACK),
    )


def build_post_call_snapshot_from_runtime(
    runtime: StsRuntime | CascadeRuntime,
    extraction_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    override = _coerce_extraction_override(extraction_override)
    extraction = (
        override if override is not None else dict(runtime.extraction_schema)
    )
    return build_post_call_snapshot(
        script_config_id=None,
        version=None,
        extraction_schema=extraction,
    )


async def maybe_write_post_call_snapshot(
    session_call_id: str | None,
    runtime: StsRuntime | CascadeRuntime,
    pg: dict[str, Any],
) -> None:
    """Module-path calls: patch snapshot at WS connect if dialer did not write one."""
    if not session_call_id or runtime.source != "module":
        return
    try:
        from db import postgres as pg_db

        pool = pg_db.get_pool()
    except Exception as exc:
        logger.warning("post_call_snapshot skipped (no pool): {}", exc)
        return

    snapshot = build_post_call_snapshot_from_runtime(
        runtime,
        extraction_override=pg.get("extraction_schema_override"),
    )
    try:
        patched = await pg_db.patch_call_log_post_call_snapshot(
            pool, session_call_id, snapshot
        )
        if patched:
            logger.debug(
                "post_call_snapshot written for session={} script={}",
                session_call_id,
                runtime.script_id,
            )
    except Exception as exc:
        logger.warning(
            "post_call_snapshot patch failed for {}: {}",
            session_call_id,
            exc,
        )


def schedule_post_call_snapshot_write(
    session_call_id: str | None,
    runtime: StsRuntime | CascadeRuntime,
    pg: dict[str, Any],
) -> None:
    """Fire-and-forget snapshot write for module-path bots."""
    if not session_call_id or runtime.source != "module":
        return

    async def _run() -> None:
        try:
            from call_transcript import _pg_write

            await _pg_write(
                maybe_write_post_call_snapshot(session_call_id, runtime, pg)
            )
        except Exception as exc:
            logger.warning("post_call_snapshot schedule failed: {}", exc)

    coro = _run()
    try:
        spawn_background_task(coro, "post_call_snapshot")
    except RuntimeError:
        coro.close()  # prevent "coroutine was never awaited" warning


def _load_sts_script(script_id_override: str | None = None) -> ModuleType:
    raw = (script_id_override or os.getenv("STS_SCRIPT") or "pyramid_mr").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", raw):
        raise ValueError(
            f"Invalid STS_SCRIPT={raw!r}; use a snake_case module name under sts_scripts/"
        )
    mod_name = f"sts_scripts.{raw}"
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        logger.error("Failed to import STS script {}: {}", mod_name, exc)
        raise
    missing = [a for a in _STS_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(f"STS script {mod_name} missing: {', '.join(missing)}")
    return mod


def _load_cascade_script(script_id_override: str | None = None) -> ModuleType:
    raw = (script_id_override or os.getenv("CASCADE_SCRIPT") or "prowave").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", raw):
        raise ValueError(
            f"Invalid CASCADE_SCRIPT={raw!r}; use a snake_case module under cascade_scripts/"
        )
    mod_name = f"cascade_scripts.{raw}"
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        logger.error("Failed to import cascade script {}: {}", mod_name, exc)
        raise
    missing = [a for a in _CASCADE_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(f"Cascade script {mod_name} missing: {', '.join(missing)}")
    return mod


def _sts_from_prefetch(prefetch: dict[str, Any]) -> StsRuntime:
    markers = prefetch.get("goodbye_markers") or []
    if not isinstance(markers, (list, tuple)):
        markers = []
    return StsRuntime(
        script_id=str(prefetch.get("script_id") or ""),
        source="script_config",
        system_instruction=str(prefetch.get("system_instruction") or ""),
        bootstrap_messages=list(prefetch.get("bootstrap_messages") or []),
        goodbye_markers=tuple(str(m) for m in markers),
        gemini_model=str(prefetch.get("gemini_model") or ""),
        gemini_voice=str(prefetch.get("gemini_voice") or ""),
        gemini_language=parse_gemini_language(str(prefetch.get("gemini_language") or "")),
        gemini_vad=build_gemini_vad(prefetch),
        gemini_temperature=_safe_float(
            prefetch.get("gemini_temperature") or 0.5,
            0.5,
            field="gemini_temperature",
        ),
        extraction_schema=dict(prefetch.get("extraction_schema") or {}),
        gemini_enable_affective_dialog=False,
    )


def _sts_from_module(mod: ModuleType, ctx: LeadContext) -> StsRuntime:
    sid = getattr(mod, "SCRIPT_ID", os.getenv("STS_SCRIPT", "pyramid_mr"))
    markers = getattr(mod, "GOODBYE_HANGUP_MARKERS", ())
    return StsRuntime(
        script_id=str(sid),
        source="module",
        system_instruction=mod.build_system_instruction(ctx),
        bootstrap_messages=list(mod.build_bootstrap_messages(ctx)),
        goodbye_markers=tuple(str(m) for m in markers),
        gemini_model=str(mod.GEMINI_MODEL),
        gemini_voice=str(mod.GEMINI_VOICE),
        gemini_language=mod.GEMINI_LANGUAGE,
        gemini_vad=mod.GEMINI_VAD,
        gemini_temperature=float(mod.GEMINI_TEMPERATURE),
        extraction_schema=dict(mod.EXTRACTION_SCHEMA),
        gemini_enable_affective_dialog=bool(
            getattr(mod, "GEMINI_ENABLE_AFFECTIVE_DIALOG", False)
        ),
        module_name=mod.__name__,
    )


def resolve_sts_runtime(body: dict[str, Any]) -> StsRuntime:
    """Tier 1: prefetched config from /ws. Tier 2/3: importlib module."""
    prefetch = body.get("_prefetched_config")
    if isinstance(prefetch, dict):
        if prefetch.get("source") == "script_config" and prefetch.get("route") == "sts":
            runtime = _sts_from_prefetch(prefetch)
            version = prefetch.get("version", "?")
            logger.info(
                "STS script active: {} (script_config v{})",
                runtime.script_id,
                version,
            )
            _log_prompt_summary(runtime.system_instruction, runtime.bootstrap_messages)
            return runtime
        if prefetch.get("source") == "script_config":
            logger.warning(
                "Ignoring prefetched config with route={!r} in STS bot",
                prefetch.get("route"),
            )

    pg = body.get("_pg") or {}
    mod = _load_sts_script(pg.get("script_id"))
    ctx = LeadContext.from_body(body)
    runtime = _sts_from_module(mod, ctx)
    logger.info("STS script active: {} ({})", runtime.script_id, runtime.module_name)
    _log_prompt_summary(runtime.system_instruction, runtime.bootstrap_messages)
    return runtime


def _cascade_from_prefetch(prefetch: dict[str, Any]) -> CascadeRuntime:
    tts_voice = str(prefetch.get("cascade_tts_voice") or "")
    if not tts_voice:
        tts_voice = os.getenv(_DEFAULT_CASCADE_TTS_VOICE_ENV, "") or "sonic-3"
    return CascadeRuntime(
        script_id=str(prefetch.get("script_id") or ""),
        source="script_config",
        system_prompt=str(prefetch.get("system_prompt") or ""),
        extraction_schema=dict(prefetch.get("extraction_schema") or {}),
        stt_model=str(prefetch.get("cascade_stt_model") or _DEFAULT_CASCADE_STT_MODEL),
        llm_model=str(prefetch.get("cascade_llm_model") or _DEFAULT_CASCADE_LLM_MODEL),
        tts_voice=tts_voice,
        push_lead_data_schema=build_push_lead_data_schema(
            prefetch.get("cascade_live_tools") or []
        ),
    )


def _cascade_from_module(mod: ModuleType, ctx: LeadContext) -> CascadeRuntime:
    sid = getattr(mod, "SCRIPT_ID", os.getenv("CASCADE_SCRIPT", "prowave"))
    return CascadeRuntime(
        script_id=str(sid),
        source="module",
        system_prompt=mod.build_system_prompt(ctx),
        extraction_schema=dict(mod.EXTRACTION_SCHEMA),
        stt_model=_DEFAULT_CASCADE_STT_MODEL,
        llm_model=_DEFAULT_CASCADE_LLM_MODEL,
        tts_voice=os.getenv(_DEFAULT_CASCADE_TTS_VOICE_ENV, "") or "",
        push_lead_data_schema=None,
        module_name=mod.__name__,
    )


def resolve_cascade_runtime(body: dict[str, Any]) -> CascadeRuntime:
    """Tier 1: prefetched config from /ws. Tier 2/3: importlib module."""
    prefetch = body.get("_prefetched_config")
    if isinstance(prefetch, dict):
        if (
            prefetch.get("source") == "script_config"
            and prefetch.get("route") == "cascaded"
        ):
            runtime = _cascade_from_prefetch(prefetch)
            version = prefetch.get("version", "?")
            logger.info(
                "Cascade script active: {} (script_config v{})",
                runtime.script_id,
                version,
            )
            try:
                logger.info("[prompt] cascade system_prompt for call ->\n{}", runtime.system_prompt)
            except Exception:
                logger.debug("[prompt] Failed to log cascade system_prompt", exc_info=True)
            return runtime
        if prefetch.get("source") == "script_config":
            logger.warning(
                "Ignoring prefetched config with route={!r} in cascade bot",
                prefetch.get("route"),
            )

    pg = body.get("_pg") or {}
    mod = _load_cascade_script(pg.get("script_id"))
    ctx = LeadContext.from_body(body, default_lead_name="Sir")
    runtime = _cascade_from_module(mod, ctx)
    logger.info("Cascade script active: {} ({})", runtime.script_id, runtime.module_name)
    try:
        logger.info("[prompt] cascade system_prompt for call ->\n{}", runtime.system_prompt)
    except Exception:
        logger.debug("[prompt] Failed to log cascade system_prompt", exc_info=True)
    return runtime

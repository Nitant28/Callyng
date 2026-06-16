"""Process-local prefetch registry for database-driven script configs.

Single-worker uvicorn only — same constraint as ``_PG_CONTEXT`` and ``_warmup_ready``.
"""

from __future__ import annotations

import copy
import re
from string import Template
from typing import Any

import asyncpg
from loguru import logger

_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# session_call_id -> rendered script config dict (see render_script_config output shape)
PREFETCHED_CONFIGS: dict[str, dict[str, Any]] = {}


def register_prefetched_config(session_call_id: str, config: dict[str, Any]) -> None:
    if session_call_id and config:
        PREFETCHED_CONFIGS[session_call_id] = config


def pop_prefetched_config(session_call_id: str | None) -> dict[str, Any] | None:
    if not session_call_id:
        return None
    return PREFETCHED_CONFIGS.pop(session_call_id, None)


def build_lead_dict(lead: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, str]:
    """LeadContext fields plus filtered metadata for ``Template.safe_substitute``."""
    meta = metadata if isinstance(metadata, dict) else {}
    out: dict[str, str] = {
        "lead_name": str(lead.get("name") or "Sir/Madam"),
        "lead_phone": str(lead.get("phone") or ""),
        "lead_city": str(meta.get("city") or ""),
    }
    for key, value in meta.items():
        if not isinstance(key, str) or not _METADATA_KEY_RE.fullmatch(key):
            continue
        if key in out:
            continue
        out[key] = str(value) if value is not None else ""
    return out


def _substitute_template(text: str, lead_dict: dict[str, str]) -> str:
    return Template(text).safe_substitute(lead_dict)


def _render_bootstrap_messages(
    messages: Any,
    lead_dict: dict[str, str],
) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    rendered: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        item = copy.deepcopy(msg)
        content = item.get("content")
        if isinstance(content, str):
            item["content"] = _substitute_template(content, lead_dict)
        rendered.append(item)
    return rendered


def render_script_config(
    row: dict[str, Any],
    lead_dict: dict[str, str],
    *,
    expected_route: str | None = None,
) -> dict[str, Any]:
    """Render ``script_configs`` row templates for dial-time prefetch."""
    route = str(row.get("route") or "")
    if expected_route is not None and route != expected_route:
        raise ValueError(
            f"script_config route {route!r} does not match bot_config route {expected_route!r}"
        )

    template = str(row.get("system_instruction_template") or "")
    rendered_instruction = _substitute_template(template, lead_dict)
    bootstrap = _render_bootstrap_messages(row.get("bootstrap_messages_json"), lead_dict)

    config: dict[str, Any] = {
        "source": "script_config",
        "route": route,
        "script_config_id": str(row.get("id") or ""),
        "script_id": str(row.get("script_id") or ""),
        "version": int(row.get("version") or 1),
        "system_instruction": rendered_instruction,
        "bootstrap_messages": bootstrap,
        "goodbye_markers": row.get("goodbye_markers") or [],
        "gemini_model": str(row.get("gemini_model") or ""),
        "gemini_voice": str(row.get("gemini_voice") or ""),
        "gemini_language": str(row.get("gemini_language") or ""),
        "gemini_temperature": float(row.get("gemini_temperature") or 0.5),
        "vad_start_sensitivity": str(row.get("vad_start_sensitivity") or "HIGH"),
        "vad_end_sensitivity": str(row.get("vad_end_sensitivity") or "LOW"),
        "vad_silence_duration_ms": int(row.get("vad_silence_duration_ms") or 800),
        "vad_prefix_padding_ms": int(row.get("vad_prefix_padding_ms") or 300),
        "system_prompt": rendered_instruction,
        "cascade_stt_provider": str(row.get("cascade_stt_provider") or "sarvam"),
        "cascade_stt_model": str(row.get("cascade_stt_model") or "saarika:v2.5"),
        "cascade_llm_provider": str(row.get("cascade_llm_provider") or "groq"),
        "cascade_llm_model": str(row.get("cascade_llm_model") or "llama-3.3-70b-versatile"),
        "cascade_tts_provider": str(row.get("cascade_tts_provider") or "cartesia"),
        "cascade_tts_voice": str(row.get("cascade_tts_voice") or "sonic-3"),
        "cascade_live_tools": row.get("cascade_live_tools") or [],
        "extraction_schema": row.get("extraction_schema") or {},
        "lead_schema": row.get("lead_schema") or {"fields": []},
        "normalization_rules": row.get("normalization_rules") or [],
        "outcome_event_map": row.get("outcome_event_map") or {},
        "outcome_terminal": row.get("outcome_terminal") or [],
        "outcome_retry": row.get("outcome_retry") or [],
        "outcome_callback": row.get("outcome_callback") or [],
    }
    return config


async def sweep_stale_prefetched_configs(pool: asyncpg.Pool) -> int:
    """Drop prefetch entries whose call_logs row is no longer in progress."""
    keys = list(PREFETCHED_CONFIGS.keys())
    if not keys:
        return 0
    rows = await pool.fetch(
        """
        SELECT session_call_id FROM call_logs
        WHERE session_call_id = ANY($1::text[]) AND in_progress = FALSE
        """,
        keys,
    )
    purged = 0
    for row in rows:
        sid = row["session_call_id"]
        if PREFETCHED_CONFIGS.pop(sid, None) is not None:
            purged += 1
    if purged:
        logger.info("Prefetch sweep purged {} stale config(s)", purged)
    return purged

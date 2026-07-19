"""Post-call structured lead extraction via OpenAI-compatible, Anthropic, or Gemini APIs."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlencode

import aiohttp
from loguru import logger

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
_GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_VALID_PROVIDERS = frozenset({"openai", "anthropic", "gemini"})
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_MAX_TOKENS = 4096


def post_call_provider() -> str:
    """Return normalized ``POST_CALL_PROVIDER`` (default ``openai``)."""
    raw = (os.getenv("POST_CALL_PROVIDER") or "openai").strip().lower()
    return raw or "openai"


def _resolve_openai_key(api_key: str | None = None) -> str:
    return (
        (api_key or "").strip()
        or (os.getenv("OPENAI_API_KEY") or "").strip()
        or (os.getenv("GROQ_API_KEY") or "").strip()
    )


def _resolve_provider_key(provider: str, api_key: str | None = None) -> str:
    if api_key and api_key.strip():
        return api_key.strip()
    if provider == "openai":
        return _resolve_openai_key(None)
    if provider == "anthropic":
        return (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if provider == "gemini":
        return (os.getenv("GOOGLE_API_KEY") or "").strip()
    return ""


def post_call_llm_configured() -> bool:
    """True when the active ``POST_CALL_PROVIDER`` has an API key set."""
    provider = post_call_provider()
    if provider not in _VALID_PROVIDERS:
        return False
    return bool(_resolve_provider_key(provider))


def post_call_missing_key_message() -> str:
    """Human-readable missing-key message for the active provider."""
    provider = post_call_provider()
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY not configured"
    if provider == "gemini":
        return "GOOGLE_API_KEY not configured"
    if provider == "openai":
        return "OPENAI_API_KEY or GROQ_API_KEY not configured"
    return f"unsupported POST_CALL_PROVIDER={provider!r} (expected openai|anthropic|gemini)"

_VALID_MODES = frozenset({"fields", "summary", "both"})

_MIN_INTERRUPTED_ASSISTANT_CHARS = 15

_GLOBAL_EXTRACTION_PREAMBLE = """Transcript reliability (critical):
- role=assistant text is the bot's own generated speech and is MORE reliable than role=user text.
- role=user text comes from phone speech-to-text and may contain errors.
- Prefer the last assistant confirmation/summary turn when resolving conflicts."""

def validate_extraction_schema(schema: dict[str, Any]) -> None:
    """Raise ValueError if schema is missing required structure."""
    if not isinstance(schema, dict):
        raise ValueError("extraction_schema must be a dict")
    mode = schema.get("mode")
    if mode not in _VALID_MODES:
        raise ValueError(
            f"extraction_schema.mode must be one of {sorted(_VALID_MODES)!r}, got {mode!r}"
        )
    if mode in ("fields", "both"):
        fields = schema.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("extraction_schema.fields must be a non-empty list")


def _field_type_hint(field: dict[str, Any]) -> str:
    ftype = field.get("type", "string")
    if ftype == "enum":
        values = field.get("values") or []
        return "one of " + ", ".join(str(v) for v in values)
    if ftype == "boolean":
        return "boolean (true/false)"
    if ftype == "datetime":
        return "ISO 8601 datetime string or the literal NULL"
    return "string"


def _format_field_lines(fields: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for field in fields:
        key = field.get("key")
        if not key:
            continue
        required = field.get("required", False)
        req_label = "required" if required else "optional"
        hint = _field_type_hint(field)
        desc = (field.get("description") or "").strip()
        line = f"- {key} ({req_label}): {hint}"
        if desc:
            line += f". {desc}"
        lines.append(line)
    return lines


def filter_short_interrupted_turns(
    transcript: list[dict[str, Any]],
    *,
    min_chars: int = _MIN_INTERRUPTED_ASSISTANT_CHARS,
) -> list[dict[str, Any]]:
    """Drop very short interrupted assistant fragments (noise before merge)."""
    out: list[dict[str, Any]] = []
    for turn in transcript:
        if turn.get("role") == "assistant" and turn.get("interrupted"):
            content = (turn.get("content") or "").strip()
            if len(content) < min_chars:
                continue
        out.append(dict(turn))
    return out


def merge_consecutive_turns(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent turns with the same role into one turn."""
    if not transcript:
        return []
    merged: list[dict[str, Any]] = []
    for turn in transcript:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not role or not content:
            continue
        if merged and merged[-1].get("role") == role:
            prev = merged[-1]
            prev_content = (prev.get("content") or "").strip()
            prev["content"] = f"{prev_content} {content}".strip()
            if turn.get("interrupted"):
                prev["interrupted"] = True
            ts = turn.get("timestamp") or turn.get("ts")
            if ts and not prev.get("timestamp") and not prev.get("ts"):
                if "timestamp" in prev:
                    prev["timestamp"] = ts
                else:
                    prev["ts"] = ts
        else:
            merged.append(dict(turn))
    return merged


def prepare_transcript_for_storage(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter noise and merge same-role turns for stored transcripts."""
    return merge_consecutive_turns(filter_short_interrupted_turns(transcript))


def format_transcript_for_extraction(transcript: list[dict[str, Any]]) -> str:
    """Format transcript with assistant-priority labeling for Groq extraction."""
    prepared = merge_consecutive_turns(filter_short_interrupted_turns(transcript))
    assistant_lines: list[str] = []
    user_lines: list[str] = []
    for idx, turn in enumerate(prepared, start=1):
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            assistant_lines.append(f"[turn {idx}] {content}")
        elif role == "user":
            user_lines.append(f"[turn {idx}] {content}")
    parts = [
        "ASSISTANT (authoritative — bot's own words; prefer over user STT when they conflict):",
    ]
    if assistant_lines:
        parts.extend(assistant_lines)
    else:
        parts.append("(none)")
    parts.append("")
    parts.append("USER (may contain speech-to-text errors on phone audio):")
    if user_lines:
        parts.extend(user_lines)
    else:
        parts.append("(none)")
    return "\n".join(parts)



def build_extraction_system_prompt(schema: dict[str, Any]) -> str:
    """Compile Groq system prompt from script EXTRACTION_SCHEMA."""
    validate_extraction_schema(schema)
    mode = schema["mode"]
    parts = [
        "You analyze outbound voice-call transcripts.",
        "Reply with ONE JSON object only. No markdown fences, no other text.",
        "",
        _GLOBAL_EXTRACTION_PREAMBLE,
        "",
    ]

    if mode in ("fields", "both"):
        parts.append("Keys and rules:")
        parts.extend(_format_field_lines(schema.get("fields") or []))
        parts.append("")

    rules = (schema.get("extraction_rules") or "").strip()
    if rules:
        parts.append(rules)
        parts.append("")

    if mode == "summary":
        summary_prompt = (schema.get("summary_prompt") or "").strip()
        if not summary_prompt:
            raise ValueError("extraction_schema.summary_prompt required when mode='summary'")
        parts.append("Write a summary paragraph with key:")
        parts.append('- summary (string, required): ' + summary_prompt)
    elif mode == "both":
        summary_prompt = (schema.get("summary_prompt") or "").strip()
        if summary_prompt:
            parts.append("Also include:")
            parts.append('- summary (string, required): ' + summary_prompt)

    return "\n".join(parts).strip()


def apply_normalization_rules(
    parsed: dict[str, Any],
    rules: list[Any],
) -> dict[str, Any]:
    """
    Apply declarative post-call normalization rules.

    Rule shape::

        {
          "when": {"field": "site_visit_agreed", "truthy": true},
          "and_intent_in": ["", "Unknown"],
          "set": {"intent_status": "Interested"}
        }

    ``when`` supports ``field`` + ``truthy`` (bool) or ``eq`` (any value).
    """
    out = dict(parsed)
    if not rules:
        return out

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when")
        if not isinstance(when, dict):
            continue
        field = when.get("field")
        if not field:
            continue
        val = out.get(field)
        matched = False
        if "truthy" in when:
            truthy = when["truthy"]
            if val is True:
                is_truthy = True
            elif isinstance(val, str):
                s = val.strip().casefold()
                is_truthy = s not in ("", "null", "none", "false", "0", "no")
            else:
                is_truthy = bool(val)
            matched = is_truthy if truthy else not is_truthy
        elif "eq" in when:
            matched = val == when["eq"]
        else:
            matched = bool(val)

        if not matched:
            continue

        and_intent = rule.get("and_intent_in")
        if isinstance(and_intent, list):
            raw_intent = out.get("intent_status")
            intent = (
                raw_intent.strip()
                if isinstance(raw_intent, str)
                else (str(raw_intent).strip() if raw_intent is not None else "")
            )
            allowed = {str(x) for x in and_intent}
            if intent not in allowed:
                continue

        to_set = rule.get("set")
        if isinstance(to_set, dict):
            out.update(to_set)

    return out


def normalize_post_call_extraction(
    parsed: dict[str, Any],
    *,
    normalization_rules: list[Any] | None = None,
) -> dict[str, Any]:
    """Deterministic patch after Groq parse — known inconsistency patterns."""
    if normalization_rules:
        out = apply_normalization_rules(parsed, normalization_rules)
        if "intent_status" not in out or not str(out.get("intent_status", "")).strip():
            out["intent_status"] = "Unknown"
        return out
    else:
        out = dict(parsed)
        raw_intent = out.get("intent_status")
        intent = (
            raw_intent.strip()
            if isinstance(raw_intent, str)
            else (str(raw_intent).strip() if raw_intent is not None else "")
        )
        weak = intent == "" or intent.casefold() == "unknown"

        svn = out.get("site_visit_agreed")
        truthy_svn = svn is True or (
            isinstance(svn, str) and svn.strip().casefold() in ("true", "1", "yes")
        )

        if truthy_svn and weak:
            logger.info(
                "normalize_post_call_extraction: site_visit_agreed=true with weak intent_status={!r} -> Interested",
                raw_intent,
            )
            out["intent_status"] = "Interested"

        callback_time = out.get("callback_time")
        has_callback = (
            callback_time is not None
            and str(callback_time).strip().lower() not in ("", "null", "none")
        )
        if has_callback and out.get("intent_status") not in (
            "Callback_Requested",
            "Interested",
        ):
            logger.info(
                "normalize_post_call_extraction: callback_time set with intent_status={!r} -> Callback_Requested",
                out.get("intent_status"),
            )
            out["intent_status"] = "Callback_Requested"

        if "intent_status" not in out or not str(out.get("intent_status", "")).strip():
            out["intent_status"] = "Unknown"

        return out


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def _first_markdown_json_block(text: str) -> str | None:
    """If the model wrapped JSON in a ``` fence anywhere, return the inner body."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if not m:
        return None
    inner = m.group(1).strip()
    return inner if inner else None


def _parse_model_json_object(content: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse one JSON object from model message.content (empty, fences, leading prose)."""
    if not isinstance(content, str):
        return None, "missing_message_content"
    text = content.strip()
    if not text:
        return None, "empty_message_content"

    candidates: list[str] = []
    fenced = _first_markdown_json_block(text)
    if fenced:
        candidates.append(fenced)
    candidates.append(_strip_json_fence(text))

    seen: set[str] = set()
    uniq: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)

    for candidate in uniq:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj, None
            return None, "parsed_JSON_is_not_an_object"
        except json.JSONDecodeError:
            continue

    start = text.find("{")
    if start == -1:
        snippet = text[:400].replace("\n", "\\n")
        return None, f"no_json_object_in_response: {snippet!r}"

    dec = json.JSONDecoder()
    try:
        obj, _end = dec.raw_decode(text, start)
    except json.JSONDecodeError as exc:
        snippet = text[start : start + 400].replace("\n", "\\n")
        return None, f"JSONDecodeError: {exc}; snippet={snippet!r}"

    if not isinstance(obj, dict):
        return None, "parsed_JSON_is_not_an_object"
    return obj, None


def _user_extraction_message(transcript_payload: str) -> str:
    return "Extract the JSON object from this transcript:\n\n" + transcript_payload


async def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_sec: float,
) -> tuple[Any | None, str | None]:
    """POST JSON; return (parsed_json, error)."""
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=body) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    err = f"LLM HTTP {resp.status}: {raw[:500]}"
                    logger.warning("post_call_extract {}", err)
                    return None, err
                return json.loads(raw), None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.warning("post_call_extract request failed: {}", err)
        return None, err


def _openai_content_from_response(data: Any) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, "unexpected response type"
    choices = data.get("choices") or []
    if not choices:
        return None, "no choices in response"
    choice0 = choices[0]
    msg = choice0.get("message") or {}
    content = msg.get("content")
    if content is None:
        fr = choice0.get("finish_reason")
        return None, f"missing message content (finish_reason={fr!r})"
    if not isinstance(content, str):
        return None, f"unexpected message content type: {type(content).__name__}"
    return content, None


def _anthropic_content_from_response(data: Any) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, "unexpected response type"
    blocks = data.get("content") or []
    if not blocks:
        return None, "no content in response"
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        return None, "no text blocks in response"
    return "".join(parts), None


def _gemini_content_from_response(data: Any) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, "unexpected response type"
    candidates = data.get("candidates") or []
    if not candidates:
        return None, "no candidates in response"
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    if not texts:
        return None, "no text parts in response"
    return "".join(texts), None


async def _chat_openai_compat(
    *,
    system_prompt: str,
    user_content: str,
    model: str,
    api_key: str,
    timeout_sec: float,
) -> tuple[str | None, str | None]:
    base = (os.getenv("OPENAI_BASE_URL") or _DEFAULT_OPENAI_BASE_URL).rstrip("/")
    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data, err = await _post_json(url, headers=headers, body=body, timeout_sec=timeout_sec)
    if err:
        return None, err
    return _openai_content_from_response(data)


async def _chat_anthropic(
    *,
    system_prompt: str,
    user_content: str,
    model: str,
    api_key: str,
    timeout_sec: float,
) -> tuple[str | None, str | None]:
    base = (os.getenv("ANTHROPIC_BASE_URL") or _DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")
    url = f"{base}/v1/messages"
    body = {
        "model": model,
        "max_tokens": _ANTHROPIC_MAX_TOKENS,
        "temperature": 0.1,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    data, err = await _post_json(url, headers=headers, body=body, timeout_sec=timeout_sec)
    if err:
        return None, err
    return _anthropic_content_from_response(data)


async def _chat_gemini(
    *,
    system_prompt: str,
    user_content: str,
    model: str,
    api_key: str,
    timeout_sec: float,
) -> tuple[str | None, str | None]:
    model_id = model.removeprefix("models/")
    url = _GEMINI_GENERATE_URL.format(model=model_id) + "?" + urlencode({"key": api_key})
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": 0.1},
    }
    headers = {"Content-Type": "application/json"}
    data, err = await _post_json(url, headers=headers, body=body, timeout_sec=timeout_sec)
    if err:
        return None, err
    return _gemini_content_from_response(data)


async def extract_post_call(
    transcript: list[dict[str, Any]],
    *,
    extraction_schema: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    timeout_sec: float = 60.0,
) -> tuple[dict[str, Any] | None, str | None, str]:
    """Call the configured post-call LLM; return (parsed, error, model_used)."""
    system_prompt = build_extraction_system_prompt(extraction_schema)
    mdl = model or os.getenv("POST_CALL_MODEL", _DEFAULT_MODEL)
    provider = post_call_provider()
    if provider not in _VALID_PROVIDERS:
        err = (
            f"unsupported POST_CALL_PROVIDER={provider!r} "
            f"(expected {sorted(_VALID_PROVIDERS)})"
        )
        logger.warning("post_call_extract {}", err)
        return None, err, mdl

    key = _resolve_provider_key(provider, api_key)
    if not key:
        return None, None, mdl

    user_content = _user_extraction_message(format_transcript_for_extraction(transcript))

    if provider == "openai":
        content, err = await _chat_openai_compat(
            system_prompt=system_prompt,
            user_content=user_content,
            model=mdl,
            api_key=key,
            timeout_sec=timeout_sec,
        )
    elif provider == "anthropic":
        content, err = await _chat_anthropic(
            system_prompt=system_prompt,
            user_content=user_content,
            model=mdl,
            api_key=key,
            timeout_sec=timeout_sec,
        )
    else:
        content, err = await _chat_gemini(
            system_prompt=system_prompt,
            user_content=user_content,
            model=mdl,
            api_key=key,
            timeout_sec=timeout_sec,
        )

    if err:
        return None, err, mdl
    if content is None:
        return None, "empty LLM content", mdl

    parsed, parse_err = _parse_model_json_object(content)
    if parse_err:
        preview = content[:500] + ("…" if len(content) > 500 else "")
        logger.warning(
            "post_call_extract parse failed: {} | preview={!r}",
            parse_err,
            preview,
        )
        return None, parse_err, mdl
    return parsed, None, mdl

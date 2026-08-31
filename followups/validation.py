"""Validate model output before it can reach a customer.

Nothing that leaves this module is allowed to expose that an AI was involved, to
leak internal errors, or to be structurally unusable. Anything suspicious is
rejected with a reason so the caller can fall back to a deterministic message.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

MAX_WHATSAPP_CHARS = 1024
MAX_EMAIL_SUBJECT_CHARS = 200
MAX_EMAIL_BODY_CHARS = 6000
MIN_MESSAGE_CHARS = 12
MIN_SUBJECT_CHARS = 5

_TEXT_KEYS = ("message", "text", "body", "reply", "content", "output", "response", "result")

_LITERAL_JUNK = frozenset(
    {"undefined", "null", "none", "nil", "n/a", "na", "true", "false", "{}", "[]", "[object object]"}
)

_BANNED_SUBSTRINGS = (
    "gemini",
    "openai",
    "anthropic",
    "langchain",
    "vertex ai",
    "n8n",
    "api key",
    "apikey",
    "access token",
    "rate limit",
    "quota exceeded",
    "traceback",
    "stack trace",
    "stacktrace",
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "system prompt",
    "system message",
    "output parser",
    "json schema",
    "internal server error",
    "econnrefused",
    "etimedout",
    "nodeoperationerror",
    "nodeapierror",
)

_BANNED_WORD_RE = re.compile(r"\b(undefined|nan|null)\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"\{\{.*?\}\}|\{[a-z_][a-z0-9_]*\}|\[(?:insert|your|name|client|todo|placeholder)[^\]]*\]|<[a-z_]+>",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^\s*```(?:json|javascript|text)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    text: str | None = None
    reason: str | None = None


def strip_code_fence(raw: str) -> str:
    return _FENCE_RE.sub("", raw).strip()


def extract_object(raw: Any) -> dict[str, Any] | None:
    """Coerce a model response into a dict when it structurally is one."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        for item in raw:
            found = extract_object(item)
            if found is not None:
                return found
        return None
    if isinstance(raw, str):
        candidate = strip_code_fence(raw)
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                return None
            return extract_object(parsed)
    return None


def extract_text(raw: Any, *, keys: tuple[str, ...] = _TEXT_KEYS, _depth: int = 0) -> str | None:
    """Pull the human-readable message out of whatever shape the model returned."""
    if raw is None or _depth > 5:
        return None
    if isinstance(raw, str):
        obj = extract_object(raw)
        if obj is not None:
            return extract_text(obj, keys=keys, _depth=_depth + 1)
        text = strip_code_fence(raw).strip()
        return text or None
    if isinstance(raw, dict):
        for key in keys:
            if key in raw:
                found = extract_text(raw[key], keys=keys, _depth=_depth + 1)
                if found:
                    return found
        return None
    if isinstance(raw, list):
        for item in raw:
            found = extract_text(item, keys=keys, _depth=_depth + 1)
            if found:
                return found
        return None
    if isinstance(raw, (int, float)):
        return None
    return None


def _normalise_whitespace(text: str) -> str:
    collapsed = re.sub(r"[ \t\u00a0]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", collapsed).strip()


def validate_message(
    candidate: Any,
    *,
    max_chars: int = MAX_WHATSAPP_CHARS,
    min_chars: int = MIN_MESSAGE_CHARS,
    inbound_text: str | None = None,
) -> ValidationResult:
    """Decide whether a model-produced message is safe to send as-is."""
    if candidate is None:
        return ValidationResult(False, reason="missing")

    text = extract_text(candidate)
    if text is None:
        return ValidationResult(False, reason="unusable_shape")

    text = _normalise_whitespace(text)
    if not text:
        return ValidationResult(False, reason="empty")

    folded = text.casefold()
    if folded in _LITERAL_JUNK:
        return ValidationResult(False, reason="literal_junk")
    if _BANNED_WORD_RE.search(text):
        return ValidationResult(False, reason="literal_junk")
    if text.startswith("{") or text.startswith("["):
        return ValidationResult(False, reason="json_like")
    if len(text) < min_chars:
        return ValidationResult(False, reason="too_short")
    if len(text) > max_chars:
        return ValidationResult(False, reason="too_long")
    if _PLACEHOLDER_RE.search(text):
        return ValidationResult(False, reason="placeholder_leftover")
    for banned in _BANNED_SUBSTRINGS:
        if banned in folded:
            return ValidationResult(False, reason="banned_content")
    if inbound_text and folded == _normalise_whitespace(str(inbound_text)).casefold():
        return ValidationResult(False, reason="echoes_inbound")

    return ValidationResult(True, text=text)


def validate_email(candidate: Any) -> tuple[ValidationResult, ValidationResult]:
    """Validate an AI email as a (subject, body) pair."""
    obj = extract_object(candidate)
    if obj is None and isinstance(candidate, dict):
        obj = candidate
    if obj is None:
        missing = ValidationResult(False, reason="unusable_shape")
        return missing, missing

    subject = validate_message(
        obj.get("subject"),
        max_chars=MAX_EMAIL_SUBJECT_CHARS,
        min_chars=MIN_SUBJECT_CHARS,
    )
    body = validate_message(
        obj.get("body") if obj.get("body") is not None else obj.get("message"),
        max_chars=MAX_EMAIL_BODY_CHARS,
    )
    return subject, body

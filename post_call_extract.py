"""Post-call structured lead extraction via Groq (OpenAI-compatible chat API)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import aiohttp
from loguru import logger

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"

_DEFAULT_MODEL = "llama-3.3-70b-versatile"

_EXTRACTION_SYSTEM = """You analyze outbound voice-call transcripts. Reply with ONE JSON object only. No markdown fences, no other text.

Keys and rules:
- intent_status (string, required): one of Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Interested, Unknown.
  - Interested: caller is engaged — e.g. agreed to or strongly leaning toward a site visit, asked for details/timing, or clearly wants to explore the 2 BHK without a hard refusal.
  - Callback_Requested: caller gave a concrete time/date to be called back (not vague "later").
  - Busy: wants to end now / call back later but gave NO specific time.
  - Not_Interested: explicit refusal of the home/project/inquiry — not a short "no" that only answers "anything else to ask?".
  - Wrong_Requirement: wants plot/shop/office/rent/commercial/wrong BHK type.
  - Unknown: genuinely ambiguous ending or dropped call with no usable signal.

Consistency (critical):
- If the caller agreed to a site visit, said yes to visiting / a weekend slot / "चालेल" / "haan chalel" for the visit, or confirmed a visit time, site_visit_agreed should be true and intent_status must reflect engagement — use Interested, or Callback_Requested if the main outcome was a scheduled callback with a concrete time. Do NOT leave intent_status as Unknown when a site visit was clearly agreed.
- If assistant only asked whether the caller had *more questions* / *anything specific to ask* / *काही specific विचारायचं आहे* / similar, and the caller replied with a short negative like "nahi nahi" / "नाही नाही" meaning "nothing else to ask", that is NOT property refusal — not Not_Interested unless they also clearly refuse the project/home.

- bhk_preference (string): e.g. 2BHK, 3BHK, or the literal NULL if not stated.
- location_preference (string): area/city mentioned, or the literal NULL.
- site_visit_agreed (boolean): true only if caller clearly agreed to a site visit.
- callback_time (string): specific time/date if given, else the literal NULL.
- language_used (string): one of Marathi, Hindi, English, Mixed.
- caller_notes (string): other useful facts, or the literal NULL.

Transcript is JSON: array of {role, content, ...}. Infer only what the conversation supports."""


def normalize_post_call_extraction(parsed: dict[str, Any]) -> dict[str, Any]:
    """Deterministic patch after Groq parse — e.g. site visit agreed cannot pair with Unknown."""
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
    """Parse one JSON object from Groq ``message.content`` (empty, fences, leading prose)."""
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


async def extract_post_call(
    transcript: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_sec: float = 60.0,
) -> tuple[dict[str, Any] | None, str | None, str]:
    """Call Groq; return ``(parsed_dict_or_none, error_or_none, model_used)``."""
    key = api_key or os.getenv("GROQ_API_KEY", "")
    mdl = model or os.getenv("POST_CALL_MODEL", _DEFAULT_MODEL)
    if not key:
        return None, None, mdl

    user_payload = json.dumps(transcript, ensure_ascii=False)
    body = {
        "model": mdl,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Extract the JSON object from this transcript:\n\n" + user_payload
                ),
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers=headers,
                json=body,
            ) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    err = f"Groq HTTP {resp.status}: {raw[:500]}"
                    logger.warning("post_call_extract {}", err)
                    return None, err, mdl
                data = json.loads(raw)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.warning("post_call_extract request failed: {}", err)
        return None, err, mdl

    choices = data.get("choices") or []
    if not choices:
        return None, "no choices in Groq response", mdl
    choice0 = choices[0]
    msg = choice0.get("message") or {}
    content = msg.get("content")
    if content is None:
        fr = choice0.get("finish_reason")
        return None, f"missing message content (finish_reason={fr!r})", mdl
    if not isinstance(content, str):
        return None, f"unexpected message content type: {type(content).__name__}", mdl

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

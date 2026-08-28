"""Generic Pipecat service factory for cascade STT / LLM / TTS."""

from __future__ import annotations

import json
import os
from typing import Any

from pipecat.transcriptions.language import Language
from pipecat.services.cartesia.tts import (
    CartesiaTTSService,
    CartesiaTTSSettings,
    GenerationConfig,
)
from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings
from pipecat.services.deepgram.tts import DeepgramTTSService, DeepgramTTSSettings
from pipecat.services.elevenlabs.stt import (
    ElevenLabsRealtimeSTTService,
    ElevenLabsRealtimeSTTSettings,
)
from pipecat.services.elevenlabs.tts import (
    ElevenLabsTTSService,
    ElevenLabsTTSSettings,
)
from pipecat.services.google.llm import GoogleLLMService, GoogleLLMSettings
from pipecat.services.groq.llm import GroqLLMService, GroqLLMSettings
from pipecat.services.openai.base_llm import OpenAILLMSettings
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings
from pipecat.services.sarvam.tts import SarvamTTSService, SarvamTTSSettings
from pipecat.services.soniox.stt import SonioxSTTService, SonioxSTTSettings
from pipecat.services.soniox.tts import SonioxTTSService, SonioxTTSSettings

from providers import catalog
from providers.keys import resolve_api_key

TELEPHONY_SAMPLE_RATE = 8000
# Pipecat 1.7's default 3s pause watchdog is too tight for first-utterance
# ElevenLabs/Cartesia websocket connect on 8 kHz PSTN (force-resume = silence).
TTS_PAUSE_WATCHDOG_TIMEOUT_S = 10.0
# Flash websocket often returns a completed context with zero audio at pcm_8000.
# Request pcm_16000; BaseOutputTransport resamples to 8 kHz for Plivo.
ELEVENLABS_TTS_SAMPLE_RATE = 16000

ServiceEntry = tuple[type, type, catalog.VoiceMode]

_SERVICES: dict[tuple[str, str], ServiceEntry] = {
    ("stt", "sarvam"): (SarvamSTTService, SarvamSTTSettings, "standard"),
    ("stt", "soniox"): (SonioxSTTService, SonioxSTTSettings, "standard"),
    ("stt", "elevenlabs"): (
        ElevenLabsRealtimeSTTService,
        ElevenLabsRealtimeSTTSettings,
        "standard",
    ),
    ("stt", "deepgram"): (DeepgramSTTService, DeepgramSTTSettings, "standard"),
    ("llm", "groq"): (GroqLLMService, GroqLLMSettings, "standard"),
    ("llm", "openai"): (OpenAILLMService, OpenAILLMSettings, "standard"),
    ("llm", "google"): (GoogleLLMService, GoogleLLMSettings, "standard"),
    ("tts", "cartesia"): (CartesiaTTSService, CartesiaTTSSettings, "standard"),
    ("tts", "elevenlabs"): (
        ElevenLabsTTSService,
        ElevenLabsTTSSettings,
        "standard",
    ),
    ("tts", "deepgram"): (DeepgramTTSService, DeepgramTTSSettings, "deepgram_model"),
    ("tts", "sarvam"): (SarvamTTSService, SarvamTTSSettings, "sarvam_speaker"),
    ("tts", "soniox"): (SonioxTTSService, SonioxTTSSettings, "standard"),
}

_NESTED: dict[str, type] = {"generation_config": GenerationConfig}


def _coerce_elevenlabs_language(value: str) -> Language | None:
    """Map catalog language strings to Language so Flash gets a real language_code."""
    text = value.strip().replace("_", "-")
    if not text or text.lower() in ("unknown", "auto"):
        return None
    try:
        return Language(text)
    except ValueError:
        base = text.split("-", 1)[0].lower()
        try:
            return Language(base)
        except ValueError:
            return None


def _coerce_safety_settings(value: Any) -> Any:
    """Parse catalog JSON string into a list; omit blanks."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"safety_settings must be valid JSON: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("safety_settings must be a JSON array")
        return parsed
    if isinstance(value, list):
        return value
    raise ValueError("safety_settings must be a JSON string or list")


def _split_nested(flat: dict[str, Any]) -> dict[str, Any]:
    """Fold dotted keys into their nested pydantic model."""
    plain: dict[str, Any] = {}
    groups: dict[str, dict[str, Any]] = {}
    for key, value in flat.items():
        head, _, tail = key.partition(".")
        if tail:
            groups.setdefault(head, {})[tail] = value
        else:
            plain[key] = value
    for group, values in groups.items():
        model_cls = _NESTED[group]
        plain[group] = model_cls(**values)
    return plain


async def _build(
    kind: catalog.Kind,
    provider: str,
    model: str,
    settings: dict[str, Any],
    *,
    client_id: Any = None,
    pool: Any = None,
    **overrides: Any,
) -> Any:
    provider_key = (provider or catalog.default_provider(kind)).strip().lower()
    model_key = (model or catalog.default_model(kind, provider_key)).strip()
    spec = catalog.get_provider(kind, provider_key)
    mspec = catalog.get_model(kind, provider_key, model_key)

    api_key = await resolve_api_key(
        spec.api_key_env,
        provider=spec.label,
        client_id=client_id,
        pool=pool,
    )

    payload: dict[str, Any] = {"model": model_key}
    ctor: dict[str, Any] = {"api_key": api_key}
    if kind in ("stt", "tts"):
        ctor["sample_rate"] = TELEPHONY_SAMPLE_RATE
    if kind == "tts":
        ctor["pause_watchdog_timeout_s"] = TTS_PAUSE_WATCHDOG_TIMEOUT_S
        if provider_key == "elevenlabs":
            ctor["sample_rate"] = ELEVENLABS_TTS_SAMPLE_RATE

    for field in mspec.fields:
        if field.key not in settings:
            continue
        value = settings[field.key]
        if (
            kind == "tts"
            and provider_key == "elevenlabs"
            and field.key == "language"
            and isinstance(value, str)
        ):
            value = _coerce_elevenlabs_language(value)
            if value is None:
                continue
        if field.key == "safety_settings":
            value = _coerce_safety_settings(value)
            if value is None:
                continue
        if field.ctor:
            ctor[field.key] = value
        else:
            payload[field.key] = value

    payload.update(overrides)

    service_key = (kind, provider_key)
    if service_key not in _SERVICES:
        raise ValueError(f"Unsupported {kind} provider: {provider_key!r}")
    cls, settings_cls, _voice_mode = _SERVICES[service_key]
    return cls(
        settings=settings_cls.from_mapping(_split_nested(payload)),
        **ctor,
    )


async def create_stt_service(
    provider: str,
    model: str,
    settings: dict[str, Any],
    *,
    client_id: Any = None,
    pool: Any = None,
) -> Any:
    return await _build(
        "stt",
        provider,
        model,
        settings,
        client_id=client_id,
        pool=pool,
    )


async def create_llm_service(
    provider: str,
    model: str,
    settings: dict[str, Any],
    *,
    system_prompt: str,
    client_id: Any = None,
    pool: Any = None,
) -> Any:
    return await _build(
        "llm",
        provider,
        model,
        settings,
        client_id=client_id,
        pool=pool,
        system_instruction=system_prompt,
    )


async def create_tts_service(
    provider: str,
    model: str,
    settings: dict[str, Any],
    *,
    voice: str = "",
    client_id: Any = None,
    pool: Any = None,
) -> Any:
    provider_key = (provider or catalog.default_provider("tts")).strip().lower()
    model_key = (model or catalog.default_model("tts", provider_key)).strip()
    spec = catalog.get_provider("tts", provider_key)
    voice_mode = spec.voice_mode

    resolved = (voice or "").strip() or str(settings.get("voice") or "").strip()
    if voice_mode == "deepgram_model":
        resolved = resolved or model_key
    elif voice_mode == "sarvam_speaker":
        if not resolved:
            resolved = (os.getenv(spec.voice_env or "", "") or "").strip()
    else:
        if not resolved:
            resolved = (os.getenv(spec.voice_env or "", "") or "").strip()

    if not resolved:
        raise ValueError(
            f"{spec.label}: no voice id (set one on the script config "
            f"or export {spec.voice_env})"
        )

    if voice_mode == "deepgram_model":
        resolved = resolved or model_key

    return await _build(
        "tts",
        provider,
        model,
        settings,
        client_id=client_id,
        pool=pool,
        voice=resolved,
    )

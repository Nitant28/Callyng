# Model IDs verified against Pipecat 1.7.0 on 2026-08-22.
# Voice-agent catalog refresh — see cascade.md §15.
"""Curated cascade provider/model catalog — single source of truth for factory, validation, and API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

FieldType = Literal["string", "select", "number", "boolean"]
Gender = Literal["male", "female"]
VoiceMode = Literal["standard", "deepgram_model", "sarvam_speaker"]

Kind = Literal["stt", "llm", "tts"]

_LANG = ("hi", "en", "mr")
_SARVAM_LANG = ("unknown", "hi-IN", "mr-IN", "en-IN")


@dataclass(frozen=True)
class RecommendedVoice:
    id: str
    label: str
    gender: Gender
    language: str


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: FieldType
    default: Any = None
    options: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    required: bool = False
    ctor: bool = False


@dataclass(frozen=True)
class ModelSpec:
    label: str
    fields: tuple[Field, ...] = ()
    recommended_voices: tuple[RecommendedVoice, ...] = ()

    @property
    def field_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.fields)


@dataclass(frozen=True)
class ProviderSpec:
    label: str
    api_key_env: str
    default_model: str
    models: dict[str, ModelSpec]
    voice_env: str | None = None
    voice_mode: VoiceMode = "standard"


_CARTESIA_VOICES = (
    RecommendedVoice("bdab08ad-4137-4548-b9db-6142854c7525", "Hindi Reporter Man", "male", "hi-IN"),
    RecommendedVoice("ac7ee4fa-25db-420d-bfff-f590d740aeb2", "Hindi Calm Man", "male", "hi-IN"),
    RecommendedVoice("c1abd502-9231-4558-a054-10ac950c356d", "Hindi Narrator Woman", "female", "hi-IN"),
    RecommendedVoice("3b554273-4299-48b9-9aaf-eefd438e3941", "Indian Lady", "female", "hi-IN"),
)

_ELEVENLABS_VOICES = (
    RecommendedVoice("21m00Tcm4TlvDq8ikWAM", "Rachel", "female", "en"),
    RecommendedVoice("pNInz6obpgDQGcFmaJgB", "Adam", "male", "en"),
)

_SARVAM_SPEAKERS = (
    RecommendedVoice("shubh", "Shubh", "male", "hi-IN"),
    RecommendedVoice("ashutosh", "Ashutosh", "male", "hi-IN"),
    RecommendedVoice("priya", "Priya", "female", "hi-IN"),
    RecommendedVoice("suhani", "Suhani", "female", "hi-IN"),
)

_SONIOX_VOICES = (
    RecommendedVoice("Adrian", "Adrian", "male", "en"),
    RecommendedVoice("Mina", "Mina", "female", "en"),
)

_SAARAS_FIELDS = (
    Field(
        "language",
        "Language",
        "select",
        options=_SARVAM_LANG,
        default="unknown",
    ),
    Field(
        "mode",
        "Mode",
        "select",
        options=("transcribe", "translate", "verbatim", "translit", "codemix"),
        default="transcribe",
        ctor=True,
    ),
)

_LLM_FIELDS = (
    Field("temperature", "Temperature", "number", min=0, max=2, step=0.1, default=0.2),
    Field("max_tokens", "Max tokens", "number", min=1, max=8192, step=1, default=1024),
    Field("top_p", "Top P", "number", min=0, max=1, step=0.05, default=1.0),
)

_GOOGLE_SAFETY_FIELD = Field(
    "safety_settings",
    "Safety settings JSON",
    "string",
)

_EL_BASE = (
    Field("voice", "Voice ID", "string"),
    Field("language", "Language", "select", options=_LANG, default="hi"),
    Field("stability", "Stability", "number", min=0, max=1, step=0.05, default=0.5),
    Field(
        "similarity_boost",
        "Similarity",
        "number",
        min=0,
        max=1,
        step=0.05,
        default=0.75,
    ),
    Field("use_speaker_boost", "Speaker boost", "boolean", default=True),
)
_EL_SPEED = (Field("speed", "Speed", "number", min=0.7, max=1.2, step=0.05, default=1.0),)

STT_CATALOG: dict[str, ProviderSpec] = {
    "sarvam": ProviderSpec(
        label="Sarvam",
        api_key_env="SARVAM_API_KEY",
        default_model="saaras:v3",
        models={
            "saaras:v3": ModelSpec("Saaras v3", _SAARAS_FIELDS),
            "saaras:v2.5": ModelSpec("Saaras v2.5", _SAARAS_FIELDS),
        },
    ),
    "soniox": ProviderSpec(
        label="Soniox",
        api_key_env="SONIOX_API_KEY",
        default_model="stt-rt-v5",
        models={
            "stt-rt-v5": ModelSpec(
                "Soniox Real-Time v5",
                (
                    Field(
                        "language_hints_strict",
                        "Strict language hints",
                        "boolean",
                        default=False,
                    ),
                    Field(
                        "max_endpoint_delay_ms",
                        "Max endpoint delay (ms)",
                        "number",
                        min=500,
                        max=3000,
                        step=100,
                        default=1000,
                    ),
                    Field(
                        "endpoint_sensitivity",
                        "Endpoint sensitivity",
                        "number",
                        min=-1.0,
                        max=1.0,
                        step=0.1,
                        default=0.0,
                    ),
                    Field(
                        "endpoint_latency_adjustment_level",
                        "Endpoint latency level",
                        "number",
                        min=0,
                        max=3,
                        step=1,
                        default=0,
                    ),
                    Field(
                        "enable_language_identification",
                        "Language identification",
                        "boolean",
                        default=False,
                    ),
                    Field(
                        "enable_speaker_diarization",
                        "Speaker diarization",
                        "boolean",
                        default=False,
                    ),
                    Field(
                        "vad_force_turn_endpoint",
                        "Use Pipecat VAD (not Soniox endpoint)",
                        "boolean",
                        default=True,
                        ctor=True,
                    ),
                ),
            ),
        },
    ),
    "elevenlabs": ProviderSpec(
        label="ElevenLabs",
        api_key_env="ELEVENLABS_API_KEY",
        default_model="scribe_v2_realtime",
        models={
            "scribe_v2_realtime": ModelSpec(
                "Scribe v2 Realtime",
                (
                    Field("language", "Language", "select", options=_LANG, default="hi"),
                    Field("keyterms", "Key terms", "string"),
                    Field(
                        "vad_threshold",
                        "VAD threshold",
                        "number",
                        min=0,
                        max=1,
                        step=0.05,
                        default=0.5,
                    ),
                    Field(
                        "vad_silence_threshold_secs",
                        "VAD silence (s)",
                        "number",
                        min=0.1,
                        max=5.0,
                        step=0.1,
                        default=1.0,
                    ),
                    Field(
                        "min_speech_duration_ms",
                        "Min speech (ms)",
                        "number",
                        min=0,
                        max=5000,
                        step=50,
                        default=100,
                    ),
                    Field(
                        "min_silence_duration_ms",
                        "Min silence (ms)",
                        "number",
                        min=0,
                        max=5000,
                        step=50,
                        default=500,
                    ),
                    Field(
                        "filter_background_audio",
                        "Filter background audio",
                        "boolean",
                    ),
                ),
            ),
        },
    ),
    "deepgram": ProviderSpec(
        label="Deepgram",
        api_key_env="DEEPGRAM_API_KEY",
        default_model="nova-3",
        models={
            "nova-3": ModelSpec(
                "Nova-3",
                (
                    Field(
                        "language",
                        "Language",
                        "select",
                        options=_LANG + ("multi",),
                        default="hi",
                    ),
                    Field("smart_format", "Smart format", "boolean", default=True),
                    Field("punctuate", "Punctuate", "boolean", default=True),
                    Field("interim_results", "Interim results", "boolean", default=True),
                    Field(
                        "utterance_end_ms",
                        "Utterance end (ms)",
                        "number",
                        min=500,
                        max=5000,
                        step=100,
                        default=1000,
                    ),
                    Field(
                        "endpointing",
                        "Endpointing (ms)",
                        "number",
                        min=100,
                        max=5000,
                        step=100,
                        default=300,
                    ),
                ),
            ),
        },
    ),
}

LLM_CATALOG: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        label="Groq",
        api_key_env="GROQ_API_KEY",
        default_model="openai/gpt-oss-120b",
        models={
            "openai/gpt-oss-120b": ModelSpec("GPT-OSS 120B", _LLM_FIELDS),
            "openai/gpt-oss-20b": ModelSpec("GPT-OSS 20B", _LLM_FIELDS),
            "qwen/qwen3.6-27b": ModelSpec("Qwen3.6 27B", _LLM_FIELDS),
        },
    ),
    "openai": ProviderSpec(
        label="OpenAI",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        models={
            "gpt-4o-mini": ModelSpec("GPT-4o Mini", _LLM_FIELDS),
            "gpt-4.1-mini": ModelSpec("GPT-4.1 Mini", _LLM_FIELDS),
            "gpt-4o": ModelSpec("GPT-4o", _LLM_FIELDS),
        },
    ),
    "google": ProviderSpec(
        label="Google",
        api_key_env="GOOGLE_API_KEY",
        default_model="gemini-3.6-flash",
        models={
            "gemini-3.6-flash": ModelSpec(
                "Gemini 3.6 Flash",
                _LLM_FIELDS
                + (
                    Field(
                        "thinking",
                        "Thinking budget",
                        "number",
                        min=0,
                        max=24576,
                        step=256,
                        default=0,
                    ),
                    _GOOGLE_SAFETY_FIELD,
                ),
            ),
            "gemini-2.5-flash": ModelSpec(
                "Gemini 2.5 Flash",
                _LLM_FIELDS
                + (
                    Field(
                        "thinking",
                        "Thinking budget",
                        "number",
                        min=0,
                        max=24576,
                        step=256,
                        default=0,
                    ),
                    _GOOGLE_SAFETY_FIELD,
                ),
            ),
            "gemini-2.5-flash-lite": ModelSpec(
                "Gemini 2.5 Flash Lite",
                _LLM_FIELDS + (_GOOGLE_SAFETY_FIELD,),
            ),
            "gemini-2.5-pro": ModelSpec(
                "Gemini 2.5 Pro",
                _LLM_FIELDS
                + (
                    Field(
                        "thinking",
                        "Thinking budget",
                        "number",
                        min=0,
                        max=24576,
                        step=256,
                        default=0,
                    ),
                    _GOOGLE_SAFETY_FIELD,
                ),
            ),
            "gemini-3.5-flash": ModelSpec(
                "Gemini 3.5 Flash",
                _LLM_FIELDS
                + (
                    Field(
                        "thinking",
                        "Thinking budget",
                        "number",
                        min=0,
                        max=24576,
                        step=256,
                        default=0,
                    ),
                    _GOOGLE_SAFETY_FIELD,
                ),
            ),
        },
    ),
}

TTS_CATALOG: dict[str, ProviderSpec] = {
    "cartesia": ProviderSpec(
        label="Cartesia",
        api_key_env="CARTESIA_API_KEY",
        voice_env="CARTESIA_VOICE_ID",
        default_model="sonic-3.5",
        models={
            "sonic-3.5": ModelSpec(
                "Sonic 3.5",
                (
                    Field("voice", "Voice ID", "string"),
                    Field(
                        "language",
                        "Language",
                        "select",
                        options=_LANG,
                        default="hi",
                    ),
                    Field("generation_config.emotion", "Emotion", "string"),
                ),
                recommended_voices=_CARTESIA_VOICES,
            ),
            "sonic-3": ModelSpec(
                "Sonic 3",
                (
                    Field("voice", "Voice ID", "string"),
                    Field(
                        "language",
                        "Language",
                        "select",
                        options=_LANG,
                        default="hi",
                    ),
                    Field(
                        "generation_config.speed",
                        "Speed",
                        "number",
                        min=0.6,
                        max=1.5,
                        step=0.05,
                        default=1.0,
                    ),
                    Field(
                        "generation_config.volume",
                        "Volume",
                        "number",
                        min=0.5,
                        max=2.0,
                        step=0.05,
                        default=1.0,
                    ),
                    Field("generation_config.emotion", "Emotion", "string"),
                ),
                recommended_voices=_CARTESIA_VOICES,
            ),
        },
    ),
    "elevenlabs": ProviderSpec(
        label="ElevenLabs",
        api_key_env="ELEVENLABS_API_KEY",
        voice_env="ELEVENLABS_VOICE_ID",
        default_model="eleven_flash_v2_5",
        models={
            "eleven_flash_v2_5": ModelSpec(
                "Flash v2.5",
                _EL_BASE + _EL_SPEED,
                recommended_voices=_ELEVENLABS_VOICES,
            ),
            "eleven_flash_v2": ModelSpec(
                "Flash v2",
                _EL_BASE + _EL_SPEED,
                recommended_voices=_ELEVENLABS_VOICES,
            ),
            "eleven_v3": ModelSpec(
                "Eleven v3",
                _EL_BASE,
                recommended_voices=_ELEVENLABS_VOICES,
            ),
        },
    ),
    "deepgram": ProviderSpec(
        label="Deepgram",
        api_key_env="DEEPGRAM_API_KEY",
        default_model="aura-2-thalia-en",
        voice_mode="deepgram_model",
        models={
            "aura-2-thalia-en": ModelSpec(
                "Aura-2 Thalia (en)",
                (),
                recommended_voices=(
                    RecommendedVoice("aura-2-thalia-en", "Thalia", "female", "en"),
                ),
            ),
            "aura-2-helena-en": ModelSpec(
                "Aura-2 Helena (en)",
                (),
                recommended_voices=(
                    RecommendedVoice("aura-2-helena-en", "Helena", "female", "en"),
                ),
            ),
            "aura-2-odysseus-en": ModelSpec(
                "Aura-2 Odysseus (en)",
                (),
                recommended_voices=(
                    RecommendedVoice("aura-2-odysseus-en", "Odysseus", "male", "en"),
                ),
            ),
            "aura-2-arcas-en": ModelSpec(
                "Aura-2 Arcas (en)",
                (),
                recommended_voices=(
                    RecommendedVoice("aura-2-arcas-en", "Arcas", "male", "en"),
                ),
            ),
        },
    ),
    "sarvam": ProviderSpec(
        label="Sarvam",
        api_key_env="SARVAM_API_KEY",
        voice_env="SARVAM_TTS_SPEAKER",
        voice_mode="sarvam_speaker",
        default_model="bulbul:v3",
        models={
            "bulbul:v3": ModelSpec(
                "Bulbul v3",
                (
                    Field(
                        "voice",
                        "Speaker",
                        "select",
                        options=("shubh", "ashutosh", "priya", "suhani"),
                        default="shubh",
                    ),
                    Field(
                        "language",
                        "Language",
                        "select",
                        options=_LANG,
                        default="hi",
                    ),
                    Field(
                        "pace",
                        "Pace",
                        "number",
                        min=0.5,
                        max=2.0,
                        step=0.05,
                        default=1.0,
                    ),
                    Field(
                        "temperature",
                        "Temperature",
                        "number",
                        min=0.01,
                        max=2.0,
                        step=0.05,
                        default=0.6,
                    ),
                ),
                recommended_voices=_SARVAM_SPEAKERS,
            ),
        },
    ),
    "soniox": ProviderSpec(
        label="Soniox",
        api_key_env="SONIOX_API_KEY",
        voice_env="SONIOX_TTS_VOICE",
        default_model="tts-rt-v1",
        models={
            "tts-rt-v1": ModelSpec(
                "TTS v1",
                (
                    Field("voice", "Voice", "string"),
                    Field(
                        "language",
                        "Language",
                        "select",
                        options=_LANG,
                        default="hi",
                    ),
                    Field(
                        "speed",
                        "Speed",
                        "number",
                        min=0.7,
                        max=1.3,
                        step=0.05,
                        default=1.0,
                    ),
                ),
                recommended_voices=_SONIOX_VOICES,
            ),
        },
    ),
}

_CATALOGS: dict[Kind, dict[str, ProviderSpec]] = {
    "stt": STT_CATALOG,
    "llm": LLM_CATALOG,
    "tts": TTS_CATALOG,
}

_DEFAULT_PROVIDERS: dict[Kind, str] = {
    "stt": "sarvam",
    "llm": "groq",
    "tts": "cartesia",
}


def default_provider(kind: Kind) -> str:
    return _DEFAULT_PROVIDERS[kind]


def default_model(kind: Kind, provider: str) -> str:
    spec = get_provider(kind, provider)
    return spec.default_model


def get_provider(kind: Kind, provider: str) -> ProviderSpec:
    catalog_map = _CATALOGS.get(kind, {})
    key = (provider or "").strip().lower()
    if key not in catalog_map:
        raise ValueError(f"Unknown {kind} provider: {provider!r}")
    return catalog_map[key]


def get_model(kind: Kind, provider: str, model: str) -> ModelSpec:
    pspec = get_provider(kind, provider)
    mid = (model or "").strip()
    if mid not in pspec.models:
        raise ValueError(
            f"Unknown {kind} model {model!r} for provider {provider!r}"
        )
    return pspec.models[mid]


# Hindi outbound voice-agent presets for the default cascade stack.
DEFAULT_CASCADE_TTS_VOICE = "c1abd502-9231-4558-a054-10ac950c356d"

_OPTIMIZED_ROLE_SETTINGS: dict[tuple[Kind, str, str], dict[str, Any]] = {
    ("stt", "sarvam", "saaras:v3"): {
        "language": "hi-IN",
        "mode": "transcribe",
    },
    ("llm", "groq", "openai/gpt-oss-120b"): {
        "temperature": 0.2,
        "max_tokens": 512,
        "top_p": 0.95,
    },
    ("tts", "cartesia", "sonic-3.5"): {
        "language": "hi",
        "voice": DEFAULT_CASCADE_TTS_VOICE,
    },
}


def build_settings_from_model(model_spec: ModelSpec) -> dict[str, Any]:
    """Build settings dict from catalog field defaults only."""
    settings: dict[str, Any] = {}
    for field in model_spec.fields:
        if field.default is not None:
            settings[field.key] = field.default
        elif field.required:
            settings[field.key] = False if field.type == "boolean" else ""
    return settings


def default_role_settings(
    kind: Kind,
    provider: str | None = None,
    model: str | None = None,
    *,
    optimized: bool = True,
) -> dict[str, Any]:
    """Settings for a catalog role, optionally merged with voice-agent presets."""
    provider_key = (provider or default_provider(kind)).strip().lower()
    model_key = (model or default_model(kind, provider_key)).strip()
    model_spec = get_model(kind, provider_key, model_key)
    settings = build_settings_from_model(model_spec)
    if optimized:
        settings.update(_OPTIMIZED_ROLE_SETTINGS.get((kind, provider_key, model_key), {}))
    return settings


def default_cascade_boilerplate(*, optimized: bool = True) -> dict[str, Any]:
    """Optimized STT/LLM/TTS settings and voice for the default cascade providers."""
    stt_provider = default_provider("stt")
    llm_provider = default_provider("llm")
    tts_provider = default_provider("tts")
    tts_settings = default_role_settings(
        "tts", tts_provider, default_model("tts", tts_provider), optimized=optimized
    )
    voice = (
        tts_settings.get("voice") or DEFAULT_CASCADE_TTS_VOICE
        if optimized
        else ""
    )
    return {
        "cascade_stt_settings": default_role_settings(
            "stt", stt_provider, default_model("stt", stt_provider), optimized=optimized
        ),
        "cascade_llm_settings": default_role_settings(
            "llm", llm_provider, default_model("llm", llm_provider), optimized=optimized
        ),
        "cascade_tts_settings": tts_settings,
        "cascade_tts_voice": voice,
    }


def _field_to_json(f: Field) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": f.key,
        "label": f.label,
        "type": f.type,
        "required": f.required,
    }
    if f.default is not None:
        out["default"] = f.default
    if f.options is not None:
        out["options"] = list(f.options)
    if f.min is not None:
        out["min"] = f.min
    if f.max is not None:
        out["max"] = f.max
    if f.step is not None:
        out["step"] = f.step
    return out


def _voice_to_json(v: RecommendedVoice) -> dict[str, Any]:
    return {
        "id": v.id,
        "label": v.label,
        "gender": v.gender,
        "language": v.language,
    }


def catalog_as_json() -> dict[str, Any]:
    """Serialize catalog for admin UI; omits api_key_env, adds key_configured."""
    result: dict[str, Any] = {}
    for kind, catalog_map in _CATALOGS.items():
        kind_out: dict[str, Any] = {}
        for key, pspec in catalog_map.items():
            models_out: dict[str, Any] = {}
            for mid, mspec in pspec.models.items():
                entry: dict[str, Any] = {
                    "label": mspec.label,
                    "fields": [_field_to_json(f) for f in mspec.fields],
                }
                if mspec.recommended_voices:
                    entry["recommended_voices"] = [
                        _voice_to_json(v) for v in mspec.recommended_voices
                    ]
                models_out[mid] = entry
            kind_out[key] = {
                "label": pspec.label,
                "default_model": pspec.default_model,
                "key_configured": bool((os.getenv(pspec.api_key_env) or "").strip()),
                "models": models_out,
            }
        result[kind] = kind_out
    return result

"""Unit tests for providers/factory.py."""

from __future__ import annotations

import json

import pytest

from providers.factory import create_stt_service, create_llm_service, create_tts_service

_PROVIDER_ENV = {
    "SARVAM_API_KEY": "sk-sarvam",
    "DEEPGRAM_API_KEY": "sk-deepgram",
    "GROQ_API_KEY": "sk-groq",
    "OPENAI_API_KEY": "sk-openai",
    "GOOGLE_API_KEY": "sk-google",
    "CARTESIA_API_KEY": "sk-cartesia",
    "ELEVENLABS_API_KEY": "sk-eleven",
    "SONIOX_API_KEY": "sk-soniox",
    "CARTESIA_VOICE_ID": "voice-cartesia",
    "ELEVENLABS_VOICE_ID": "voice-eleven",
    "SARVAM_TTS_SPEAKER": "shubh",
    "SONIOX_TTS_VOICE": "Adrian",
}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    for key in _PROVIDER_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("factory", "args", "env"),
    [
        (
            create_stt_service,
            ("sarvam", "saaras:v3", {}),
            {"SARVAM_API_KEY": "sk-sarvam"},
        ),
        (
            create_stt_service,
            ("soniox", "stt-rt-v5", {}),
            {"SONIOX_API_KEY": "sk-soniox"},
        ),
        (
            create_stt_service,
            ("elevenlabs", "scribe_v2_realtime", {"language": "hi"}),
            {"ELEVENLABS_API_KEY": "sk-eleven"},
        ),
        (
            create_stt_service,
            ("deepgram", "nova-3", {"language": "hi"}),
            {"DEEPGRAM_API_KEY": "sk-deepgram"},
        ),
        (
            create_llm_service,
            ("groq", "openai/gpt-oss-120b", {"temperature": 0.2}),
            {"GROQ_API_KEY": "sk-groq"},
        ),
        (
            create_llm_service,
            ("openai", "gpt-4o-mini", {}),
            {"OPENAI_API_KEY": "sk-openai"},
        ),
        (
            create_llm_service,
            ("openai", "gpt-4.1-mini", {}),
            {"OPENAI_API_KEY": "sk-openai"},
        ),
        (
            create_llm_service,
            ("google", "gemini-3.6-flash", {}),
            {"GOOGLE_API_KEY": "sk-google"},
        ),
        (
            create_tts_service,
            ("cartesia", "sonic-3.5", {"language": "hi"}),
            {"CARTESIA_API_KEY": "sk-cartesia", "CARTESIA_VOICE_ID": "voice-cartesia"},
        ),
        (
            create_tts_service,
            ("elevenlabs", "eleven_flash_v2_5", {}),
            {"ELEVENLABS_API_KEY": "sk-eleven", "ELEVENLABS_VOICE_ID": "voice-eleven"},
        ),
        (
            create_tts_service,
            ("deepgram", "aura-2-thalia-en", {}),
            {"DEEPGRAM_API_KEY": "sk-deepgram"},
        ),
        (
            create_tts_service,
            ("sarvam", "bulbul:v3", {"voice": "shubh"}),
            {"SARVAM_API_KEY": "sk-sarvam"},
        ),
        (
            create_tts_service,
            ("soniox", "tts-rt-v1", {"language": "hi"}),
            {"SONIOX_API_KEY": "sk-soniox", "SONIOX_TTS_VOICE": "Adrian"},
        ),
    ],
)
async def test_each_provider_builds(
    monkeypatch: pytest.MonkeyPatch,
    factory,
    args,
    env,
):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if factory is create_llm_service:
        svc = await factory(*args, system_prompt="hello")
    elif factory is create_tts_service:
        svc = await factory(*args, voice="")
    else:
        svc = await factory(*args)
    assert svc is not None


@pytest.mark.asyncio
async def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk-sarvam")
    with pytest.raises(ValueError, match="Unknown stt provider"):
        await create_stt_service("not-a-vendor", "saaras:v3", {})


@pytest.mark.asyncio
async def test_unknown_model_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-groq")
    with pytest.raises(ValueError, match="Unknown llm model"):
        await create_llm_service(
            "groq",
            "not-a-model",
            {},
            system_prompt="hi",
        )


@pytest.mark.asyncio
async def test_stale_settings_key_dropped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven")
    svc = await create_tts_service(
        "elevenlabs",
        "eleven_v3",
        {"speed": 1.0, "language": "hi"},
        voice="voice-eleven",
    )
    assert svc._settings.extra == {}
    assert svc._settings.speed is None


@pytest.mark.asyncio
async def test_cartesia_dotted_keys_become_generation_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia")
    svc = await create_tts_service(
        "cartesia",
        "sonic-3",
        {
            "generation_config.speed": 1.1,
            "generation_config.volume": 1.0,
            "language": "hi",
        },
        voice="voice-cartesia",
    )
    assert svc._settings.generation_config.speed == 1.1
    assert svc._settings.generation_config.volume == 1.0


@pytest.mark.asyncio
async def test_sonic_35_rejects_speed_in_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia")
    svc = await create_tts_service(
        "cartesia",
        "sonic-3.5",
        {"generation_config.speed": 1.1, "language": "hi"},
        voice="voice-cartesia",
    )
    assert svc._settings.generation_config is None or not hasattr(
        svc._settings.generation_config, "speed"
    ) or svc._settings.generation_config.speed is None


@pytest.mark.asyncio
async def test_stt_uses_telephony_sample_rate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk-sarvam")
    svc = await create_stt_service("sarvam", "saaras:v3", {})
    assert svc._init_sample_rate == 8000


@pytest.mark.asyncio
async def test_tts_pause_watchdog_timeout_is_telephony_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    from providers.factory import TTS_PAUSE_WATCHDOG_TIMEOUT_S

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-eleven")
    from providers.factory import ELEVENLABS_TTS_SAMPLE_RATE

    svc = await create_tts_service("elevenlabs", "eleven_flash_v2_5", {}, voice="")
    assert svc._pause_watchdog_timeout_s == TTS_PAUSE_WATCHDOG_TIMEOUT_S
    assert svc._pause_watchdog_timeout_s > 3.0
    assert svc._init_sample_rate == ELEVENLABS_TTS_SAMPLE_RATE


@pytest.mark.asyncio
async def test_elevenlabs_tts_language_hi_becomes_language_enum(
    monkeypatch: pytest.MonkeyPatch,
):
    from pipecat.transcriptions.language import Language

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-eleven")
    svc = await create_tts_service(
        "elevenlabs",
        "eleven_flash_v2_5",
        {"language": "hi"},
        voice="",
    )
    assert svc._settings.language == Language.HI


@pytest.mark.asyncio
async def test_sarvam_mode_reaches_constructor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk-sarvam")
    svc = await create_stt_service(
        "sarvam",
        "saaras:v3",
        {"mode": "translate", "language": "hi-IN"},
    )
    assert getattr(svc, "_mode", None) == "translate"
    assert "mode" not in svc._settings.extra


@pytest.mark.asyncio
async def test_deepgram_tts_uses_model_as_voice(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "sk-deepgram")
    svc = await create_tts_service("deepgram", "aura-2-thalia-en", {}, voice="")
    assert svc._settings.voice == "aura-2-thalia-en"
    assert svc._settings.model == "aura-2-thalia-en"


@pytest.mark.asyncio
async def test_sarvam_tts_speaker_from_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk-sarvam")
    svc = await create_tts_service(
        "sarvam",
        "bulbul:v3",
        {"voice": "priya"},
        voice="",
    )
    assert svc._settings.voice == "priya"


@pytest.mark.asyncio
async def test_missing_env_key_raises_named_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Groq: GROQ_API_KEY is not set"):
        await create_llm_service(
            "groq",
            "openai/gpt-oss-120b",
            {},
            system_prompt="hi",
        )


@pytest.mark.asyncio
async def test_tts_voice_falls_back_to_voice_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia")
    monkeypatch.setenv("CARTESIA_VOICE_ID", "env-voice")
    svc = await create_tts_service("cartesia", "sonic-3.5", {}, voice="")
    assert svc._settings.voice == "env-voice"


_SAFETY_ITEM = {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_NONE",
}


@pytest.mark.asyncio
async def test_elevenlabs_stt_filter_background_audio_true(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven")
    svc = await create_stt_service(
        "elevenlabs",
        "scribe_v2_realtime",
        {"language": "hi", "filter_background_audio": True},
    )
    assert svc._settings.filter_background_audio is True


@pytest.mark.asyncio
async def test_elevenlabs_stt_filter_background_audio_omitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven")
    svc = await create_stt_service(
        "elevenlabs",
        "scribe_v2_realtime",
        {"language": "hi"},
    )
    assert svc._settings.filter_background_audio is not True


@pytest.mark.asyncio
async def test_google_safety_settings_json_string(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    svc = await create_llm_service(
        "google",
        "gemini-3.6-flash",
        {"safety_settings": json.dumps([_SAFETY_ITEM])},
        system_prompt="hi",
    )
    assert svc._settings.safety_settings is not None
    assert len(svc._settings.safety_settings) == 1


@pytest.mark.asyncio
async def test_google_safety_settings_list_passthrough(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    svc = await create_llm_service(
        "google",
        "gemini-3.6-flash",
        {"safety_settings": [_SAFETY_ITEM]},
        system_prompt="hi",
    )
    assert len(svc._settings.safety_settings) == 1


@pytest.mark.asyncio
async def test_google_safety_settings_empty_string_omitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    baseline = await create_llm_service(
        "google",
        "gemini-3.6-flash",
        {},
        system_prompt="hi",
    )
    svc = await create_llm_service(
        "google",
        "gemini-3.6-flash",
        {"safety_settings": "  "},
        system_prompt="hi",
    )
    assert svc._settings.safety_settings == baseline._settings.safety_settings


@pytest.mark.asyncio
async def test_google_safety_settings_invalid_json_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
    with pytest.raises(ValueError, match="valid JSON"):
        await create_llm_service(
            "google",
            "gemini-3.6-flash",
            {"safety_settings": "{not-json"},
            system_prompt="hi",
        )


@pytest.mark.asyncio
async def test_tts_voice_raises_when_blank(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia")
    monkeypatch.delenv("CARTESIA_VOICE_ID", raising=False)
    with pytest.raises(ValueError, match="no voice id"):
        await create_tts_service("cartesia", "sonic-3.5", {}, voice="")

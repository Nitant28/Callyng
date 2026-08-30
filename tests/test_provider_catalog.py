"""Unit tests for providers/catalog.py."""

from __future__ import annotations

import dataclasses

import pytest

from providers import catalog


def test_default_models_exist_in_catalog():
    for kind in ("stt", "llm", "tts"):
        provider = catalog.default_provider(kind)  # type: ignore[arg-type]
        model = catalog.default_model(kind, provider)  # type: ignore[arg-type]
        catalog.get_model(kind, provider, model)  # type: ignore[arg-type]


def test_stt_defaults_are_2026_models():
    assert catalog.default_model("stt", "sarvam") == "saaras:v3"
    assert catalog.default_model("stt", "deepgram") == "nova-3"
    assert catalog.default_model("stt", "soniox") == "stt-rt-v5"
    assert catalog.default_model("stt", "elevenlabs") == "scribe_v2_realtime"


def test_google_llm_defaults_are_current():
    assert catalog.default_model("llm", "google") == "gemini-3.6-flash"
    catalog.get_model("llm", "google", "gemini-3.5-flash")
    catalog.get_model("llm", "openai", "gpt-4.1-mini")
    assert catalog.default_model("tts", "cartesia") == "sonic-3.5"
    assert catalog.default_model("tts", "elevenlabs") == "eleven_flash_v2_5"
    assert catalog.default_model("tts", "deepgram") == "aura-2-thalia-en"
    assert catalog.default_model("tts", "sarvam") == "bulbul:v3"
    assert catalog.default_model("tts", "soniox") == "tts-rt-v1"


def test_legacy_models_removed():
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_model("stt", "sarvam", "saarika:v2.5")
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_model("stt", "deepgram", "nova-2")
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_model("tts", "elevenlabs", "eleven_turbo_v2_5")
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_model("llm", "google", "gemini-2.0-flash")
    with pytest.raises(ValueError, match="Unknown"):
        catalog.get_model("llm", "groq", "llama-3.3-70b-versatile")


def test_eleven_v3_has_no_speed_while_flash_does():
    v3 = catalog.get_model("tts", "elevenlabs", "eleven_v3")
    flash = catalog.get_model("tts", "elevenlabs", "eleven_flash_v2_5")
    assert "speed" not in v3.field_keys
    assert "speed" in flash.field_keys


def test_sonic_35_has_no_speed_while_sonic_3_does():
    sonic35 = catalog.get_model("tts", "cartesia", "sonic-3.5")
    sonic3 = catalog.get_model("tts", "cartesia", "sonic-3")
    assert "generation_config.speed" not in sonic35.field_keys
    assert "generation_config.speed" in sonic3.field_keys


def test_recommended_voices_in_json():
    data = catalog.catalog_as_json()
    cartesia = data["tts"]["cartesia"]["models"]["sonic-3.5"]
    assert len(cartesia["recommended_voices"]) == 4
    assert cartesia["recommended_voices"][0]["gender"] in ("male", "female")


def test_catalog_as_json_never_leaks_api_key_env():
    data = catalog.catalog_as_json()
    dumped = str(data)
    assert "API_KEY" not in dumped
    for kind in data.values():
        for provider in kind.values():
            assert "api_key_env" not in provider
            assert "key_configured" in provider


@pytest.mark.parametrize(
    ("kind", "provider", "settings_cls"),
    [
        ("stt", "sarvam", "pipecat.services.sarvam.stt.SarvamSTTSettings"),
        ("stt", "soniox", "pipecat.services.soniox.stt.SonioxSTTSettings"),
        (
            "stt",
            "elevenlabs",
            "pipecat.services.elevenlabs.stt.ElevenLabsRealtimeSTTSettings",
        ),
        ("stt", "deepgram", "pipecat.services.deepgram.stt.DeepgramSTTSettings"),
        ("llm", "groq", "pipecat.services.groq.llm.GroqLLMSettings"),
        ("llm", "openai", "pipecat.services.openai.base_llm.OpenAILLMSettings"),
        ("llm", "google", "pipecat.services.google.llm.GoogleLLMSettings"),
        ("tts", "cartesia", "pipecat.services.cartesia.tts.CartesiaTTSSettings"),
        ("tts", "elevenlabs", "pipecat.services.elevenlabs.tts.ElevenLabsTTSSettings"),
        ("tts", "deepgram", "pipecat.services.deepgram.tts.DeepgramTTSSettings"),
        ("tts", "sarvam", "pipecat.services.sarvam.tts.SarvamTTSSettings"),
        ("tts", "soniox", "pipecat.services.soniox.tts.SonioxTTSSettings"),
    ],
)
def test_catalog_field_keys_match_pipecat_settings(
    kind: str, provider: str, settings_cls: str
):
    import importlib

    mod_path, cls_name = settings_cls.rsplit(".", 1)
    settings_class = getattr(importlib.import_module(mod_path), cls_name)
    pipecat_fields = {f.name for f in dataclasses.fields(settings_class)}
    nested_paths = {
        "generation_config.speed",
        "generation_config.volume",
        "generation_config.emotion",
    }
    pspec = catalog.get_provider(kind, provider)  # type: ignore[arg-type]
    for mid, mspec in pspec.models.items():
        for field in mspec.fields:
            if field.ctor:
                continue
            if field.key in nested_paths:
                assert field.key.startswith("generation_config.")
                continue
            assert field.key in pipecat_fields, (
                f"{kind}/{provider}/{mid}: {field.key} not on {settings_cls}"
            )


def test_default_cascade_boilerplate_matches_default_stack():
    boilerplate = catalog.default_cascade_boilerplate()
    assert boilerplate["cascade_stt_settings"] == {
        "language": "hi-IN",
        "mode": "transcribe",
    }
    assert boilerplate["cascade_llm_settings"] == {
        "temperature": 0.2,
        "max_tokens": 512,
        "top_p": 0.95,
    }
    assert boilerplate["cascade_tts_settings"]["language"] == "hi"
    assert boilerplate["cascade_tts_settings"]["voice"] == catalog.DEFAULT_CASCADE_TTS_VOICE
    assert boilerplate["cascade_tts_voice"] == catalog.DEFAULT_CASCADE_TTS_VOICE


def test_elevenlabs_stt_has_opt_in_background_audio_filter():
    spec = catalog.get_model("stt", "elevenlabs", "scribe_v2_realtime")
    field = next(f for f in spec.fields if f.key == "filter_background_audio")
    assert field.type == "boolean"
    assert field.required is False
    assert field.default is None
    boilerplate = catalog.default_cascade_boilerplate()
    assert "filter_background_audio" not in boilerplate["cascade_stt_settings"]


def test_google_llm_models_have_safety_settings_string():
    provider = catalog.get_provider("llm", "google")
    for model_id, spec in provider.models.items():
        field = next(f for f in spec.fields if f.key == "safety_settings")
        assert field.type == "string", model_id
        assert field.required is False
        assert field.default is None
    boilerplate = catalog.default_cascade_boilerplate()
    assert "safety_settings" not in boilerplate["cascade_llm_settings"]


def test_catalog_as_json_exposes_new_1_7_fields():
    data = catalog.catalog_as_json()
    el_keys = {
        f["key"] for f in data["stt"]["elevenlabs"]["models"]["scribe_v2_realtime"]["fields"]
    }
    assert "filter_background_audio" in el_keys
    el_field = next(
        f
        for f in data["stt"]["elevenlabs"]["models"]["scribe_v2_realtime"]["fields"]
        if f["key"] == "filter_background_audio"
    )
    assert el_field["type"] == "boolean"
    google_flash = data["llm"]["google"]["models"]["gemini-3.6-flash"]["fields"]
    safety = next(f for f in google_flash if f["key"] == "safety_settings")
    assert safety["type"] == "string"
    assert safety["label"]


def test_default_cascade_boilerplate_validates():
    from api.script_config_validation import validate_cascade_config

    data = {
        "route": "cascaded",
        "cascade_stt_provider": catalog.default_provider("stt"),
        "cascade_stt_model": catalog.default_model("stt", catalog.default_provider("stt")),
        "cascade_llm_provider": catalog.default_provider("llm"),
        "cascade_llm_model": catalog.default_model("llm", catalog.default_provider("llm")),
        "cascade_tts_provider": catalog.default_provider("tts"),
        "cascade_tts_model": catalog.default_model("tts", catalog.default_provider("tts")),
        **catalog.default_cascade_boilerplate(),
    }
    validate_cascade_config(data)

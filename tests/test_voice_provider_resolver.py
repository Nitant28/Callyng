"""Unit tests for selectable Voice / TTS Provider (ElevenLabs vs Telnyx/Cartesia/Sarvam/Deepgram)."""

import pytest
import os

from providers import catalog
from providers.factory import create_tts_service


def test_catalog_tts_providers_present():
    tts_cat = catalog.TTS_CATALOG
    assert "elevenlabs" in tts_cat
    assert "cartesia" in tts_cat
    assert "sarvam" in tts_cat
    assert "deepgram" in tts_cat
    assert "soniox" in tts_cat


def test_elevenlabs_provider_spec():
    spec = catalog.get_provider("tts", "elevenlabs")
    assert spec.label == "ElevenLabs"
    assert spec.api_key_env == "ELEVENLABS_API_KEY"
    assert "eleven_turbo_v2_5" in spec.models
    assert "eleven_multilingual_v2" in spec.models
    assert "eleven_flash_v2_5" in spec.models


def test_cartesia_provider_spec():
    spec = catalog.get_provider("tts", "cartesia")
    assert spec.label == "Cartesia"
    assert spec.api_key_env == "CARTESIA_API_KEY"


@pytest.mark.asyncio
async def test_create_elevenlabs_tts_service():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ELEVENLABS_API_KEY", "el_test_key_123")
        tts = await create_tts_service(
            provider="elevenlabs",
            model="eleven_multilingual_v2",
            settings={"language": "hi"},
            voice="21m00Tcm4TlvDq8ikWAM",
        )
        assert tts is not None


@pytest.mark.asyncio
async def test_create_cartesia_tts_service():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CARTESIA_API_KEY", "cartesia_test_key_123")
        tts = await create_tts_service(
            provider="cartesia",
            model="sonic-3.5",
            settings={},
            voice="bdab08ad-4137-4548-b9db-6142854c7525",
        )
        assert tts is not None

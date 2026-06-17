"""Unit tests for script_prefetch (Redis required for register/pop)."""

from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv

import script_prefetch as sp

load_dotenv(override=True)


async def _redis_test(coro):
    from db import redis_client as redis_db
    redis = redis_db.get_redis()
    async for key in redis.scan_iter(match="prefetch:*"):
        await redis.delete(key)
    return await coro()


@pytest.mark.asyncio

async def test_build_lead_dict_filters_metadata_keys():
    lead = {"name": "Satyam", "phone": "+919123866924"}
    meta = {
        "city": "Pune",
        "bhk": "2BHK",
        "City": "ignored",
        "../x": "bad",
        "9bad": "bad",
    }
    d = sp.build_lead_dict(lead, meta)
    assert d["lead_name"] == "Satyam"
    assert d["lead_phone"] == "+919123866924"
    assert d["lead_city"] == "Pune"
    assert d["bhk"] == "2BHK"
    assert "City" not in d
    assert "../x" not in d
    assert "9bad" not in d


@pytest.mark.asyncio
async def test_render_script_config_substitutes_templates():
    sc = {
        "id": "00000000-0000-4000-8000-000000000099",
        "script_id": "pyramid_mr",
        "route": "sts",
        "version": 2,
        "system_instruction_template": "Hello $lead_name from $lead_city",
        "bootstrap_messages_json": [
            {"role": "user", "content": "Connected. Greet $lead_name."},
        ],
        "goodbye_markers": ["bye"],
        "gemini_model": "models/gemini-3.1-flash-live-preview",
        "gemini_voice": "Aoede",
        "gemini_language": "hi-IN",
        "gemini_temperature": 0.5,
        "vad_start_sensitivity": "HIGH",
        "vad_end_sensitivity": "LOW",
        "vad_silence_duration_ms": 800,
        "vad_prefix_padding_ms": 300,
        "cascade_stt_provider": "sarvam",
        "cascade_stt_model": "saarika:v2.5",
        "cascade_llm_provider": "groq",
        "cascade_llm_model": "llama-3.3-70b-versatile",
        "cascade_tts_provider": "cartesia",
        "cascade_tts_voice": "sonic-3",
        "cascade_live_tools": [],
        "extraction_schema": {"fields": {}},
        "lead_schema": {"fields": []},
        "normalization_rules": [],
        "outcome_event_map": {},
        "outcome_terminal": ["Interested"],
        "outcome_retry": ["Busy"],
        "outcome_callback": ["Callback_Requested"],
    }
    lead_dict = {"lead_name": "Asha", "lead_city": "Mumbai", "lead_phone": "+911"}
    cfg = sp.render_script_config(sc, lead_dict, expected_route="sts")
    assert cfg["source"] == "script_config"
    assert cfg["system_instruction"] == "Hello Asha from Mumbai"
    assert cfg["system_prompt"] == "Hello Asha from Mumbai"
    assert cfg["bootstrap_messages"][0]["content"] == "Connected. Greet Asha."
    assert cfg["version"] == 2


@pytest.mark.asyncio

async def test_render_script_config_route_mismatch_raises():
    row = {"route": "cascaded"}
    with pytest.raises(ValueError, match="does not match"):
        sp.render_script_config(row, {}, expected_route="sts")


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
@pytest.mark.asyncio

async def test_sweep_stale_prefetched_configs():
    from db import redis_client
    await redis_client.init_redis()
    await sp.register_prefetched_config("call-live", {"route": "sts"})
    await sp.register_prefetched_config("call-done", {"route": "sts"})
    await sp.register_prefetched_config("call-orphan", {"route": "sts"})

    class _Pool:
        async def fetch(self, _sql, keys):
            assert "call-live" in keys
            return [{"session_call_id": "call-done"}]

    n = await sp.sweep_stale_prefetched_configs(_Pool())
    assert n == 1
    assert await sp.pop_prefetched_config("call-live") is not None
    assert await sp.pop_prefetched_config("call-done") is None
    assert await sp.pop_prefetched_config("call-orphan") is not None



@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
@pytest.mark.asyncio

async def test_register_and_pop_prefetched_config():
    from db import redis_client
    await redis_client.init_redis()
    await sp.register_prefetched_config("sid-1", {"route": "sts"})
    assert await sp.pop_prefetched_config("sid-1") == {"route": "sts"}
    assert await sp.pop_prefetched_config("sid-1") is None


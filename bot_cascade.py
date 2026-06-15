#
# bot_cascade.py — Aakashvani | Sarvam STT + Groq + Cartesia pipeline
#
# System prompt lives under cascade_scripts/ (see CASCADE_SCRIPT env).
#

from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import time
from datetime import datetime, timezone
from types import ModuleType

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from call_limits import (
    end_call_function_schema,
    make_end_call_handler,
    parse_max_call_minutes,
    schedule_max_call_duration,
)
from call_metrics import UsageMetricsAccumulator, UsageMetricsTap
from call_transcript import TranscriptBuffer, attach_pipeline_finalize
from lead_context import LeadContext

load_dotenv(override=True)

_CASCADE_SCRIPT_ATTRS = (
    "build_system_prompt",
    "EXTRACTION_SCHEMA",
)


def _load_cascade_script(script_id_override: str | None = None) -> ModuleType:
    raw = (script_id_override or os.getenv("CASCADE_SCRIPT") or "prowave").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", raw):
        raise ValueError(
            f"Invalid CASCADE_SCRIPT={raw!r}; use a snake_case module under cascade_scripts/"
        )
    mod_name = f"cascade_scripts.{raw}"
    mod = importlib.import_module(mod_name)
    missing = [a for a in _CASCADE_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(f"Cascade script {mod_name} missing: {', '.join(missing)}")
    return mod


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, plivo_call_id: str):
    body = getattr(runner_args, "body", {}) or {}
    ctx = LeadContext.from_body(body, default_lead_name="Sir")
    
    # 3-tier resolution order step 2: read script_id from _pg
    pg = body.get("_pg") or {}
    script_id_override = pg.get("script_id")
    
    casc = _load_cascade_script(script_id_override)
    sid = getattr(casc, "SCRIPT_ID", os.getenv("CASCADE_SCRIPT", "prowave"))
    logger.info("Cascade script active: {} ({})", sid, casc.__name__)

    logger.info("Starting cascaded bot — Diya (script %s)", sid)

    dynamic_prompt = casc.build_system_prompt(ctx)

    push_lead_data_fn = FunctionSchema(
        name="push_lead_data",
        description="Call this before ending every call to save lead qualification data. Always call this regardless of outcome.",
        properties={
            "intent_status": {
                "type": "string",
                "description": "Whether lead is interested: Yes, No, Busy, Callback, Unclear",
            },
            "bhk_preference": {
                "type": "string",
                "description": "BHK preference: 2BHK, 3BHK, NULL if not collected",
            },
            "location_preference": {
                "type": "string",
                "description": "Preferred location in Pune, or NULL if not collected",
            },
            "callback_time": {
                "type": "string",
                "description": "Requested callback time if busy, else NULL",
            },
            "language_used": {
                "type": "string",
                "description": "Language used in call: Hindi, Marathi, English",
            },
        },
        required=["intent_status", "bhk_preference", "location_preference"],
    )

    end_call_fn = end_call_function_schema()
    tools = ToolsSchema(standard_tools=[push_lead_data_fn, end_call_fn])

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamSTTService.Settings(
            model="saarika:v2.5",
            language="unknown",
        ),
    )

    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            system_instruction=dynamic_prompt,
            temperature=0.2,
        ),
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("CARTESIA_VOICE_ID"),
            model="sonic-3",
            language="hi",
        ),
        sample_rate=8000,
    )

    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    transcript_buffer = TranscriptBuffer()
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)
    transcript_buffer.register(user_aggregator, assistant_aggregator)

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        usage_tap,
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    pg = body.get("_pg") or {}
    max_minutes = parse_max_call_minutes(pg.get("max_call_minutes"))
    call_limits = schedule_max_call_duration(
        task, max_minutes, "max_call_duration"
    )
    coordinator = call_limits.coordinator

    async def handle_push_lead_data(params: FunctionCallParams):
        data = params.arguments
        logger.info(f"LEAD DATA CAPTURED: {json.dumps(data, ensure_ascii=False, indent=2)}")
        logger.info(
            "Phone: {} | Name: {} | City: {}",
            ctx.lead_phone,
            ctx.lead_name,
            ctx.lead_city,
        )
        await params.result_callback({"status": "saved"})

    llm.register_function("push_lead_data", handle_push_lead_data)
    llm.register_function("end_call", make_end_call_handler(coordinator))

    started_at_iso = datetime.now(timezone.utc).isoformat()
    perf_pipeline = time.perf_counter()
    pg = body.get("_pg") or {}
    extraction_schema = pg.get("extraction_schema_override") or casc.EXTRACTION_SCHEMA

    attach_pipeline_finalize(
        task,
        transcript_buffer,
        context,
        route=os.getenv("BOT_ROUTE", "cascade"),
        session_call_id=body.get("_session_call_id"),
        plivo_call_id=plivo_call_id,
        started_at_iso=started_at_iso,
        perf_start=perf_pipeline,
        strip_bootstrap=False,
        usage_accumulator=usage_accumulator,
        extraction_schema=extraction_schema,
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Call connected — Diya starting")
        await asyncio.sleep(1.0)
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Call disconnected")
        wt = call_limits.watchdog_task
        if wt is not None and not wt.done():
            wt.cancel()
            try:
                await wt
            except asyncio.CancelledError:
                pass
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(
        "Transport: %s | Call: %s",
        transport_type,
        call_data.get("call_id", "unknown"),
    )

    serializer = PlivoFrameSerializer(
        stream_id=call_data["stream_id"],
        call_id=call_data["call_id"],
        auth_id=os.getenv("PLIVO_AUTH_ID", ""),
        auth_token=os.getenv("PLIVO_AUTH_TOKEN", ""),
    )

    from_number = (
        bot_config.get("telephony_number")
        or os.getenv("PLIVO_PHONE_NUMBER", "")
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await run_bot(transport, runner_args, call_data["call_id"])

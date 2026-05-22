#
# bot_sts.py — Aakashvani | Gemini Live (STS) pipeline
#
# Persona text and Gemini tuning live under sts_scripts/ (see STS_SCRIPT env).
# Lead qualification is post-call (Groq in call_transcript.py).
#

from __future__ import annotations

import asyncio
import importlib
import os
import re
import time
from datetime import datetime, timezone
from types import ModuleType

from dotenv import load_dotenv
from google.genai.types import HttpOptions
from loguru import logger

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
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy

from call_limits import (
    end_call_function_schema,
    make_end_call_handler,
    parse_goodbye_hangup_delay_s,
    parse_goodbye_hangup_enabled,
    parse_max_call_minutes,
    register_goodbye_hangup_fallback,
    schedule_max_call_duration,
)
from call_metrics import UsageMetricsAccumulator, UsageMetricsTap
from call_transcript import TranscriptBuffer, attach_pipeline_finalize
from lead_context import LeadContext

load_dotenv(override=True)

_STS_SCRIPT_ATTRS = (
    "build_system_instruction",
    "build_bootstrap_messages",
    "GOODBYE_HANGUP_MARKERS",
    "GEMINI_MODEL",
    "GEMINI_VOICE",
    "GEMINI_LANGUAGE",
    "GEMINI_VAD",
    "GEMINI_TEMPERATURE",
    "EXTRACTION_SCHEMA",
)


def _load_sts_script() -> ModuleType:
    raw = (os.getenv("STS_SCRIPT") or "pyramid_mr").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", raw):
        raise ValueError(
            f"Invalid STS_SCRIPT={raw!r}; use a snake_case module name under sts_scripts/"
        )
    mod_name = f"sts_scripts.{raw}"
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        logger.error("Failed to import STS script {}: {}", mod_name, exc)
        raise
    missing = [a for a in _STS_SCRIPT_ATTRS if not hasattr(mod, a)]
    if missing:
        raise ValueError(f"STS script {mod_name} missing: {', '.join(missing)}")
    return mod


def _context_window_compression_settings() -> dict[str, int | bool] | None:
    """Gemini Live sliding-window compression (Pipecat → Google API).

    Pipecat's ``_connect`` reads this as a dict (``.get("enabled")``), not a Pydantic model.
    Retained token target defaults to trigger_tokens / 2 on the API side.
    Default trigger 20000 → ~10k retained.
    """
    raw = (os.getenv("GEMINI_CONTEXT_COMPRESSION") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return None
    try:
        trigger = int(os.getenv("GEMINI_CWC_TRIGGER_TOKENS", "20000"))
    except ValueError:
        trigger = 20000
    if trigger < 1:
        trigger = 20000
    return {"enabled": True, "trigger_tokens": trigger}


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
    t0: float,
    *,
    plivo_call_id: str,
):
    _lap(t0, "run_bot() entered — building pipeline")

    body = getattr(runner_args, "body", {}) or {}
    ctx = LeadContext.from_body(body)
    sts = _load_sts_script()
    sid = getattr(sts, "SCRIPT_ID", os.getenv("STS_SCRIPT", "pyramid_mr"))
    logger.info("STS script active: {} ({})", sid, sts.__name__)

    end_tools = ToolsSchema(standard_tools=[end_call_function_schema()])
    _affective = getattr(sts, "GEMINI_ENABLE_AFFECTIVE_DIALOG", False)
    if _affective and "gemini-3" in (getattr(sts, "GEMINI_MODEL", "") or ""):
        logger.warning(
            "GEMINI_ENABLE_AFFECTIVE_DIALOG ignored: {} does not support affective dialog "
            "(use a Gemini 2.5 Live model, e.g. "
            "models/gemini-2.5-flash-native-audio-preview-12-2025)",
            sts.GEMINI_MODEL,
        )
        _affective = False
    elif _affective:
        logger.info("Gemini affective dialog enabled (api_version=v1alpha)")

    cwc = _context_window_compression_settings()
    llm_settings_kw: dict = {
        "model": sts.GEMINI_MODEL,
        "voice": sts.GEMINI_VOICE,
        "language": sts.GEMINI_LANGUAGE,
        "vad": sts.GEMINI_VAD,
        "temperature": sts.GEMINI_TEMPERATURE,
    }
    if cwc is not None:
        llm_settings_kw["context_window_compression"] = cwc
    if _affective:
        llm_settings_kw["enable_affective_dialog"] = True

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        http_options=HttpOptions(api_version="v1alpha") if _affective else None,
        system_instruction=sts.build_system_instruction(ctx),
        tools=end_tools,
        settings=GeminiLiveLLMService.Settings(**llm_settings_kw),
    )
    _lap(t0, "GeminiLiveLLMService object created (not yet connected)")

    transcript_buffer = TranscriptBuffer()
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)

    bootstrap_messages = sts.build_bootstrap_messages(ctx)
    context = LLMContext(bootstrap_messages, tools=end_tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
    )

    pipeline = Pipeline([
        transport.input(),
        user_aggregator,
        llm,
        transport.output(),
        usage_tap,
        assistant_aggregator,
    ])
    _lap(t0, "Pipeline built")

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
    _lap(t0, "PipelineTask created — registering event handlers")

    max_minutes = parse_max_call_minutes()
    call_limits = schedule_max_call_duration(
        task, max_minutes, "max_call_duration"
    )
    coordinator = call_limits.coordinator
    llm.register_function("end_call", make_end_call_handler(coordinator))

    started_at_iso = datetime.now(timezone.utc).isoformat()
    perf_pipeline = time.perf_counter()
    transcript_buffer.register(user_aggregator, assistant_aggregator)
    cancel_goodbye_pending = register_goodbye_hangup_fallback(
        user_aggregator,
        assistant_aggregator,
        coordinator,
        markers=tuple(sts.GOODBYE_HANGUP_MARKERS),
        enabled=parse_goodbye_hangup_enabled(),
        delay_s=parse_goodbye_hangup_delay_s(),
    )
    session_call_id = body.get("_session_call_id")
    attach_pipeline_finalize(
        task,
        transcript_buffer,
        context,
        route=os.getenv("BOT_ROUTE", "sts"),
        session_call_id=session_call_id,
        plivo_call_id=plivo_call_id,
        started_at_iso=started_at_iso,
        perf_start=perf_pipeline,
        strip_bootstrap=True,
        usage_accumulator=usage_accumulator,
        extraction_schema=sts.EXTRACTION_SCHEMA,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        _lap(
            t0,
            f"on_client_connected fired — queueing LLMRunFrame for {ctx.lead_name}",
        )
        await task.queue_frames([LLMRunFrame()])
        _lap(t0, "LLMRunFrame queued — Gemini will greet as soon as WS is ready")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        _lap(t0, "on_client_disconnected fired — cancelling task")
        cancel_goodbye_pending()
        wt = call_limits.watchdog_task
        if wt is not None and not wt.done():
            wt.cancel()
            try:
                await wt
            except asyncio.CancelledError:
                pass
        await task.cancel()

    _lap(t0, "Starting PipelineRunner — handing control to pipecat")
    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)
    _lap(t0, "PipelineRunner finished")


async def bot(runner_args: RunnerArguments):
    """Entry point — matches the interface expected by server.py"""
    t0 = time.perf_counter()
    _lap(t0, "bot() called — WebSocket accepted by server.py")

    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    _lap(
        t0,
        f"parse_telephony_websocket done — transport={transport_type}  call_id={call_data.get('call_id', 'unknown')}",
    )

    serializer = PlivoFrameSerializer(
        stream_id=call_data["stream_id"],
        call_id=call_data["call_id"],
        auth_id=os.getenv("PLIVO_AUTH_ID", ""),
        auth_token=os.getenv("PLIVO_AUTH_TOKEN", ""),
    )
    _lap(t0, "PlivoFrameSerializer created")

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )
    _lap(t0, "FastAPIWebsocketTransport created — calling run_bot()")

    await run_bot(transport, runner_args, t0, plivo_call_id=call_data["call_id"])


def _lap(t0: float, label: str) -> None:
    elapsed = time.perf_counter() - t0
    logger.info(f"[⏱ {elapsed:6.3f}s] {label}")

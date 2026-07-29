#
# bot_sts.py — Aakashvani | Gemini Live (STS) pipeline
#
# Persona text and Gemini tuning live under sts_scripts/ (see STS_SCRIPT env).
# Lead qualification is post-call (Groq in call_transcript.py).
#

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from google.genai.types import HttpOptions
from loguru import logger

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import LLMRunFrame, TranscriptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
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
    BotSpeechEndGate,
    SilenceActivityTap,
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
from script_runtime import resolve_sts_runtime, schedule_post_call_snapshot_write

load_dotenv(override=True)


def _context_window_compression_settings() -> dict[str, int | bool] | None:
    """Gemini Live sliding-window compression (Pipecat → Google API).

    Pipecat's ``_connect`` reads this as a dict (``.get("enabled")``), not a Pydantic model.
    Retained token target defaults to trigger_tokens / 2 on the API side.
    Default trigger 32000 → ~16k retained.
    """
    raw = (os.getenv("GEMINI_CONTEXT_COMPRESSION") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return None
    try:
        trigger = int(os.getenv("GEMINI_CWC_TRIGGER_TOKENS", "32000"))
    except ValueError:
        trigger = 32000
    if trigger < 1:
        trigger = 32000
    return {"enabled": True, "trigger_tokens": trigger}


class StsTranscriptionCatcher(FrameProcessor):
    """Captures upstream TranscriptionFrames from GeminiLive into the transcript buffer.

    GeminiLiveLLMService does not emit UserStoppedSpeakingFrame, so the standard
    user_aggregator on_user_turn_stopped event never fires on the STS route.
    This processor intercepts each upstream TranscriptionFrame and appends the
    user turn directly to the transcript buffer.
    """

    def __init__(self, transcript_buffer) -> None:
        super().__init__()
        self._tb = transcript_buffer

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, TranscriptionFrame)
            and direction == FrameDirection.UPSTREAM
            and (getattr(frame, "text", None) or "").strip()
        ):
            ts = datetime.now(timezone.utc).isoformat()
            self._tb.turns.append({"role": "user", "content": frame.text.strip(), "timestamp": ts})
            self._tb._schedule_pg_flush()
        await self.push_frame(frame, direction)


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
    runtime = resolve_sts_runtime(body)
    pg = body.get("_pg") or {}
    session_call_id = body.get("_session_call_id")
    schedule_post_call_snapshot_write(session_call_id, runtime, pg)

    end_tools = ToolsSchema(standard_tools=[end_call_function_schema()])
    _affective = runtime.gemini_enable_affective_dialog
    if _affective and "gemini-3" in (runtime.gemini_model or ""):
        logger.warning(
            "GEMINI_ENABLE_AFFECTIVE_DIALOG ignored: {} does not support affective dialog "
            "(use a Gemini 2.5 Live model, e.g. "
            "models/gemini-2.5-flash-native-audio-preview-12-2025)",
            runtime.gemini_model,
        )
        _affective = False
    elif _affective:
        logger.info("Gemini affective dialog enabled (api_version=v1alpha)")

    cwc = _context_window_compression_settings()
    llm_settings_kw: dict = {
        "model": runtime.gemini_model,
        "voice": runtime.gemini_voice,
        "language": runtime.gemini_language,
        "vad": runtime.gemini_vad,
        "temperature": runtime.gemini_temperature,
    }
    if cwc is not None:
        llm_settings_kw["context_window_compression"] = cwc
        logger.info(
            "Gemini context window compression enabled trigger_tokens={}",
            cwc.get("trigger_tokens"),
        )
    if _affective:
        llm_settings_kw["enable_affective_dialog"] = True

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        http_options=HttpOptions(api_version="v1alpha") if _affective else None,
        system_instruction=runtime.system_instruction,
        tools=end_tools,
        settings=GeminiLiveLLMService.Settings(**llm_settings_kw),
    )
    _lap(t0, "GeminiLiveLLMService object created (not yet connected)")

    @llm.event_handler("on_error")
    async def on_llm_error(service, error):
        logger.error("[gemini] Service error (may cause voice cut): {}", error)

    @llm.event_handler("on_completion_timeout")
    async def on_llm_completion_timeout(service):
        logger.error("[gemini] Completion timeout — active call may experience voice cut")

    transcript_buffer = TranscriptBuffer(session_call_id=session_call_id)
    sts_catcher = StsTranscriptionCatcher(transcript_buffer)
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)

    context = LLMContext(runtime.bootstrap_messages, tools=end_tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
    )

    silence_tap = SilenceActivityTap()
    end_gate = BotSpeechEndGate()

    pipeline = Pipeline([
        transport.input(),
        user_aggregator,
        silence_tap,
        sts_catcher,
        llm,
        transport.output(),
        end_gate,
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

    max_minutes = parse_max_call_minutes(pg.get("max_call_minutes"))
    call_limits = schedule_max_call_duration(
        task,
        max_minutes,
        "max_call_duration",
        hangup_delay_s=parse_goodbye_hangup_delay_s(),
    )
    coordinator = call_limits.coordinator
    end_gate.bind(coordinator)
    silence_tap.bind(coordinator)
    llm.register_function("end_call", make_end_call_handler(coordinator))

    started_at_iso = datetime.now(timezone.utc).isoformat()
    perf_pipeline = time.perf_counter()
    transcript_buffer.register(user_aggregator, assistant_aggregator)
    cancel_goodbye_pending = register_goodbye_hangup_fallback(
        user_aggregator,
        assistant_aggregator,
        coordinator,
        markers=runtime.goodbye_markers,
        enabled=parse_goodbye_hangup_enabled(),
        delay_s=parse_goodbye_hangup_delay_s(),
    )
    extraction_schema = pg.get("extraction_schema_override") or runtime.extraction_schema

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
        extraction_schema=extraction_schema,
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

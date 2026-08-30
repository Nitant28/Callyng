#
# bot_cascade.py — Aakashvani | Sarvam STT + Groq + Cartesia pipeline
#
# System prompt lives under cascade_scripts/ (see CASCADE_SCRIPT env).
#

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
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
from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from call_limits import (
    BotSpeechEndGate,
    SilenceActivityTap,
    end_call_function_schema,
    make_end_call_handler,
    parse_goodbye_hangup_delay_s,
    parse_max_call_minutes,
    schedule_max_call_duration,
)
from call_metrics import UsageMetricsAccumulator, UsageMetricsTap
from call_transcript import TranscriptBuffer, attach_pipeline_finalize
from lead_context import LeadContext
from providers.factory import (
    TELEPHONY_SAMPLE_RATE,
    create_llm_service,
    create_stt_service,
    create_tts_service,
)
from call_transfer import store_transfer_destination
from db import postgres as pg_db
from script_runtime import (
    CascadeRuntime,
    build_live_tool_schemas,
    resolve_cascade_runtime,
    schedule_post_call_snapshot_write,
)
from telephony import build_transfer_xml_url, stop_plivo_stream, transfer_plivo_call

load_dotenv(override=True)

# Short Hindi/Marathi replies (haan, ji, nahi) are ~150–200ms. Silero's
# default start_secs=0.2 misses them, so VAD never starts a turn, Sarvam
# never flushes, and Pipecat's default Smart Turn stop never ends the turn —
# the bot talks over the callee and never consumes their reply.
# stop_secs stays at 0.2 (Pipecat's STT-latency assumption).
CASCADE_VAD_PARAMS = VADParams(
    confidence=0.5,
    start_secs=0.1,
    stop_secs=0.2,
    min_volume=0.4,
)
CASCADE_SPEECH_TIMEOUT_S = 0.6


# Empty LLMContext + LLMRunFrame yields a 0-length assistant turn (no TTS).
# Mute-until-first-bot then deadlocks: user stays muted, greeting never starts.
def cascade_kickoff_messages(lead_name: str) -> list[dict[str, str]]:
    name = (lead_name or "Sir").strip() or "Sir"
    return [
        {
            "role": "user",
            "content": (
                f"The call has just connected. {name} has answered. "
                f"Execute Step 1 from your call flow: say ONLY the Step 1 "
                f"opening sentence in Hindi, addressing {name} warmly — "
                f"then stop and wait. Do not say anything else."
            ),
        }
    ]


def cascade_user_turn_strategies() -> UserTurnStrategies:
    """VAD barge-in + silence timeout. Do not use Smart Turn on 8 kHz PSTN."""
    return UserTurnStrategies(
        start=[
            VADUserTurnStartStrategy(),
            TranscriptionUserTurnStartStrategy(),
        ],
        stop=[
            SpeechTimeoutUserTurnStopStrategy(
                user_speech_timeout=CASCADE_SPEECH_TIMEOUT_S,
            ),
        ],
    )


def cascade_user_aggregator_params() -> LLMUserAggregatorParams:
    return LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(
            sample_rate=TELEPHONY_SAMPLE_RATE,
            params=CASCADE_VAD_PARAMS,
        ),
        user_turn_strategies=cascade_user_turn_strategies(),
        # Kickoff makes the greeting speak; mute then drops line-noise
        # VAD until that first BotStoppedSpeaking (empty 5s turn at t+2s).
        user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
    )


def _optional_pool():
    try:
        from db import postgres as pg_db

        return pg_db.get_pool()
    except Exception:
        return None


def transfer_call_schema() -> FunctionSchema:
    return FunctionSchema(
        name="transfer_call",
        description=(
            "Cold-transfer the caller to a human. Use this when the caller asks "
            "for a person. Do not pass a destination; the number is configured."
        ),
        properties={
            "reason": {
                "type": "string",
                "description": "Optional reason for the transfer",
            }
        },
        required=[],
    )


def cascade_tool_schemas(runtime: CascadeRuntime) -> list[FunctionSchema]:
    """end_call always; live tools and transfer_call only when toggled on."""
    tools: list[FunctionSchema] = [end_call_function_schema()]
    if runtime.live_tools_enabled:
        tools.extend(build_live_tool_schemas(runtime.live_tools))
    if runtime.transfer_enabled and runtime.transfer_number:
        tools.append(transfer_call_schema())
    return tools


def _default_push_lead_data_schema() -> FunctionSchema:
    return FunctionSchema(
        name="push_lead_data",
        description=(
            "Call this before ending every call to save lead qualification data. "
            "Always call this regardless of outcome."
        ),
        properties={
            "intent_status": {
                "type": "string",
                "description": "Whether lead is interested: Yes, No, Busy, Callback, Unclear",
            },
            "bhk_preference": {
                "type": "string",
                "description": "BHK preference: 2BHK, 3BHK, or the string NULL if not collected",
            },
            "location_preference": {
                "type": "string",
                "description": "Preferred location in Pune, or the string NULL if not collected",
            },
            "callback_time": {
                "type": "string",
                "nullable": True,
                "description": "Requested callback time if busy; omit or null if none",
            },
            "language_used": {
                "type": "string",
                "description": "Language used in call: Hindi, Marathi, English",
            },
        },
        required=["intent_status", "bhk_preference", "location_preference"],
    )


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
    plivo_call_id: str,
    *,
    stream_id: str | None = None,
    serializer: PlivoFrameSerializer | None = None,
):
    body = getattr(runner_args, "body", {}) or {}
    ctx = LeadContext.from_body(body, default_lead_name="Sir")
    runtime = resolve_cascade_runtime(body)
    pg = body.get("_pg") or {}
    session_call_id = body.get("_session_call_id")
    schedule_post_call_snapshot_write(session_call_id, runtime, pg)

    bootstrap_from_prefetch = list(runtime.bootstrap_messages or [])
    kickoff = cascade_kickoff_messages(ctx.lead_name)
    context_messages = bootstrap_from_prefetch if bootstrap_from_prefetch else kickoff

    logger.info(
        "Starting cascaded bot — script {} | stt={}/{} llm={}/{} tts={}/{}",
        runtime.script_id,
        runtime.stt_provider,
        runtime.stt_model,
        runtime.llm_provider,
        runtime.llm_model,
        runtime.tts_provider,
        runtime.tts_model,
    )

    tool_schemas = cascade_tool_schemas(runtime)
    tools = ToolsSchema(standard_tools=tool_schemas)
    tool_names = {schema.name for schema in tool_schemas}

    client_id = pg.get("client_id")
    pool = _optional_pool()
    try:
        stt = await create_stt_service(
            runtime.stt_provider,
            runtime.stt_model,
            runtime.stt_settings,
            client_id=client_id,
            pool=pool,
        )
        llm = await create_llm_service(
            runtime.llm_provider,
            runtime.llm_model,
            runtime.llm_settings,
            system_prompt=runtime.system_prompt,
            client_id=client_id,
            pool=pool,
        )
        tts = await create_tts_service(
            runtime.tts_provider,
            runtime.tts_model,
            runtime.tts_settings,
            voice=runtime.tts_voice,
            client_id=client_id,
            pool=pool,
        )
    except ValueError as exc:
        logger.error(
            "Cascade service construction failed for script {}: {}",
            runtime.script_id,
            exc,
        )
        raise

    context = LLMContext(
        messages=context_messages,
        tools=tools,
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=cascade_user_aggregator_params(),
    )

    transcript_buffer = TranscriptBuffer(session_call_id=session_call_id)
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)
    transcript_buffer.register(user_aggregator, assistant_aggregator)

    silence_tap = SilenceActivityTap()
    end_gate = BotSpeechEndGate()
    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        silence_tap,
        llm,
        tts,
        transport.output(),
        end_gate,
        usage_tap,
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=TELEPHONY_SAMPLE_RATE,
            audio_out_sample_rate=TELEPHONY_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

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

    async def handle_push_lead_data(params: FunctionCallParams):
        data = params.arguments
        logger.info(f"LEAD DATA CAPTURED: {json.dumps(data, ensure_ascii=False, indent=2)}")
        logger.info(
            "Phone: {} | Name: {} | City: {}",
            ctx.lead_phone,
            ctx.lead_name,
            ctx.lead_city,
        )
        await params.result_callback(
            {
                "status": "saved",
                "next": (
                    "Speak a short goodbye in the current language, "
                    "then call end_call. Do not restart the greeting."
                ),
            }
        )

    transfer_state: dict[str, bool] = {"transferred": False}

    def _make_generic_live_tool_handler(tool_name: str):
        async def _handle(params: FunctionCallParams):
            logger.info(
                "live tool {} args={}",
                tool_name,
                json.dumps(params.arguments or {}, ensure_ascii=False),
            )
            await params.result_callback({"status": "ok"})

        return _handle

    async def handle_transfer_call(params: FunctionCallParams):
        number = runtime.transfer_number
        reason = (params.arguments or {}).get("reason")
        logger.info(
            "transfer_call session={} to={} reason={}",
            session_call_id,
            number,
            reason,
        )
        transfer_state["transferred"] = True
        if session_call_id:
            await store_transfer_destination(session_call_id, number)
            pool = _optional_pool()
            if pool is not None:
                try:
                    await pg_db.mark_call_transferred(pool, session_call_id)
                except Exception as exc:
                    logger.warning("mark_call_transferred failed: {}", exc)
        if not plivo_call_id or not number:
            await params.result_callback(
                {"status": "error", "detail": "missing call uuid or transfer number"}
            )
            return
        aleg_url = build_transfer_xml_url(session_call_id or "")
        try:
            async with aiohttp.ClientSession() as http:
                await transfer_plivo_call(
                    http, plivo_call_id, number, aleg_url=aleg_url
                )
                # Stream XML stays active until the WS is torn down; Transfer
                # then never fetches Dial XML. Stop the stream (do not hang up).
                if serializer is not None:
                    serializer._params.auto_hang_up = False
                    serializer._hangup_attempted = True
                if stream_id:
                    await stop_plivo_stream(http, plivo_call_id, stream_id)
        except Exception as exc:
            logger.exception("Plivo transfer failed: {}", exc)
            await params.result_callback({"status": "error", "detail": str(exc)})
            return
        await params.result_callback({"status": "transferring"})

    llm.register_function("end_call", make_end_call_handler(coordinator))
    if "push_lead_data" in tool_names:
        llm.register_function("push_lead_data", handle_push_lead_data)
    if "transfer_call" in tool_names:
        llm.register_function("transfer_call", handle_transfer_call)
    for schema in tool_schemas:
        if schema.name in {"end_call", "push_lead_data", "transfer_call"}:
            continue
        llm.register_function(schema.name, _make_generic_live_tool_handler(schema.name))

    started_at_iso = datetime.now(timezone.utc).isoformat()
    perf_pipeline = time.perf_counter()
    extraction_schema = pg.get("extraction_schema_override") or runtime.extraction_schema

    attach_pipeline_finalize(
        task,
        transcript_buffer,
        context,
        route="cascaded",
        session_call_id=session_call_id,
        plivo_call_id=plivo_call_id,
        started_at_iso=started_at_iso,
        perf_start=perf_pipeline,
        strip_bootstrap=False,
        usage_accumulator=usage_accumulator,
        extraction_schema=extraction_schema,
        providers={
            "stt": runtime.stt_provider,
            "llm": runtime.llm_provider,
            "tts": runtime.tts_provider,
        },
        transfer_state=transfer_state,
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info(
            "Call connected — script {} (stt={}/{} llm={}/{} tts={}/{})",
            runtime.script_id,
            runtime.stt_provider,
            runtime.stt_model,
            runtime.llm_provider,
            runtime.llm_model,
            runtime.tts_provider,
            runtime.tts_model,
        )
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

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await run_bot(
        transport,
        runner_args,
        call_data["call_id"],
        stream_id=call_data.get("stream_id"),
        serializer=serializer,
    )

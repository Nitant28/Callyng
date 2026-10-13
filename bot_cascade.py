#
# bot_cascade.py — Aakashvani | STT + LLM + TTS pipeline with Telnyx Telephony
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
from pipecat.serializers.telnyx import TelnyxFrameSerializer
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
from telephony import build_transfer_xml_url, stop_telnyx_stream, transfer_telnyx_call

load_dotenv(override=True)

CASCADE_VAD_PARAMS = VADParams(
    confidence=0.5,
    start_secs=0.1,
    stop_secs=0.2,
    min_volume=0.4,
)
CASCADE_SPEECH_TIMEOUT_S = 0.6


def cascade_user_turn_strategies() -> UserTurnStrategies:
    return UserTurnStrategies(
        start=[
            VADUserTurnStartStrategy(),
            TranscriptionUserTurnStartStrategy(),
        ],
        stop=[
            SpeechTimeoutUserTurnStopStrategy(
                timeout_s=CASCADE_SPEECH_TIMEOUT_S
            ),
        ],
    )


def cascade_user_aggregator_params() -> LLMUserAggregatorParams:
    return LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(params=CASCADE_VAD_PARAMS),
        user_turn_strategies=cascade_user_turn_strategies(),
        user_mute_strategies={MuteUntilFirstBotCompleteUserMuteStrategy()},
    )


def cascade_kickoff_messages(lead_name: str) -> list[dict[str, str]]:
    name = (lead_name or "Sir").strip() or "Sir"
    return [
        {
            "role": "user",
            "content": (
                f"Greet the callee ({name}) in one short sentence as instructed in your prompt."
            ),
        }
    ]


def _optional_pool():
    try:
        from db import postgres as pg

        return getattr(pg, "_pool", None)
    except Exception:
        return None


def _make_generic_live_tool_handler(tool_name: str):
    async def _handler(params: FunctionCallParams):
        args = params.arguments if isinstance(params.arguments, dict) else {}
        logger.info(
            "Cascade generic tool {} called with args {}",
            tool_name,
            list(args.keys()),
        )
        await params.result_callback({"status": "acknowledged", "tool": tool_name})

    return _handler


def cascade_tool_schemas(runtime: CascadeRuntime) -> list[FunctionSchema]:
    declared = [end_call_function_schema()]
    if runtime.transfer_enabled:
        declared.append(
            FunctionSchema(
                name="transfer_call",
                description=(
                    "Cold transfer the caller to a human agent when the caller "
                    "explicitly asks to talk to a person or asks a question only "
                    "a human can answer."
                ),
                properties={
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for the transfer (e.g. caller requested human).",
                    },
                },
                required=[],
            )
        )
    declared.extend(build_live_tool_schemas(runtime))
    return declared


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
    telephony_call_id: str,
    *,
    stream_id: str | None = None,
    serializer: TelnyxFrameSerializer | None = None,
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

    bot_speech_gate = BotSpeechEndGate()
    silence_tap = SilenceActivityTap()
    transcript_buffer = TranscriptBuffer()
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            silence_tap,
            user_aggregator,
            llm,
            tts,
            bot_speech_gate,
            usage_tap,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=TELEPHONY_SAMPLE_RATE,
            audio_out_sample_rate=TELEPHONY_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    max_mins = parse_max_call_minutes()
    schedule_max_call_duration(
        task,
        max_mins,
        session_call_id=session_call_id,
        lead_name=ctx.lead_name,
    )

    call_limits = silence_tap.start_watchdog(
        task,
        session_call_id=session_call_id,
        delay_s=parse_goodbye_hangup_delay_s(),
    )

    coordinator = _Coordinator(task, bot_speech_gate)
    transfer_state: dict[str, Any] = {"transferred": False}

    async def handle_push_lead_data(params: FunctionCallParams):
        args = params.arguments or {}
        logger.info("push_lead_data invoked args: {}", args)
        lead_id = pg.get("lead_id")
        pool = _optional_pool()
        if lead_id and pool is not None:
            try:
                from uuid import UUID

                import db.postgres as pg_db

                await pg_db.update_lead_fields(
                    pool,
                    UUID(str(lead_id)),
                    args.get("intent_status"),
                    args.get("bhk_preference"),
                    args.get("location_preference"),
                    budget_min=args.get("budget_min"),
                    budget_max=args.get("budget_max"),
                    language=args.get("language"),
                )
            except Exception as exc:
                logger.warning("push_lead_data db update failed: {}", exc)
        await params.result_callback({"status": "success", "message": "Lead data saved."})

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
        if not telephony_call_id or not number:
            await params.result_callback(
                {"status": "error", "detail": "missing call id or transfer number"}
            )
            return
        aleg_url = build_transfer_xml_url(session_call_id or "")
        try:
            async with aiohttp.ClientSession() as http:
                await transfer_telnyx_call(
                    http, telephony_call_id, number, aleg_url=aleg_url
                )
                if serializer is not None:
                    serializer._params.auto_hang_up = False
                    serializer._hangup_attempted = True
                if stream_id:
                    await stop_telnyx_stream(http, telephony_call_id, stream_id)
        except Exception as exc:
            logger.exception("Telnyx transfer failed: {}", exc)
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
        plivo_call_id=telephony_call_id,
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
        await asyncio.sleep(0.5)
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


class _Coordinator:
    def __init__(self, task: PipelineTask, gate: BotSpeechEndGate) -> None:
        self.task = task
        self.bot_speech_end_gate = gate


async def bot(runner_args: RunnerArguments):
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(
        "Transport: %s | Call: %s",
        transport_type,
        call_data.get("call_id", "unknown"),
    )

    from telephony import create_telnyx_serializer

    serializer = create_telnyx_serializer(call_data)

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

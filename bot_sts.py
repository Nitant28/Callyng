#
# bot_sts.py — Gemini Live STS bot for Plivo telephony
# Drop-in replacement for bot_cascade.py
# All tunable STS options are documented inline
#

import os
import time

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.google.gemini_live.llm import (
    GeminiLiveLLMService,
    GeminiVADParams,
)
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

load_dotenv(override=True)

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Diya, a premium relationship manager for Pyramid Constructions.
You are calling about "Pyramid Parkland Nxt" — a 2 BHK project in Bhukum, Pune.

RULES:
- Speak ONLY in Marathi
- Keep every response to 1-2 sentences maximum
- Use respectful "Aapan" / "Tumhi" — never "Tu"
- Never make up any project details
- If asked something you don't know: "Me exact details check karun 5 minitat call karte"
- Pronounce: Bhukum = "Bhoo-koom", Hinjawadi = "Hin-ja-wa-dee"

GREETING (two steps — do not combine):
Step 1: Say ONLY "Namaskar, {lead_name} anshi boltiye ka?" and wait.
Step 2: After they respond, say "Me Diya, Bhukum madhil Pyramid Parkland Nxt madhun boltiye. 2 BHK sathi inquiry keli hoti — bolayla vel aahe ka?"

PROJECT FACTS:
- Location: Bhukum, Paud Road, near Bharat Petrol Pump, Manas Lake view
- Size: 768 to 816 sq ft
- Floors: 12
- RERA possession: December 2030 | Our commitment: Late 2027
- Price: Ask customer for site visit — do not quote price over phone
- Hinjawadi IT Park: 20 mins | Chandani Chowk: 15 mins | Pirangut: 5 mins
- Amenities: Gym, kids play area, amphitheatre, walking track, indoor games

NOT INTERESTED: "Kahi harakat nahi, tumchya velesathi dhanyawad."
BROCHURE REQUEST: "Me brochure WhatsApp var pathavte."
"""


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, t0: float):
    _lap(t0, "run_bot() entered — building pipeline")

    body = getattr(runner_args, "body", {})
    lead_name = body.get("lead_name", "Sir / Madam")
    prompt = SYSTEM_PROMPT.replace("{lead_name}", lead_name)

    # ── Gemini Live (STT + LLM + TTS in one) ──────────────────────────────────
    # Pattern below mirrors the official pipecat Gemini Live examples
    # (pipecat-ai/pipecat-examples/gemini-live-starters): we pre-seed the
    # LLMContext with a user-role bootstrap message and leave
    # inference_on_context_initialization at its default (True). Combined with
    # `queue_frames([LLMRunFrame()])` in on_client_connected, this lets pipecat
    # fire the first generation the *instant* the Gemini WS handshake finishes,
    # overlapping the handshake with all other startup work instead of
    # serializing poll → sleep → seed.
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),

        # system_instruction: sets the bot's persona/rules at the session level.
        # Takes precedence over any system message added via LLMContext.
        system_instruction=prompt,

        settings=GeminiLiveLLMService.Settings(

            # ── Model ──────────────────────────────────────────────────────────
            # Always include the "models/" prefix — required for Gemini Live API.
            # models/gemini-3.1-flash-live-preview  → latest, lowest latency
            #                                          no proactivity/affective dialog
            # models/gemini-2.5-flash-native-audio-preview-12-17 → previous gen,
            #                                          supports proactivity + affective
            model="models/gemini-3.1-flash-live-preview",

            # ── Voice ──────────────────────────────────────────────────────────
            # Options (as of 2025): Aoede, Charon, Fenrir, Kore, Puck,
            #                       Erinome, Leda, Orus, Zephyr
            # Aoede / Kore / Erinome → warmer, female-leaning
            # Charon / Puck          → neutral
            # Fenrir / Orus          → deeper, male-leaning
            voice="Aoede",

            # ── Language ───────────────────────────────────────────────────────
            # Set explicitly for non-English to improve VAD + transcription accuracy.
            # Examples: "hi-IN" (Hindi), "mr-IN" (Marathi), "en-IN" (Indian English)
            # Leave commented to let Gemini auto-detect from audio.
            # language="mr-IN",

            # ── VAD (Voice Activity Detection) ────────────────────────────────
            # Gemini Live uses server-side VAD by default.
            # For telephony (8 kHz mulaw), server VAD works well without Silero.
            vad=GeminiVADParams(
                # silence_duration_ms: how long silence (ms) before end-of-turn.
                # Default ~700 ms. Increase if callers get cut off mid-sentence.
                silence_duration_ms=800,

                # prefix_padding_ms: audio before speech onset to include.
                # Helps catch the first syllable. Default ~200 ms.
                prefix_padding_ms=200,

                # disabled=True → turns off server VAD entirely.
                # Use only if you plug in a local SileroVADAnalyzer via
                # LLMUserAggregatorParams instead.
                # disabled=False,
            ),

            # ── Sampling / generation ─────────────────────────────────────────
            # temperature=0.8,   # 0.0–2.0; lower = more deterministic responses
            # max_tokens=256,    # cap response length (in output tokens)
            # top_p=0.95,        # nucleus sampling probability mass
            # top_k=40,          # top-k sampling cutoff

            # ── Thinking / reasoning (gemini-3.1 only) ────────────────────────
            # Adds a reasoning pass before responding. Increases latency noticeably.
            # Levels: "minimal", "low", "medium", "high"
            # from google.genai.types import ThinkingConfig
            # thinking=ThinkingConfig(thinking_level="minimal"),

            # ── Context window compression ────────────────────────────────────
            # Prevents hitting token limits on long calls by summarising older turns.
            # context_window_compression={"enabled": True},

            # ── Affective dialog (gemini-2.5 only — NOT gemini-3.1) ───────────
            # Adapts tone/prosody to match the caller's detected emotional state.
            # enable_affective_dialog=True,

            # ── Proactivity (gemini-2.5 only — NOT gemini-3.1) ────────────────
            # Lets the model speak unprompted — e.g. fill silence, ask follow-ups.
            # from google.genai.types import ProactivityConfig
            # proactivity=ProactivityConfig(enabled=True),
        ),
    )
    _lap(t0, "GeminiLiveLLMService object created (not yet connected)")

    # ── Context ────────────────────────────────────────────────────────────────
    # Pre-seed the context with a user-role bootstrap turn. pipecat's
    # GeminiLiveLLMService picks this up on the first LLMContextFrame and, if
    # the Gemini WS isn't ready yet, defers via `_run_llm_when_session_ready`
    # so generation kicks off the *moment* the handshake completes — i.e. zero
    # additional wall-clock cost beyond the unavoidable WS connect.
    bootstrap_messages = [
        {
            "role": "user",
            "content": (
                "The call has just connected. Begin with Step 1 of your "
                f"greeting: say only 'Namaskar, {lead_name} anshi boltiye ka?' "
                "and then stop and wait for the caller's response."
            ),
        }
    ]
    context = LLMContext(bootstrap_messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    # ── Pipeline: transport.input → aggregator → Gemini Live → transport.output ─
    pipeline = Pipeline([
        transport.input(),
        user_aggregator,       # ← required: buffers/routes audio to Gemini
        llm,
        transport.output(),
        assistant_aggregator,  # ← required: captures assistant turns
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

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Official pipecat pattern: just queue LLMRunFrame and let the
        # service's `_run_llm_when_session_ready` mechanism handle the race
        # between Gemini WS handshake completion and context arrival. No
        # polling, no artificial sleep, no late add_message.
        _lap(t0, "on_client_connected fired — queueing LLMRunFrame")
        await task.queue_frames([LLMRunFrame()])
        _lap(t0, "LLMRunFrame queued — Gemini will greet as soon as WS is ready")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        _lap(t0, "on_client_disconnected fired — cancelling task")
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
    _lap(t0, f"parse_telephony_websocket done — transport={transport_type}  call_id={call_data.get('call_id', 'unknown')}")

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

    await run_bot(transport, runner_args, t0)


def _lap(t0: float, label: str) -> None:
    """Log a labelled timestamp relative to t0."""
    elapsed = time.perf_counter() - t0
    logger.info(f"[⏱ {elapsed:6.3f}s] {label}")
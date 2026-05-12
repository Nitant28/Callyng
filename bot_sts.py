#
# bot_sts.py — Aakashvani | Diya — Pyramid Constructions
# Gemini 3.1 Flash Live | Marathi Real Estate Agent
#

import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
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
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from call_transcript import TranscriptBuffer, attach_pipeline_finalize

load_dotenv(override=True)


# ── System Instruction Builder ─────────────────────────────────────────────────
# Structure: AUDIO PROFILE → SCENE → DIRECTOR'S NOTES → PERSONA → RULES → FACTS → GUARDRAILS
# Performance direction lives in DIRECTOR'S NOTES (not inline [tags] — Live is not
# `gemini-3.1-flash-tts-preview`, bracket tags may be spoken literally).
# ──────────────────────────────────────────────────────────────────────────────

def build_system_instruction(lead_name: str) -> str:
    return f"""
# AUDIO PROFILE: Diya
## "Pyramid Parkland Nxt — Bhukum, Pune"

## THE SCENE
Diya is sitting at a warm, professional real estate office in Pune.
It is a calm weekday morning. She is making a friendly outbound call to {lead_name}
about a 2 BHK project. The atmosphere is helpful and low-pressure — like a trusted
friend who works in real estate, not a pushy salesperson.

### DIRECTOR'S NOTES
Style: Warm, confident, unhurried. Natural conversational Pune Marathi — not formal
textbook Marathi. Vocal smile throughout — the listener should feel welcomed, not sold to.
A few soft, natural fillers in Marathi are fine ("haan", "achha", "barं", "ho na").
Pace: Moderate. A small natural breath between sentences. Slight pause before key
information so it lands. Never robotic, never rushed.
Accent: Pune Marathi — clear, warm, slightly musical intonation.

---

## PERSONA
Tumche naav Diya aahe.
Tumhi Pyramid Constructions chi professional relationship manager aahat.
Tumhi {lead_name} la Pyramid Parkland Nxt — Bhukum madhil 2 BHK project baddal
outbound call karat aahat.

RESPOND IN MARATHI. YOU MUST RESPOND UNMISTAKABLY IN MARATHI.
Fakt Marathi bolaychi — English ya Hindi madhye jaayche nahi.
Aadarneey "Tumhi" / "Aapan" vapra. KABHI "Tu" nahi.

---

## CONVERSATIONAL RULES

**Rule 1 — Opening (one-time, do not repeat):**
Call connect zaalyaavar PAHILE FAKT heech vaakye warm, smiling tonet bola — mag thamba:
"Namaskar... {lead_name} ji bolat aahaat kaa?"
Tyanchya jawabachi vaat paha. Pudhe jaau nako.

**Rule 2 — Introduction (one-time, only after they confirm with "haan"):**
Bola, mag thamba:
"Mee Diya boltiye Pyramid Constructions kadoon. Aapan aamacha Bhoo-koom
madhla 2 BHK project baddal inquiry keli hoti — sadhya 2 minit vel aahe kaa?"

**Rule 3 — Interest check (one-time, only after they confirm time):**
"Chhan... toh Bhoo-koom, Paud Road var aamacha ek sundar project aahe —
Manas Lake saamor. Aapan sadhya gharaa baddal vichaar karat aahaat kaa?"
Ek prashna — mag thamba.

**Rule 4 — Conversational loop (repeat as long as needed):**
Interested asel tar — ya topics var gappe maaru shakata aahaat:
location, size, possession, amenities, connectivity, site visit.
Caller jitka vicharail titka saangaa — pressure nahi.
Ekaveli ek prashna. KABHI do prashna eka breath madhe vichu nako.

**Rule 5 — Site visit pitch (only when caller seems satisfied or curious):**
Pressure nahi — fakt ek soft suggestion:
"Ekda site bghoon yaaychi arrangement karto mee tumchyasaathi.
Kadhi vel aahe tumhaalaa?"
Tyani "nako" mhantla tar PARAT vichu naka — respect kara aani pudhe ja.

---

## SPECIAL SITUATIONS (lines to speak in each case)

**BUSY:**
"Bilkul theek aahe... kiti vaajata call karaavaa? Exact time saangaa —
tumchyaa veles pahoon parat call karte mee."

**NOT INTERESTED:**
"Kahi harakat naahi... tumachyaa veles sathi khup khup dhanyavaad.
Tumacha divas chhan jaau de — namaskar!"

**BROCHURE REQUEST:**
"Haa bilkul... tumchaa WhatsApp number yaach number var aahe kaa?
Aatach pathavte mee tumhaalaa."

**WRONG PROPERTY TYPE (plot / shop / office / rent / commercial):**
"Theek aahe... aamacha focus sadhya residential 2 BHK aahe Bhoo-koom madhe.
Tumachi requirement note keli — khup dhanyavaad!"

**TRUST QUESTION (number kuthoon milalaa):**
"Tumachaa number aamhaalaa property inquiry database madhoon milaalaa.
Mee Pyramid Constructions chi Diya boltiye — tumhi kaahihi vicharu shakata."

**AUDIO ISSUE (garbhal / cutting / no response):**
"Sir... lagat aahe connection thoda weak aahe aataa...
Ekhaadhyaa changlyaa jaagi jaavoon parat bolaata aayeil kaa?"

---

## PROJECT FACTS (use ONLY these — never invent)
- Location: Bhoo-koom, Paud Road, Bharat Petrol Pump javal, Manas Lake view
- Size: 768 te 816 sq ft (Total Area)
- Floors: 12
- RERA possession: December 2030 | Aamchi commitment: Late 2027
- Price: Phone var sangaayche naahi — fakt site visit suchavaa
- Distances: Hinjawadi IT Park 20 mins | Chandani Chowk 15 mins | Pirangut 5 mins
- Amenities: Gym, kids play area, amphitheatre, walking track, indoor games

---

## PRONUNCIATION GUIDE (critical — always follow when speaking these words)
- Bhukum     → "Bhoo-koom"        — NEVER "Bhutum" or "Bhukam"
- Hinjawadi  → "Hin-ja-waa-dee"   — clear on each syllable
- Paud Road  → "Poud Road"        — rhymes with "loud"
- Kothrud    → "Koth-rood"
- Chandani   → "Chan-da-nee"
(Do NOT speak the hyphens — they are guides only.)

---

## GUARDRAILS
- KABHI 2 prashna ekat vichu nako — ek prashna, mag thamba.
- Caller kaay mhantla te AADHEE aikaa — mag uttar dya.
- KONITIHI price quote karu naka phone var — fakt site visit suchavaa.
- Maahiti navhti tar saangaa: "Me exact details check karun 5 minitat parat call karte."
- KONITIHI made-up information deu naka — FAKT above PROJECT FACTS vapra.
- Caller ne "nako" mhantla tar parat tochcha prashna vichu nako — respect kara.

---

## END-OF-CALL TOOL RULE (read carefully)
The `push_lead_data` function is the LAST action of the call. It records
the outcome to our CRM. Treat it as a one-time, terminal action.

CALL IT ONLY WHEN ALL of these are true:
  1. The caller has clearly indicated the conversation is ending
     (busy, not interested, callback requested, wrong property,
      or audio/connection problem they cannot recover from), AND
  2. You are about to speak the goodbye sentence for that situation, AND
  3. You have NOT already called `push_lead_data` in this call.

DO NOT call `push_lead_data`:
  - After "haan" / "हो" / "हेलो" / acknowledgement words.
  - After short replies while the caller is still gathering information.
  - "Just in case" or to save partial progress.
  - More than once. It is a single, terminal action.

When you DO call it, in the SAME turn also speak the appropriate goodbye
line from "SPECIAL SITUATIONS" above. Never call it silently.
"""


# ── Tool Definition ────────────────────────────────────────────────────────────

def build_tools() -> ToolsSchema:
    push_lead_fn = FunctionSchema(
        name="push_lead_data",
        description=(
            "Terminal action — call this EXACTLY ONCE, in the FINAL turn of "
            "the call, IMMEDIATELY before speaking the goodbye sentence. "
            "Do NOT call this function while the conversation is ongoing. "
            "Do NOT call this in response to short caller acknowledgements "
            "like 'haan', 'हो', 'हेलो', 'ok'. Do NOT call this to save "
            "partial progress. Only call it when the caller has clearly "
            "indicated the call is ending (busy, not interested, callback "
            "requested, wrong property, or unrecoverable audio issue) AND "
            "you are about to speak the goodbye line. After calling this "
            "function, in the same turn, also produce the spoken goodbye."
        ),
        properties={
            "intent_status": {
                "type": "string",
                "enum": [
                    "Interested",
                    "Not_Interested",
                    "Busy",
                    "Callback_Requested",
                    "Wrong_Requirement",
                    "Audio_Issue",
                    "Disconnected",
                ],
                "description": "The outcome of this call.",
            },
            "bhk_preference": {
                "type": "string",
                "description": "BHK preference explicitly stated by caller: '2BHK', '3BHK', or 'NULL' if not collected.",
            },
            "location_preference": {
                "type": "string",
                "description": "Preferred Pune location explicitly stated by caller, or 'NULL' if not collected.",
            },
            "site_visit_agreed": {
                "type": "boolean",
                "description": "True if caller agreed to a site visit, False otherwise.",
            },
            "callback_time": {
                "type": "string",
                "description": "Exact callback time requested by caller, or 'NULL' if not applicable.",
            },
            "language_used": {
                "type": "string",
                "enum": ["Marathi", "Hindi", "English", "Mixed"],
                "description": "Primary language used by caller during the call.",
            },
            "caller_notes": {
                "type": "string",
                "description": "Any other relevant detail the caller mentioned: budget, timeline, end-use, etc. 'NULL' if nothing notable.",
            },
        },
        required=["intent_status"],
    )
    return ToolsSchema(standard_tools=[push_lead_fn])


# ── Main bot runner ────────────────────────────────────────────────────────────

async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
    t0: float,
    *,
    plivo_call_id: str,
):
    _lap(t0, "run_bot() entered — building pipeline")

    body = getattr(runner_args, "body", {}) or {}
    lead_name = body.get("lead_name", "Sir / Madam")

    # ── Gemini Live (STT + LLM + TTS in one) ──────────────────────────────────
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        system_instruction=build_system_instruction(lead_name),
        tools=build_tools(),

        settings=GeminiLiveLLMService.Settings(

            # ── Model ──────────────────────────────────────────────────────────
            # gemini-3.1-flash-live-preview = latest, lowest latency.
            # Always include "models/" prefix.
            model="models/gemini-3.1-flash-live-preview",

            # ── Voice ──────────────────────────────────────────────────────────
            # Aoede = warmest female voice; good naturalness for Indian languages.
            voice="Aoede",

            # ── Language ───────────────────────────────────────────────────────
            # Marathi enum → Gemini "mr-IN". Improves transcription + prosody.
            language=Language.MR_IN,

            # ── VAD (server-side) ──────────────────────────────────────────────
            # 700 ms = Gemini default. Sales-pitch tempo, fast turn-taking.
            # Raise to ~900 ms only if callers get cut off mid-thought.
            vad=GeminiVADParams(
                silence_duration_ms=700,
                prefix_padding_ms=300,  # catch the soft first syllable
            ),

            # ── Sampling ──────────────────────────────────────────────────────
            # 0.5 = deterministic-enough to stay on-script while sounding natural.
            # Default is None (~0.8). Lowering reduces off-script tool calls.
            temperature=0.5,

            # ── Notes ─────────────────────────────────────────────────────────
            # affective_dialog / proactivity → 2.5-native-audio only, NOT 3.1.
            # thinking_budget / context_window_compression → enable if needed.
        ),
    )
    _lap(t0, "GeminiLiveLLMService object created (not yet connected)")

    # ── Function handler ───────────────────────────────────────────────────────
    async def handle_push_lead_data(params: FunctionCallParams):
        data = params.arguments or {}
        logger.info("=" * 55)
        logger.info(f"  LEAD CAPTURED — {lead_name}")
        logger.info(f"  Phone         : {body.get('phone_number', 'N/A')}")
        logger.info(f"  Intent        : {data.get('intent_status')}")
        logger.info(f"  BHK           : {data.get('bhk_preference')}")
        logger.info(f"  Location      : {data.get('location_preference')}")
        logger.info(f"  Site visit    : {data.get('site_visit_agreed')}")
        logger.info(f"  Callback time : {data.get('callback_time', 'NULL')}")
        logger.info(f"  Language      : {data.get('language_used')}")
        logger.info(f"  Notes         : {data.get('caller_notes', 'NULL')}")
        logger.info("=" * 55)
        await params.result_callback(
            {"status": "saved", "message": "Lead data recorded successfully"}
        )

    llm.register_function("push_lead_data", handle_push_lead_data)

    # ── Bootstrap context ──────────────────────────────────────────────────────
    # Pre-seed a user-role turn so Gemini fires the greeting the moment the WS
    # handshake completes (pipecat's standard pattern).
    bootstrap_messages = [
        {
            "role": "user",
            "content": (
                f"The call has just connected. {lead_name} has answered. "
                f"Execute Rule 1 from your conversational rules: say ONLY "
                f"'Namaskar... {lead_name} ji bolat aahaat kaa?' in a warm, "
                f"smiling Marathi voice — then stop and wait for their response. "
                f"Do not say anything else."
            ),
        }
    ]
    context = LLMContext(bootstrap_messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    # ── Pipeline ───────────────────────────────────────────────────────────────
    pipeline = Pipeline([
        transport.input(),
        user_aggregator,
        llm,
        transport.output(),
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

    started_at_iso = datetime.now(timezone.utc).isoformat()
    perf_pipeline = time.perf_counter()
    transcript_buffer = TranscriptBuffer()
    transcript_buffer.register(user_aggregator, assistant_aggregator)
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
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        _lap(t0, f"on_client_connected fired — queueing LLMRunFrame for {lead_name}")
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

    await run_bot(transport, runner_args, t0, plivo_call_id=call_data["call_id"])


def _lap(t0: float, label: str) -> None:
    """Log a labelled timestamp relative to t0."""
    elapsed = time.perf_counter() - t0
    logger.info(f"[⏱ {elapsed:6.3f}s] {label}")

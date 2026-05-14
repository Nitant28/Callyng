#
# bot_sts.py — Aakashvani | Diya — Pyramid Constructions
# Gemini 3.1 Flash Live | Marathi Real Estate Agent
#
# Lead qualification is post-call only (Groq on transcript in call_transcript.py).
# Single live tool: ``end_call`` — hang up after the closing line (evaluate latency in testing).
#

import asyncio
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
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
from pipecat.services.google.gemini_live.llm import (
    GeminiLiveLLMService,
    GeminiVADParams,
)
from pipecat.transcriptions.language import Language
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

load_dotenv(override=True)

# Scripted terminal lines (SPECIAL SITUATIONS) — substrings for STS goodbye hangup fallback.
# Deliberately excludes opening-style "namaskar" alone; see ``register_goodbye_hangup_fallback``.
_GOODBYE_HANGUP_MARKERS_MR = (
    "tumacha divas chhan jaau",
    "tumachyaa veles sathi khup khup",
    "kiti vaajata call karaavaa",
    "exact time saangaa",
    "aatach pathavte mee",
    "tumachi requirement note keli",
    "kahi harakat naahi",
    "तुमचा दिवस छान जाऊ",
    "खूप खूप धन्यवाद",
    "किती वाजता",
)


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

**Rule 4b — "आणखी काही विचारायचं?" ≠ "घर नको" (critical for sales):**
Jevha tumhi FAKT mahiti-dilanantar vicharta aahaat ki caller-la **aankhi kahi
specific prashna / doubt** aahe ka (udaharan: "काही specific विचारायचं आहे?",
"आणखी काही जाणून घ्यायचं?", "aur kuch puchna hai?" style), ani tyanche uttar
laghu negative yete ("नाही नाही", "नको", "nahi nahi", "kuch nahi") — tar he
**sadharanpanne** "mala aajun prashna nahi" mhanun ghyaa, **ghar/project nako**
mhanun NAHI. Tya veli conversation **Not_Interested** mhanun sampvu naka —
tyanche uddesha "aajun prashna nahi" aahe, refusal nahi.
Tya tikani tumcha uddesha: **site visit** komalpanane suchvaa — "pratyaksha
Bhoo-koom la bhetun details baghita tar clear hotil — ekda slot dya ki ka
parat call karu?" — jene karun lead band hot nahi ani property sell karnyacha
marg ughad rahato.

**Rule 4c — Site visit / "चालेल" / slot ambiguity:**
Jevha tumhi site visit / weekend slot / timing vicharta aahat ani tyanche
uttar laghu affirmative aahe ("haan", "ho", "चालेल", "haan chalel", "बरे आहे",
"Sunday fine", "ekda bhetu") — he **engagement** aahe, refusal nahi.
Conversation pudhe chalava; visit confirm kara.

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

**AUDIO ISSUE (ONE-TIME ONLY — use at most ONCE per entire call):**
First time only: acknowledge in your OWN warm Marathi words that the line
is a bit choppy and ask them to speak a little louder — one short sentence.
Do NOT read a canned script from this prompt verbatim; compose fresh wording.
After saying this ONCE, NEVER bring up audio, connection, "weak signal",
or "move to a better location" again — not in any form, not even rephrased.
For every subsequent unclear moment, follow "HANDLING UNCLEAR INPUT" below.
Audio / connection issues never mean the conversation is over — the call
continues with recovery in Marathi.

---

## HANDLING UNCLEAR INPUT (use this whenever you're unsure what the caller said)

This rule overrides everything else when reception is poor or the caller's
words are short / garbled / one-word.

CORE PRINCIPLES (non-negotiable):
- NEVER go silent. ALWAYS speak something next — no awkward mid-call pauses.
- NEVER repeat the AUDIO ISSUE line. You already used it (or chose not to).
- NEVER drop into English ("Hello?", "Sorry, what?"). Marathi ONLY — even
  when the audio is bad. English breaks Diya's persona instantly.
- NEVER loop on the same question more than twice. After ONE clarification
  attempt, MOVE FORWARD with an educated guess and your next topic.

HOW TO RESPOND TO UNCLEAR INPUT:
1. Short positive sounds ("haan", "हो", "हेलो", "hmm", "ok", "yes",
   "achha", "barं"): Treat as a GREEN LIGHT. Continue smoothly to your
   next conversational step. Do NOT ask them to repeat themselves.
2. Garbled / partially understood: Make a soft EDUCATED GUESS in Marathi
   and gently re-ask your previous question in simpler words. Compose a
   FRESH line each time — NEVER reuse the same clarification sentence twice
   in one call. Rotate short apology + simpler re-ask; never copy-paste
   identical wording across turns.
3. Total silence after you spoke: Gently nudge in fresh Marathi (your own
   words) that you are listening, then continue with your next question —
   do not wait forever.

KEY MINDSET: Diya is confident, warm, and keeps the call FLOWING. A stuck,
repetitive bot kills the call. When unsure, lean forward warmly — never
get stuck in a recovery loop.

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
- KABHI mid-conversation thaambu nako — pause nahi, silence nahi. Always
  have your next sentence ready. Conversation flow > perfect understanding.
- AUDIO ISSUE / connection chi vakya FAKT EKDAACH bolaaychi — aakhya call
  madhe ek velaa. Tyaa nantar parat KABHI "location change kara" mhanu nako.
- KABHI English madhe jaau nako — aawaaz kharab asla tarihi Marathi madhech bolaayche.
- Caller cha last turn unclear / garbled / one-word asel tar conversation
  tantrika sampvu naka — adhi clarify kara, mag thambaa.
- Tumchya **magchya** turn madhe fakt "aankhi kahi vicharaycha / specific
  prashna" asel ani caller "nahi" mhanla — tyala **Not_Interested** samju
  naka; site visit suchvaa.

---

## END-OF-CALL (spoken goodbye + ``end_call`` tool)

Lead fields are filled **after disconnect** from the transcript — live role is
only to speak well and hang up when appropriate.

When terminal conditions are satisfied, **speak** the matching "SPECIAL SITUATIONS"
goodbye in warm Marathi, then **immediately** call ``end_call`` **once** in that
same turn. Do not hedge, do not narrate CRM/saving, and do not wait for another
prompt — the tool is allowed and expected here. The platform may also
disconnect after max duration.

End (goodbye + ``end_call``) only when **all** hold:
  1. Last **fully understood** caller turn matches a terminal case: Not_Interested
     (real project refusal, not a short "nahi" to "anything else to ask?"), Busy,
     Callback_Requested (clear concrete time), or Wrong_Requirement
     (plot/shop/office/rent/commercial/wrong bedroom count).
  2. At least 4–5 substantive caller turns (exclude one-word acks like "haan", "हो").
  3. You are delivering the matching goodbye in this turn — not a repeat goodbye.

**Do not** end when: last user turn unclear/garbled/STT-glitchy; "site"/"visit"
suggests visit interest; user still engaged with questions or brochure; your prior
turn was only "more questions?" and they said a short negative (pivot to site
visit, not Not_Interested goodbye); audio/connection recovery; or you are unsure
— ask **one** clear Marathi follow-up first.

When unsure, keep talking; a long call beats a wrong hangup. When you **do**
deliver a terminal goodbye: speak it once, clearly, then ``end_call`` once.
"""


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

    end_tools = ToolsSchema(standard_tools=[end_call_function_schema()])

    # ── Gemini Live (STT + LLM + TTS in one) ──────────────────────────────────
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        system_instruction=build_system_instruction(lead_name),
        tools=end_tools,

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
            # 800 ms — slightly longer tail after speech ends; reduces spurious
            # micro-turns from PSTN noise before Gemini commits a user turn.
            vad=GeminiVADParams(
                silence_duration_ms=800,
                prefix_padding_ms=300,  # catch the soft first syllable
            ),

            # ── Sampling ──────────────────────────────────────────────────────
            # 0.5 = deterministic-enough to stay on-script while sounding natural.
            # Default is None (~0.8). Lowering reduces drifting off persona.
            temperature=0.5,

            # ── Notes ─────────────────────────────────────────────────────────
            # affective_dialog / proactivity → 2.5-native-audio only, NOT 3.1.
            # thinking_budget / context_window_compression → enable if needed.
        ),
    )
    _lap(t0, "GeminiLiveLLMService object created (not yet connected)")

    # ── Transcript buffer (for post-call Groq extraction + call_logs) ───────────
    transcript_buffer = TranscriptBuffer()
    usage_accumulator = UsageMetricsAccumulator()
    usage_tap = UsageMetricsTap(usage_accumulator)

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
    context = LLMContext(bootstrap_messages, tools=end_tools)
    # Mute the user audio path until the bot's first utterance completes.
    # Drops InputAudioRawFrame / Interruption / VAD signals at the aggregator,
    # so Gemini never sees user audio during the greeting → greeting is
    # truly uninterruptible. Normal interruptions resume after first turn.
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
    )

    # ── Pipeline ───────────────────────────────────────────────────────────────
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
        markers=_GOODBYE_HANGUP_MARKERS_MR,
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
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        _lap(t0, f"on_client_connected fired — queueing LLMRunFrame for {lead_name}")
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

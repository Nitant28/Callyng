#
# bot_sts_hi.py — Aakashvani | Diya — Pyramid Constructions (Hindi outbound, Gemini Live)
# Gemini 3.1 Flash Live | Hindi real-estate voice agent
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
_GOODBYE_HANGUP_MARKERS_HI = (
    "आपका दिन शुभ हो",
    "सटीक समय बता दीजिए",
    "मैं अभी भेज देती हूँ",
    "ज़रूरत नोट कर ली",
    "जरूरत नोट कर ली",
    "कोई बात नहीं... आपके समय के लिए",
    "din shubh ho",
    "abhi bhej deti hun",
)

# ═══════════════════════════════════════════════════════════════════════════════
# PREVIOUS HINDI SCRIPT (Tesseract Nilaya / Baner–Balewadi) — kept for reference only, May 2026
# -----------------------------------------------------------------------------
# Company: Tesseract | Project: Tesseract Nilaya — Baner–Balewadi, Pune
# Opening:  "नमस्ते, क्या {lead} जी से बात हो रही है?"
# Intro:    "मैं दीया बोल रही हूँ टेसरैक्ट की तरफ़ से। आपने हमारे
#            बानेर–बालेवाड़ी वाले 2 BHK, टेसरैक्ट निलया के लिए इन्क्वायरी
#            की थी — क्या अभी दो मिनट का समय है?"
# Interest: "बहुत अच्छा... बानेर–बालेवाड़ी लिंक रोड के पास हमारा एक खूबसूरत
#            प्रोजेक्ट है — टेसरैक्ट निलया। क्या आप अभी घर की तलाश में हैं?"
# Facts:    Size 720–780 sqft carpet | 14 floors | RERA Dec 2029 | commit mid-2027
#           Hinjewadi ~25 min | Expressway ~20 min | Katraj ~15 min
#           Amenities: club house, pool, co-working lounge, sky deck, kids zone
# Persona line: "RESPOND IN HINDI. YOU MUST RESPOND UNMISTAKABLY IN HINDI."
# ═══════════════════════════════════════════════════════════════════════════════


def build_system_instruction(lead_name: str) -> str:
    """Live API system instruction: persona → language → rules → facts → end-call."""
    return f"""
# AUDIO PROFILE: Diya (दिया)
## "Pyramid Parkland Nxt — Bhukum, Pune"

## THE SCENE
Diya is in a warm, professional real-estate office in Pune on a calm weekday morning.
She is placing a friendly outbound call to {lead_name} about a 2 BHK at
Pyramid Parkland Nxt. Tone: helpful and low-pressure — a trusted advisor, not a pushy
closer.

### DIRECTOR'S NOTES
Style: Warm, confident, unhurried. Natural spoken Hindi (Delhi–Pune neutral),
not stiff textbook Hindi. Vocal smile — the listener should feel welcomed.
Light fillers are fine ("हाँ", "अच्छा", "ठीक है", "जी").
Pace: Moderate; a small breath between sentences; a slight pause before key facts.
Never robotic, never rushed.
Accent / delivery: Clear Indian Hindi; soft, professional intonation.

---

## PERSONA
आपका नाम दिया है।
आप पिरामिड कंस्ट्रक्शंस की रिलेशनशिप मैनेजर हैं।
आप {lead_name} को पिरामिड पार्कलैंड नेक्स्ट — भूकूम, पुणे में 2 BHK के लिए
आउटबाउंड कॉल कर रही हैं।

## LANGUAGE (critical — match Live API `hi-IN`)
RESPOND IN HINDI. YOU MUST RESPOND UNMISTAKABLY IN HINDI.
सिर्फ़ हिंदी में बोलें — अंग्रेज़ी में जवाब न दें (loanwords like OK / site visit
जैसे बोलचाल के शब्द चल सकते हैं, लेकिन पूरा वाक्य हिंदी में रहे)।
संबोधन: सम्मानजनक "आप" का प्रयोग करें; कभी तुम-तू न बोलें।

---

## CONVERSATIONAL RULES
(Put these in order — one-time steps first, then the open-ended loop.)

**Rule 1 — Opening (one-time, do not repeat):**
कनेक्ट होते ही पहले सिर्फ़ यह एक वाक्य गर्मजोशी से बोलें, फिर रुकें:
"नमस्ते, क्या {lead_name} जी से बात हो रही है?"
उनके जवाब का इंतज़ार करें; आगे न बढ़ें।

**Rule 2 — Introduction (one-time, only after they confirm with हाँ / जी / हां):**
फिर बोलें, फिर थमें:
"मैं दीया बोल रही हूँ पिरामिड कंस्ट्रक्शंस की तरफ़ से। आपने हमारे भूकूम वाले
2 BHK, पिरामिड पार्कलैंड नेक्स्ट के लिए इन्क्वायरी की थी — क्या अभी दो मिनट का समय है?"

**Rule 3 — Interest check (one-time, only after they confirm time):**
"बहुत अच्छा... भूकूम, पौड रोड पर हमारा एक खूबसूरत प्रोजेक्ट है —
मानस लेक के सामने। क्या आप अभी घर की तलाश में हैं?"
एक सवाल — फिर रुकें।

**Rule 4 — Conversational loop (repeat as long as needed):**
अगर रुचि है तो इन विषयों पर बात करें: लोकेशन, साइज़, कब्ज़ा, सुविधाएँ,
कनेक्टिविटी, साइट विज़िट। जितना पूछें उतना बताएं — दबाव नहीं।
एक समय में एक सवाल — एक साँस में दो सवाल नहीं।

**Rule 4b — "कुछ और पूछना है?" ≠ "प्रॉपर्टी नहीं चाहिए" (बिक्री के लिए ज़रूरी):**
जब आपने सिर्फ़ जानकारी देने के बाद पूछा हो कि कॉलर के पास **और कोई खास सवाल /
डाउट** है या नहीं (जैसे "कुछ और पूछना है?", "कुछ और जानना है?",
"काही specific विचारायचं?" स्टाइल), और उनका जवाब छोटा नकारात्मक आए
("नहीं नहीं", "नहीं", "nahi nahi", "kuch nahi") — तो यह **आम तौर पर**
"और सवाल नहीं" है, **घर/प्रोजेक्ट मना** नहीं। उस समय कॉल को **Not_Interested**
की तरह खत्म मत समझें। आगे बढ़ें: नरमी से **साइट विज़िट** सुझाएँ — "एक बार
साइट पर आकर डिटेल क्लियर कर लें — कब स्लॉट ठीक रहेगा?"

**Rule 4c — साइट विज़िट / "चलेगा" / स्लॉट:**
जब आप साइट विज़िट / वीकेंड स्लॉट / टाइमिंग पूछ रही हों और जवाब छोटा
सकारात्मक हो ("हाँ", "जी", "चलेगा", "ठीक है", "Sunday fine", "एक बार मिलते हैं") —
यह **रुचि** है, इनकार नहीं। बातचीत जारी रखें; विज़िट कन्फर्म करें।

**Rule 5 — Site visit pitch (only when caller seems satisfied or curious):**
दबाव नहीं — एक हल्का सुझाव:
"एक बार साइट देखने का इंतज़ाम कर देती हूँ आपके लिए।
कब का समय आपके लिए ठीक रहेगा?"
अगर वे "नहीं / नहीं चाहिए" कहें तो दोबारा वही सवाल न पूछें — सम्मान से आगे बढ़ें।

---

## SPECIAL SITUATIONS (speak these lines in Hindi when the case matches)

**BUSY:**
"बिल्कुल ठीक... किस समय कॉल करूँ? सटीक समय बता दीजिए —
मैं आपके हिसाब से वापस कॉल करूँगी।"

**NOT INTERESTED:**
"कोई बात नहीं... आपके समय के लिए बहुत-बहुत धन्यवाद।
आपका दिन शुभ हो — नमस्ते!"

**BROCHURE REQUEST:**
"जी बिल्कुल... क्या आपका व्हाट्सऐप इसी नंबर पर है?
मैं अभी भेज देती हूँ।"

**WRONG PROPERTY TYPE (plot / shop / office / rent / commercial):**
"ठीक है... अभी हमारा फ़ोकस भूकूम में रेज़िडेंशियल 2 BHK पर है।
आपकी ज़रूरत नोट कर ली — बहुत धन्यवाद!"

**TRUST QUESTION (number कहाँ से मिला):**
"आपका नंबर हमें प्रॉपर्टी इन्क्वायरी डेटाबेस से मिला था।
मैं पिरामिड कंस्ट्रक्शंस की दीया बोल रही हूँ — आप कुछ भी पूछ सकते हैं।"

**AUDIO ISSUE (ONE-TIME ONLY — पूरे कॉल में सबसे ज़्यादा एक बार):**
पहली बार: अपने शब्दों में संक्षेप में कहें कि लाइन थोड़ी कट रही है और थोड़ा
ज़ोर से बोलने को कहें। प्रॉम्प्ट की लाइनें याद न करके बोलें।
एक बार के बाद ऑडियो / नेटवर्क / "weak signal" दोबारा न उछालें।
उसके बाद "HANDLING UNCLEAR INPUT" अपनाएँ।
ऑडियो / कनेक्शन की वजह से कॉल खत्म नहीं — रिकवरी हिंदी में जारी रखें।

---

## HANDLING UNCLEAR INPUT
जब रिसेप्शन खराब हो या कॉलर का जवाब छोटा / अस्पष्ट / एक शब्द हो:

CORE (non-negotiable):
- कभी चुप न रहें — हमेशा अगला वाक्य बोलें; बीच में अजीब सन्नाटा नहीं।
- ऑडियो वाली एक बार वाली लाइन दोहराएँ नहीं।
- पूरा जवाब अंग्रेज़ी में न दें ("Hello?", "Sorry what?") — हिंदी में रहें।
- एक ही सवाल दो से ज़्यादा बार लूप में न पूछें; एक बार साफ़ न पूछा तो अनुमान
  लेकर आगे के विषय पर चलें।

HOW TO RESPOND:
1. छोटे सकारात्मक शब्द ("हाँ", "हां", "जी", "हेलो", "hmm", "ok", "yes",
   "अच्छा", "ठीक"): इन्हें हरी बत्ती मानें — अगले कदम पर चलें; दोहराने को न कहें।
2. गड़बड़ / आधा समझ आया: हिंदी में हल्का अनुमान लगाएँ और पिछला सवाल सरल शब्दों
   में दोबारा पूछें। हर बार नया वाक्य — एक ही सफ़ेद जवाब को कॉपी-पेस्ट न करें।
3. आपके बोलने के बाद पूरी चुप्पी: अपने शब्दों में हल्का nudge — सुन पा रहे हैं?,
   फिर अगला एक सवाल।

MINDSET: दीया आत्मविश्वासी, गर्मजोश और बहाव बनाए रखती है।

---

## PROJECT FACTS (सिर्फ़ इन्हीं का उपयोग करें — कुछ भी गलत न बनाएँ)
- Location: भूकूम, पौड रोड, भारत पेट्रोल पंप के पास, मानस लेक व्यू
- Size: 768 से 816 sq ft (टोटल एरिया)
- Floors: 12
- RERA possession: दिसंबर 2030 | हमारी कमिटमेंट: लेट 2027
- Price: फ़ोन पर कोट नहीं — सिर्फ़ साइट विज़िट सुझाएँ
- Distances: हिंजवड़ी IT पार्क ~20 मिनट | चंदनी चौक ~15 मिनट | पिरंगुट ~5 मिनट
- Amenities: जिम, किड्स प्ले एरिया, एम्फ़ीथिएटर, वॉकिंग ट्रैक, इनडोर गेम्स

---

## PRONUNCIATION GUIDE (बोलते समय — हाइफ़न मत बोलिए, सिर्फ़ मार्गदर्शक हैं)
- Bhukum    → "भू-कूम"        — NEVER "भुटुम" or "भुकम"
- Hinjawadi → "हिन-जा-वा-डी"  — हर syllable साफ़
- Paud Road → "पौड रोड"       — "loud" से तुकबंदी
- Chandani  → "चन-दा-नी"
(Do NOT speak the hyphens — they are guides only.)

---

## GUARDRAILS
- एक समय में एक सवाल; दो सवाल एक साँस में नहीं।
- पहले सुनें, फिर जवाब दें।
- फ़ोन पर कीमत कोट न करें — साइट विज़िट सुझाएँ।
- जानकारी न हो तो: "मैं एक्ज़ैक्ट डिटेल चेक करके पाँच मिनट में वापस कॉल करती हूँ।"
- ऊपर के FACTS के अलावा कुछ गढ़ें नहीं।
- "नहीं" कह दिया तो वही सवाल दोबारा न पूछें।
- बीच कॉल में अटकें नहीं — हमेशा अगला वाक्य तैयार रखें।
- ऑडियो वाली बात पूरे कॉल में सिर्फ़ एक बार।
- आख़िरी यूज़र टर्न अस्पष्ट / एक शब्द हो तो पहले साफ़ करवाएँ — कॉल को जल्दबाज़ी
  में खत्म न समझें।
- आपके **पिछले** टर्न में सिर्फ़ "और कुछ पूछना / specific सवाल" था और कॉलर ने
  छोटा "नहीं" कहा — इसे **Not_Interested** न समझें; साइट विज़िट सुझाएँ।

---

## कॉल का अंत (अलविदा बोलकर + ``end_call`` टूल)

लीड की संरचित जानकारी **डिसकनेक्ट के बाद** ट्रांसक्रिप्ट से भरी जाती है — लाइव
में सिर्फ़ अच्छी बातचीत और सही समय पर कट करना।

जब टर्मिनल शर्तें पूरी हों, उसी टर्न में पहले "SPECIAL SITUATIONS" से मेल खाता
अलविदा गर्मजोशी से बोलें, फिर **तुरंत** ``end_call`` **एक बार** चलाएँ। दूसरी
बार मत सोचें, CRM/"सेव" की बात मत करें — यहाँ टूल अनुमत और अपेक्षित है।
प्लेटफ़ॉर्म अधिकतम अवधि के बाद भी काट सकता है।

कॉल **तभी** समाप्त करें जब: (1) आख़िरी **साफ़ समझा हुआ** यूज़र टर्न टर्मिनल
केस से मेल खाता हो (Not_Interested = असली प्रॉपर्टी इनकार, सिर्फ़ "और सवाल?"
पर छोटा "नहीं" नहीं; Busy; साफ़ समय वाला Callback; Wrong_Requirement), (2) कम
से कम 4–5 मायने रखने वाले कॉलर टर्न हों, (3) यह टर्न मैचिंग अलविदा दे रहा हो
— पहले वाला टर्मिनल अलविदा दोहराएँ नहीं।

**खत्म न करें** जब: आख़िरी टर्न अस्पष्ट/STT गड़बड़; "site"/"visit" विज़िट रुचि
लगे; कॉलर सवाल/ब्रोशर पर है; आपने सिर्फ़ "और सवाल?" पूछा और छोटा नकारात्मक
मिला (साइट विज़िट पर पिवट करें); ऑडियो रिकवरी; या संदेह हो — पहले **एक** साफ़
हिंदी सवाल से पक्का करें।

संदेह पर बात जारी रखें; गलत कट से बेहतर है थोड़ी लंबी बात। टर्मिनल अलविदा पर:
ऊपर वाली लाइन एक बार साफ़ बोलें, फिर ``end_call`` एक बार।
"""


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
            voice="Sulafat",

            # ── Language (Live API: match spoken language — Hindi) ─────────────
            language=Language.HI_IN,

            # ── VAD (server-side) ──────────────────────────────────────────────
            # 800 ms — slightly longer tail after speech ends; reduces spurious
            # micro-turns from PSTN noise before Gemini commits a user turn.
            vad=GeminiVADParams(
                silence_duration_ms=600,
                prefix_padding_ms=500,  # catch the soft first syllable
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

    # ── Bootstrap context (Live API: seed user turn so the model speaks first)
    bootstrap_messages = [
        {
            "role": "user",
            "content": (
                f"The call has just connected. {lead_name} has answered. "
                f"Execute Rule 1 from your conversational rules: say ONLY "
                f"the Rule 1 opening sentence (Hindi, addressing {lead_name}) "
                f"in a warm voice — then stop and wait for their response. "
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
        markers=_GOODBYE_HANGUP_MARKERS_HI,
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
import os
import asyncio
import json

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
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

load_dotenv(override=True)

SYSTEM_PROMPT = """
You are Diya, a highly professional and warm real estate concierge at Prowave Real Estate. You are calling {lead_name} from a general database.
START EVERY CALL WITH EXACTLY THIS (Hindi Default - NEVER CHANGE):

"Hello {lead_name}, मैं दिया बात कर रही हूँ Prowave Consultants से. बस जानना था, क्या आप अभी Pune में कोई घर या flat देख रहे हैं?"
ALTERNATE MARATHI OPENING (Only use if language_mode is Marathi):
"Hello {lead_name}, मी दिया बोलते आहे Prowave Consultants कडून. फक्त विचारायचं होतं, तुम्ही सध्या पुण्यात घर किंवा फ्लॅट बघत आहात का?"

LANGUAGE RULES (VERY STRICT - NO EXCEPTIONS):
- Default language_mode = "Hindi"
- You MUST start in Hindi unless the user has explicitly requested Marathi.
- If user says anything like "Marathi", "Marathi madhe", "Marathi me", "Marathi madhe bola", "fakt marathi", or "Marathi language" → Immediately switch to Marathi mode and reply only in Marathi using the exact Marathi scripts.
- Switch language ONLY if user clearly says: "English me baat karo", "Speak in English", or explicitly asks for Marathi.
Once switched, stay in that language.
- Strictly do not switch language on your own. Never auto-detect or mix languages.

MEMORY (Track Silently):
intent_status (Yes/No)
bhk_preference
location_preference

STRICT RESPONSE RULES:
Maximum 2 sentences per response.
Only one question at a time.
Listen extremely carefully before storing BHK or location.
If you think there is an Range issue (you are hearing gibberish or no audio) tell user to come in range in CURRENT LANGUAGE

SPECIAL HANDLING RULES:
Busy Rule: If user says "abhi busy hu", "thodi der mein call karna", "baad mein call karo" etc. →
"ठीक है sir, कब call करूँ? Exact time बता दीजिए।"
Other Property Rule: If user mentions any property other than buying flat/house (plot, shop, office, rent, villa, commercial etc.) →
Immediately say: "ठीक है sir, humne aapki requirement note kar li hai, thank you!" and end the call politely.
AUDIO / RANGE ISSUE RULE:
If you hear gibberish, unclear speech, cutting voice, low volume, or no audio → Immediately tell user to switch to a location with better range

CONVERSATION FLOW (Hindi - Default):
After greeting → "क्या आप अभी पुणे में फ्लैट खरीदने का सोच रहे हैं?"
If "Nahi/No" → "Ok, Thank you for your time sir." then call push_lead_data and end.
If "Haan/Yes" → "अच्छा sir… आप kya property dekh rahe ho? two या three BHK"
Next → "ठीक है sir… पुणे में कोई specific location के लिए आप देख रहे हैं?"
Once BHK + Location collected →
"okay sir… मैंने आपकी {bhk_preference} की आवश्यकता {location_preference} में नोट कर ली है। हमारे sales executives आपको जल्द कॉल करेंगे।" then call push_lead_data and end.

MARATHI MODE (Only if user explicitly switches):
Use Marathi Opening (ONLY IF HINDI OPENING IS NOT DONE ALREADY)
"तुम्ही सध्या पुण्यात फ्लॅट घेण्याचा विचार करत आहात का?"
"ठीक आहे… तुम्हाला कोणता BHK पाहिजे?"
"ओके… पुण्यात कोणती Location बघत आहात??"
Final: "छान… तुमची {bhk_preference} साठी {location_preference} मध्ये गरज नोंदवली आहे। आमचे sales executive तुम्हाला लवकरच कॉल करतील।" then call push_lead_data and end.

TRUST QUESTIONS (Exact):
Hindi: "Aapka number hume property inquiry database se mila hai. Me actually Prowave Consultants se Diya baat kar rahi hu"
Marathi: "तुमचा number आम्हाला property inquiry database मधून मिळाला आहे. मी prowave consultants कडून Diya बोलत आहे."

ANTI-HALLUCINATION & ANTI-LOOP:
Only store what user actually says.
Never assume information.
Never cut call abruptly. Always end politely.
Use natural soft fillers when needed.

MANDATORY:
Before every call end, ALWAYS call push_lead_data.
Applies to ALL cases: Interested, Not interested, Busy, Callback later, Unclear audio, Call disconnected.
If data missing, pass "NULL".
Call function FIRST, then send final goodbye. Never skip the function call.
"""

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting Hindi bot — Diya (Prowave)")

    body = getattr(runner_args, "body", {})
    lead_name = body.get("lead_name", "Sir")
    lead_phone = body.get("phone_number", "")

    # Inject lead name into prompt
    dynamic_prompt = SYSTEM_PROMPT.format(
        lead_name=lead_name,
        bhk_preference="{bhk_preference}",    # keep as template for LLM to fill
        location_preference="{location_preference}",
    )

    # --- push_lead_data function definition ---
    push_lead_data_fn = FunctionSchema(
        name="push_lead_data",
        description="Call this before ending every call to save lead qualification data. Always call this regardless of outcome.",
        properties={
            "intent_status": {
                "type": "string",
                "description": "Whether lead is interested: Yes, No, Busy, Callback, Unclear"
            },
            "bhk_preference": {
                "type": "string",
                "description": "BHK preference: 2BHK, 3BHK, NULL if not collected"
            },
            "location_preference": {
                "type": "string",
                "description": "Preferred location in Pune, or NULL if not collected"
            },
            "callback_time": {
                "type": "string",
                "description": "Requested callback time if busy, else NULL"
            },
            "language_used": {
                "type": "string",
                "description": "Language used in call: Hindi, Marathi, English"
            }
        },
        required=["intent_status", "bhk_preference", "location_preference"]
    )

    tools = ToolsSchema(standard_tools=[push_lead_data_fn])

    # --- STT ---
    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamSTTService.Settings(
            model="saarika:v2.5",
            language="unknown",   # auto-detect Hindi/Marathi
        )
    )

    # --- LLM ---
    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            system_instruction=dynamic_prompt,
            temperature=0.2,
        )
    )

    # --- Function handler ---
    async def handle_push_lead_data(params: FunctionCallParams):
        data = params.arguments
        logger.info(f"LEAD DATA CAPTURED: {json.dumps(data, ensure_ascii=False, indent=2)}")
        logger.info(f"Phone: {lead_phone} | Name: {lead_name}")

        # TODO: send to n8n webhook or CRM here
        # await send_to_n8n(lead_phone, lead_name, data)

        await params.result_callback({"status": "saved"})

    llm.register_function("push_lead_data", handle_push_lead_data)

    # --- TTS ---
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("CARTESIA_VOICE_ID"),
            model="sonic-3",
            language="hi",
        ),
        sample_rate=8000,
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Call connected — Diya starting")
        await asyncio.sleep(1.0)
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Call disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(f"Transport: {transport_type} | Call: {call_data.get('call_id', 'unknown')}")

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

    await run_bot(transport, runner_args)
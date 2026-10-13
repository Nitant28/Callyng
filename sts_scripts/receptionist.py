"""STS script: Professional AI Receptionist for AakashVani and Clinic Reception.

Handles inquiries, greetings, appointments, and messages in a warm,
articulate, bilingual (English + Hindi/Hinglish) tone.
"""

from __future__ import annotations

from google.genai.types import EndSensitivity, StartSensitivity
from pipecat.services.google.gemini_live.llm import GeminiVADParams
from pipecat.transcriptions.language import Language

from lead_context import LeadContext

# -- Script identity -----------------------------------------------------------
SCRIPT_ID = "receptionist"

# -- Model ---------------------------------------------------------------------
GEMINI_MODEL = "models/gemini-3.1-flash-live-preview"

# -- Voice ---------------------------------------------------------------------
# Aoede: warm, articulate, professional female receptionist voice.
GEMINI_VOICE = "Aoede"

# -- Language ------------------------------------------------------------------
GEMINI_LANGUAGE = Language.EN_IN

# -- Temperature ---------------------------------------------------------------
GEMINI_TEMPERATURE = 0.5

# -- Affective dialog ----------------------------------------------------------
GEMINI_ENABLE_AFFECTIVE_DIALOG = False

# -- VAD -----------------------------------------------------------------------
GEMINI_VAD = GeminiVADParams(
    start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
    end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW,
    prefix_padding_ms=220,
    silence_duration_ms=650,
)

# -- Goodbye hangup markers ----------------------------------------------------
GOODBYE_HANGUP_MARKERS = (
    "have a great day",
    "have a wonderful day",
    "thank you for calling",
    "take care",
    "goodbye",
    "bye bye",
    "aapka din shubh ho",
    "shubh din",
)

# -- Extraction schema ---------------------------------------------------------
EXTRACTION_SCHEMA: dict = {
    "mode": "both",
    "summary_prompt": "Summarise this front-desk receptionist call in 2-3 sentences. Focus on caller requirements, booking requests, or questions asked.",
    "fields": [
        {
            "key": "caller_name",
            "type": "string",
            "required": False,
            "description": "Name of the caller or lead",
        },
        {
            "key": "inquiry_type",
            "type": "string",
            "required": False,
            "description": "Type of inquiry: appointment, general, consultation, follow_up",
        },
        {
            "key": "intent_status",
            "type": "enum",
            "values": ["Interested", "Scheduled", "Callback_Requested", "Inquiry_Answered", "Not_Interested", "Busy", "Unknown"],
            "required": True,
            "description": "Call outcome or interest status",
        },
        {
            "key": "notes",
            "type": "string",
            "required": False,
            "description": "Key points discussed during the call",
        },
        {
            "key": "follow_up_required",
            "type": "boolean",
            "required": False,
            "description": "Whether a follow up or callback is needed",
        },
    ],
}


# -- Bootstrap messages --------------------------------------------------------

def build_bootstrap_messages(ctx: LeadContext) -> list[dict]:
    """Opening greeting spoken as soon as call connects."""
    name = (ctx.lead_name or "").strip()
    if name and name not in ("Sir / Madam", "Sir/Madam", "Unknown", ""):
        greeting_text = (
            f"Hello, good day! Am I speaking with {name}? ... "
            f"This is the receptionist calling from AakashVani. How are you doing today?"
        )
    else:
        greeting_text = (
            "Hello, good day! This is the receptionist calling from AakashVani. "
            "How can I assist you today?"
        )

    return [
        {
            "role": "user",
            "content": (
                f"The call has connected. The callee has picked up the phone. "
                f"Say ONLY this exact opening in a warm, welcoming, professional receptionist voice: "
                f"'{greeting_text}' "
                f"Then stop and wait for their response. Do not say anything else."
            ),
        }
    ]


# -- System instruction --------------------------------------------------------

def build_system_instruction(ctx: LeadContext) -> str:
    lead_name = ctx.lead_name or "the caller"
    lead_city = ctx.lead_city or ""
    city_context = f"in {lead_city}" if lead_city else ""

    return f"""
# ROLE & AUDIO PROFILE: Professional AI Receptionist
You are Ananya, a warm, professional, articulate executive receptionist at AakashVani AI Reception {city_context}.
You are speaking directly over a live phone call to {lead_name}.

## TONE & CADENCE
- Style: Warm, courteous, polished, and attentive. Natural vocal smile.
- Pacing: Unhurried, clear enunciation. Not robotic, not rushed.
- Language: English-first with fluent Hindi/Hinglish understanding and mirroring.
  - If the caller speaks English, respond in fluent, polished English.
  - If the caller speaks Hindi or Hinglish, respond warmly in natural Hindi or Hinglish.
- Length: Keep every turn concise (1 to 2 sentences max).
- Rule: ONE QUESTION, ONE BREATH. Never barrage the caller with multiple questions.

## OBJECTIVES
1. Greet the person warmly and confirm you are speaking with {lead_name}.
2. Explain that you are checking in from AakashVani AI Reception to assist them with any questions or service requests.
3. Listen attentively to whatever they say, acknowledge it gracefully, and provide helpful guidance.
4. If they need an appointment, callback, or details, collect the relevant info politely.
5. If they wish to end the call, thank them warmly ("Thank you so much for your time, have a wonderful day!").

## BEHAVIORAL RULES
- Never mention you are an LLM or artificial intelligence unless specifically asked. You are the digital front desk receptionist.
- Do not repeat long canned disclaimers.
- Always validate what the caller says before asking your next question.
- If the caller says they are busy or not interested, politely thank them and say goodbye without pushing.
"""

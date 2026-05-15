"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     AAKASHVANI — MASTER STS SCRIPT TEMPLATE                ║
║                                                                              ║
║  Copy this file to sts_scripts/<your_script_name>.py                        ║
║  Set STS_SCRIPT=<your_script_name> in .env                                  ║
║  Then run: just dev  or  just dev-sts                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

NAMING RULES (enforced by server.py):
  - Filename must be snake_case, start with a letter: my_bot.py → STS_SCRIPT=my_bot
  - No hyphens, no uppercase, no spaces

QUICK START CHECKLIST:
  [ ] 1. Fill in AGENT IDENTITY (persona, language, voice)
  [ ] 2. Fill in SYSTEM INSTRUCTION (scene, rules, facts, guardrails)
  [ ] 3. Fill in GOODBYE_HANGUP_MARKERS (phrases that trigger auto-hangup)
  [ ] 4. Fill in build_bootstrap_messages() (what fires on call connect)
  [ ] 5. Tune GEMINI_VAD for your language (short words need HIGH start sensitivity)
  [ ] 6. Adjust GEMINI_TEMPERATURE (0.4–0.6 for scripted agents, higher for open-ended)
"""

from __future__ import annotations

# ── Standard imports (do not remove) ──────────────────────────────────────────
from lead_context import LeadContext
from pipecat.services.google.gemini_live.llm import GeminiVADParams
from pipecat.transcriptions.language import Language
from google.genai.types import EndSensitivity, StartSensitivity

# ==============================================================================
# PASTE SETTINGS REFERENCE HERE
# Copy the contents of gemini_live_settings_reference.py here for quick access
# while editing this file. It will be ignored at runtime (it's just comments).
# ==============================================================================


# ==============================================================================
# SECTION 1 — AGENT IDENTITY
# These values configure the Gemini Live session at connect time.
# Changing them requires a server restart (they're read once per call).
# ==============================================================================

# ── Model ──────────────────────────────────────────────────────────────────────
# "models/gemini-3.1-flash-live-preview"  → fastest, lowest latency (~0.5s)
# "models/gemini-2.0-flash-live-001"      → stable alias if preview is unavailable
GEMINI_MODEL = "models/gemini-3.1-flash-live-preview"

# ── Voice ──────────────────────────────────────────────────────────────────────
# Available voices (as of 2026): Aoede, Charon, Fenrir, Kore, Puck,
#                                 Sulafat, Leda, Orus, Zephyr, Autonoe
# Tip: Try multiple voices for your language — quality varies significantly.
# Hindi recommendation: Sulafat (warm female), Aoede (neutral female)
GEMINI_VOICE = "Aoede"

# ── Language ───────────────────────────────────────────────────────────────────
# Must match what the caller will speak AND your system instruction language.
# Mismatch = poor transcription quality.
#
# Common values:
#   Language.HI_IN   → Hindi (India)
#   Language.MR_IN   → Marathi (India)
#   Language.EN_IN   → English (India accent)
#   Language.EN_US   → English (US)
#   Language.EN_GB   → English (UK)
#   Language.TA_IN   → Tamil
#   Language.TE_IN   → Telugu
#   Language.KN_IN   → Kannada
#   Language.BN_IN   → Bengali
#   Language.GU_IN   → Gujarati
#   Language.PA_IN   → Punjabi
GEMINI_LANGUAGE = Language.HI_IN

# ── Temperature ────────────────────────────────────────────────────────────────
# Controls response randomness.
# 0.0 = fully deterministic (same input → same output, robotic)
# 0.4–0.6 = recommended for sales/support scripts (warm but predictable)
# 0.7–0.9 = more creative/varied (better for open-ended coaching, tutoring)
# 1.0 = maximum creativity (may go off-script)
GEMINI_TEMPERATURE = 0.5

# ── Script ID (used in call logs) ──────────────────────────────────────────────
# Set this to something descriptive. Appears in call_logs.db under the route column.
SCRIPT_ID = "my_bot"


# ==============================================================================
# SECTION 2 — VOICE ACTIVITY DETECTION (VAD)
# Controls when Gemini considers the user to be speaking.
# This is SERVER-SIDE — runs on Google's infrastructure, not locally.
#
# CRITICAL for Indian languages: short affirmatives like हाँ, हो, हा, जी
# are ~150–200ms bursts. Default settings swallow them entirely.
# Use HIGH start sensitivity + LOW end sensitivity for these languages.
# ==============================================================================

GEMINI_VAD = GeminiVADParams(
    # START_SENSITIVITY_HIGH  → fires on soft/short speech onset  ← recommended for Indian languages
    # START_SENSITIVITY_LOW   → only fires on louder/longer onset
    # START_SENSITIVITY_UNSPECIFIED → Google default
    start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,

    # END_SENSITIVITY_LOW  → waits longer before closing turn (better for short words) ← recommended
    # END_SENSITIVITY_HIGH → cuts turn quickly after speech stops
    # END_SENSITIVITY_UNSPECIFIED → Google default
    end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW,

    # Milliseconds of audio BEFORE detected onset to include in the turn.
    # Default: ~500ms. Lower for short words (200ms), higher for noisy environments (400ms).
    prefix_padding_ms=200,

    # Milliseconds of silence after speech before turn is considered complete.
    # Default: ~600ms. Lower = snappier but may cut off slow speakers.
    silence_duration_ms=400,

    # Set disabled=True to turn off VAD entirely and drive turn-taking manually.
    # disabled=None,
)


# ==============================================================================
# SECTION 3 — GOODBYE HANGUP MARKERS
# When the bot says any of these phrases, the system waits ~2s then hangs up.
# This is a FALLBACK — the bot should call end_call() tool first.
# Add the last line(s) of each goodbye scenario here.
#
# Rules:
#   - Use substrings, not full sentences (more robust to minor paraphrasing)
#   - Add both Devanagari and romanized versions for reliability
#   - Do NOT add mid-conversation phrases or you'll get early hangups
# ==============================================================================

GOODBYE_HANGUP_MARKERS = (
    # NOT INTERESTED goodbye
    "आपका दिन शुभ हो",
    "din shubh ho",

    # BUSY / CALLBACK goodbye
    "सटीक समय बता दीजिए",

    # BROCHURE SENT goodbye
    "मैं अभी भेज देती हूँ",
    "abhi bhej deti hun",

    # WRONG REQUIREMENT goodbye
    "ज़रूरत नोट कर ली",
    "जरूरत नोट कर ली",

    # Add your own below:
    # "your goodbye phrase here",
)


# ==============================================================================
# SECTION 4 — BOOTSTRAP MESSAGE
# This fires the moment the call connects. It's a synthetic "user" message
# that instructs Gemini to say the opening line.
#
# Google best practice: "Include information about the user to have Live API
# personalize that greeting."
#
# Keep it short and directive — tell Gemini exactly what one thing to say,
# then stop. Do NOT ask it to do the whole call here.
# ==============================================================================

def build_bootstrap_messages(ctx: LeadContext) -> list[dict]:
    """
    Fires once on call connect. Tells Gemini to say only the opening line.
    ctx is populated from the POST /start body:
      ctx.lead_name  → "Rahul"
      ctx.lead_phone → "+919123866924"
      ctx.lead_city  → "Pune"
    """
    lead_name = ctx.lead_name
    return [
        {
            "role": "user",
            "content": (
                f"The call has just connected. {lead_name} has answered. "
                f"Execute Rule 1 from your conversational rules: say ONLY "
                f"the Rule 1 opening sentence, addressing {lead_name} by name, "
                f"in a warm voice — then stop and wait for their response. "
                f"Do not say anything else."
            ),
        }
    ]


# ==============================================================================
# SECTION 5 — SYSTEM INSTRUCTION
# The main prompt. Follows Google's recommended structure:
#   1. Agent Persona
#   2. Language instruction
#   3. Conversational Rules (one-time steps → loop → tool calls)
#   4. Special situations
#   5. Handling unclear input
#   6. Domain facts / knowledge base
#   7. Guardrails
#   8. Call ending rules
#
# Google best practice: "Separate each agent into a distinct SI."
# Google best practice: "Use the word 'unmistakably' to guide precision."
# Google best practice: "Specify tool calls within a flow in distinct sentences."
#
# IMPORTANT: system_instruction stays in LiveConnectConfig, NOT in the context
# window — so it is NOT evicted by context window compression. Put stable
# facts and rules here. Dynamic per-call data goes in build_bootstrap_messages().
# ==============================================================================

def build_system_instruction(ctx: LeadContext) -> str:
    """
    Returns the system instruction string for this call.
    ctx values can be interpolated for personalization.
    This is set once at session connect — changing mid-call has no effect.
    """
    lead_name = ctx.lead_name

    return f"""
# AUDIO PROFILE: [Agent Name]
## "[Campaign / Product Name]"

## THE SCENE
# Describe the setting and emotional tone. This shapes Gemini's vocal delivery.
# Example: "[Agent] is in a warm, professional office on a calm weekday morning.
# She is placing a friendly outbound call to {lead_name} about [topic].
# Tone: helpful and low-pressure — a trusted advisor, not a pushy closer."

[REPLACE: describe the scene and emotional tone here]

### DIRECTOR'S NOTES
# How should the agent sound? Give vocal direction as if briefing a voice actor.
# Example: Style: Warm, confident, unhurried. Light fillers are fine ("हाँ", "अच्छा").
# Pace: Moderate; a small breath between sentences.

[REPLACE: vocal direction here]

---

## AGENT PERSONA
# Who is the agent? Name, role, what they're calling about.
# If you want a specific accent, specify the output language here too.
# Example: "Your name is Diya. You are a relationship manager at XYZ Corp,
# calling {lead_name} about a 2 BHK flat in Bhukum, Pune."

[REPLACE: agent persona here]

## LANGUAGE
# Google best practice: include this exact pattern for non-English languages.
# Replace OUTPUT_LANGUAGE with your language name.
RESPOND IN [OUTPUT_LANGUAGE]. YOU MUST RESPOND UNMISTAKABLY IN [OUTPUT_LANGUAGE].
[Add any code-switching rules, e.g. "Loanwords like OK/WhatsApp are fine but full sentences must be in [language]."]

---

## CONVERSATIONAL RULES
# Google best practice: "Put rules in the order you expect the model to follow.
# Delineate between one-time elements and conversational loops."
# Google best practice: "Specify tool calls in distinct sentences."

**Rule 1 — Opening (one-time):**
# The very first thing the agent says. Should be a single short sentence.
# End with a question that requires a response before proceeding.
# Example: "नमस्ते, क्या {lead_name} जी से बात हो रही है?"
[REPLACE: opening line here]
Wait for their response before proceeding to Rule 2.

**Rule 2 — Introduction (one-time, only after Rule 1 confirmed):**
# Introduce the agent and reason for calling. One sentence. Then pause.
[REPLACE: introduction line here]

**Rule 3 — Qualifying question (one-time, only after Rule 2 confirmed):**
# A single open question to establish intent/interest.
[REPLACE: qualifying question here]
Ask one question — then stop and wait.

**Rule 4 — Conversational loop (repeat as needed):**
# The main body of the call. List the topics the agent can cover.
# Remind: one question at a time, never two questions in one breath.
Topics to cover: [REPLACE: list your topics — e.g. location, pricing, features, timeline]
One question at a time. Listen first, then respond.

**Rule 5 — Closing pitch (when caller seems satisfied):**
# A soft, low-pressure suggestion toward the desired outcome.
# Example: site visit, demo booking, callback scheduling.
[REPLACE: closing pitch here]
If they say no, do not repeat the same question — move on respectfully.

---

## SPECIAL SITUATIONS
# Handle these explicitly so Gemini doesn't improvise on edge cases.
# Google best practice: "If x happens, do y — provide specific examples."

**BUSY:**
[REPLACE: what to say when caller says they're busy — ask for a specific callback time]

**NOT INTERESTED:**
[REPLACE: graceful goodbye — warm, no pressure, thank them for their time]

**CALLBACK REQUEST:**
[REPLACE: confirm a specific time — "सटीक समय बता दीजिए" style]

**BROCHURE / INFO REQUEST:**
[REPLACE: confirm WhatsApp/email and promise to send]

**WRONG REQUIREMENT:**
[REPLACE: acknowledge, note their requirement, polite goodbye]

**TRUST / "WHERE DID YOU GET MY NUMBER":**
[REPLACE: explain data source, restate agent identity, invite questions]

**AUDIO ISSUE (ONE-TIME ONLY — maximum once per call):**
First time only: briefly mention the line is unclear and ask them to speak louder.
After that, never mention audio/network again — use HANDLING UNCLEAR INPUT instead.
Do not end the call due to audio issues.

---

## HANDLING UNCLEAR INPUT
# What to do when VAD fires but transcription is ambiguous or very short.
# Google best practice: never go silent — always say the next sentence.

RULES (non-negotiable):
- Never go silent — always say the next sentence.
- Never repeat the audio issue line after the first time.
- Never respond entirely in English — stay in [OUTPUT_LANGUAGE].
- Never loop the same question more than twice — assume and move forward.

RESPONSE GUIDE:
1. Short affirmatives ("हाँ", "जी", "yes", "ok", "hmm", "ठीक"): treat as green light — proceed.
2. Garbled / partial: make a gentle assumption, rephrase the last question simply.
3. Complete silence after bot speaks: soft nudge ("सुन पा रहे हैं?"), then one question.

---

## KNOWLEDGE BASE / DOMAIN FACTS
# List ONLY verified facts. Gemini will hallucinate if not grounded here.
# Google best practice: "Provide starting commands and information."
# Do NOT include anything you're not 100% sure about.

[REPLACE: paste your product/service facts here as bullet points]
# Example:
# - Product: 2 BHK apartments, 768–816 sq ft
# - Location: Bhukum, Paud Road, near Bharat Petrol Pump
# - Possession: Late 2027
# - Distances: Hinjawadi IT Park ~20 min

If you don't know a detail, say:
"मैं एक्ज़ैक्ट डिटेल चेक करके पाँच मिनट में वापस कॉल करती हूँ।"
Never fabricate facts.

---

## GUARDRAILS
# Hard rules. Use "unmistakably" for the most critical ones.
# Google best practice: "Provide specific examples of what not to do."

- One question at a time — unmistakably never ask two questions in one breath.
- Listen first, respond second.
- [REPLACE: add your domain-specific guardrails]
- If caller says "no" to something, do not ask the same question again.
- Never go silent mid-call — always have the next sentence ready.
- Audio issue line: maximum once per call.
- If the last user turn is ambiguous or one word — clarify before ending the call.

---

## CALL ENDING (goodbye + end_call tool)
# Google best practice: "Specify tool calls in distinct sentences."
# The end_call tool is defined in call_limits.py and registered in bot_sts.py.

When terminal conditions are met: first speak the matching goodbye line warmly,
then IMMEDIATELY call end_call once. Do not call it mid-conversation.
Do not mention CRM or saving data.

END the call ONLY when:
(1) The last CLEARLY UNDERSTOOD user turn matches a terminal case:
    Not_Interested = explicit property/product refusal (not just "no more questions")
    Busy = caller explicitly says they can't talk now
    Callback = caller gave a specific time to call back
    Wrong_Requirement = caller needs something outside your scope
(2) At least 4–5 meaningful caller turns have occurred.
(3) This turn is delivering the matching goodbye — don't repeat a goodbye already said.

DO NOT end when:
- Last turn is ambiguous, one word, or STT glitch
- Caller asked a question or requested info
- You just asked "any more questions?" and got a short "no" → suggest closing action instead
- Any doubt — ask one clarifying question first

When in doubt: keep talking. A slightly long call is better than a wrong hangup.

## CALL METADATA (internal — do not read aloud)
- Callee: {ctx.lead_phone!r}
- City: {ctx.lead_city!r}
"""
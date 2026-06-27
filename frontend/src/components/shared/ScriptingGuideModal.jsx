import React, { useState } from 'react';

const GUIDE_MARKDOWN = `# Aakashvani STS Scripting Guide

> **AI OUTPUT INSTRUCTIONS:** 
> Do NOT output a single monolithic python script. The user is configuring this script via the Aakashvani CMS Script Form.
> You MUST output your response in clearly separated sections formatted exactly for the form:
> 1. **System Instruction**: Plain text prompt.
> 2. **Bootstrap Messages**: Valid JSON Array.
> 3. **Lead Schema**: Valid JSON Object.
> 4. **Extraction Schema**: Valid JSON Object.
> 5. **Outcome Event Map**: Valid flat JSON Object (string -> string). No nested wrapper key.
> 6. **Outcome Terminal**: Valid JSON Array of strings.
> 7. **Outcome Retry**: Valid JSON Array of strings.
> 8. **Outcome Callback**: Valid JSON Array of strings.
> 9. **Goodbye Hangup Markers**: Valid JSON Array of strings.

This guide contains everything you need to know to design a complete, production-ready AI voice agent for the Aakashvani system. It is divided into two parts: Technical Reference and Conversational Design.

## PART 1: TECHNICAL REFERENCE

### 1. File Structure & Registration
Scripts are written as Python modules (e.g., \`sts_scripts/my_bot.py\`). They export several constants and functions that the Aakashvani server reads to configure the Gemini Live session and the post-call extraction engine.
- **Naming**: Snake_case filename (e.g., \`my_bot.py\`). Registered via \`.env\` using \`STS_SCRIPT=my_bot\`.

### 2. Required Configuration Fields
You must define the following constants in your script:
- \`SCRIPT_ID\` (str): Unique identifier for the script (e.g., \`"pyramid_bilingual"\`).
- \`GEMINI_MODEL\` (str): \`"models/gemini-3.1-flash-live-preview"\`.
- \`GEMINI_VOICE\` (str): Target voice (e.g., \`"Aoede"\`, \`"Charon"\`, \`"Sulafat"\`).
- \`GEMINI_LANGUAGE\` (Language): Primary language (e.g., \`Language.HI_IN\`, \`Language.EN_IN\`).
- \`GEMINI_TEMPERATURE\` (float): Usually \`0.4\` to \`0.6\` for scripted agents.
- \`GEMINI_VAD\` (GeminiVADParams): Voice Activity Detection tuning.
  - Indian languages require \`start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH\` and \`end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW\`.
- \`GOODBYE_HANGUP_MARKERS\` (tuple of str): Substrings that trigger an auto-hangup if the bot forgets to use the \`end_call\` tool.

### 3. Lead Data Schema
When a call connects, the system provides a \`LeadContext\` object containing the caller's data.
- \`ctx.lead_name\` (str): The caller's name.
- \`ctx.lead_phone\` (str): The caller's phone number.
- \`ctx.lead_city\` (str): The caller's city.
Use these variables to personalize the \`build_system_instruction\` and \`build_bootstrap_messages\`.

### 4. Post-Call Processing & Extraction Schema (Required for AI)
The AI requires an \`EXTRACTION_SCHEMA\` defined separately from your lead CSV schema. This tells the Groq LLM exactly what data to extract from the conversation transcript after the call.

**Note**: The extraction mode should be set to "both" by default for all scripts so that you receive both a generated summary paragraph and structured fields.

**Required AI Fields (1 strictly required):**
1. **\`intent_status\`** (Required: True)
   - **Format**: \`enum\` string.
   - **Constraints**: Must exactly match backend normalization states (e.g., \`Interested\`, \`Not_Interested\`, \`Busy\`, \`Callback_Requested\`, \`Wrong_Requirement\`, \`Unknown\`).
   - **Why**: This is required separately for the AI to properly trigger database state updates (e.g., automatically moving a lead to "Failed" if "Not_Interested").

You may add any number of additional optional fields (like \`callback_time\`, \`caller_notes\`) as needed.
\`\`\`python
EXTRACTION_SCHEMA = {
    "mode": "both",
    "summary_prompt": "Summarise this call in 2-3 sentences. Focus on the lead's interest level and any property preference mentioned.",
    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": ["Interested", "Not_Interested", "Busy", "Callback_Requested", "Wrong_Requirement"],
            "required": True,
            "description": "The final intent of the caller."
        },
        {
            "key": "callback_time",
            "type": "string",
            "required": False,
            "description": "Specific time requested for callback, if any."
        }
    ],
    "extraction_rules": "Infer only what the transcript supports."
}
\`\`\`
The AI must strictly return a JSON object matching these keys.

### 5. Outcome Mapping & Bucketing (Required)
You MUST provide mapping logic to tell the system how to handle the \`intent_status\` values extracted above.

**1. OUTCOME_EVENT_MAP (dict)**: 
Maps specific \`intent_status\` values to external webhook event names (e.g., sending qualified leads to a CRM). You only need to map intents that require an external trigger.

Output exactly this shape (a flat object, NOT wrapped in an "OUTCOME_EVENT_MAP" key):
\`\`\`json
{
  "Interested": "lead_qualified",
  "Callback_Requested": "lead_callback_scheduled"
}
\`\`\`

**2. Bucketing Arrays (list)**:
You must categorize EVERY possible \`intent_status\` from your Extraction Schema into exactly one of three routing arrays:
- \`OUTCOME_TERMINAL\`: The lead is finalized (e.g., "Interested", "Not_Interested").
- \`OUTCOME_RETRY\`: The call should be retried later (e.g., "Busy", "Unknown").
- \`OUTCOME_CALLBACK\`: A specific callback was scheduled.

Output exactly this shape for each array (e.g., for OUTCOME_TERMINAL):
\`\`\`json
[
  "Interested",
  "Not_Interested",
  "Wrong_Requirement"
]
\`\`\`

### 6. Post-Call Flow Architecture
The post-call pipeline follows a strict sequence:
1. **Transcript**: Call ends and audio is transcribed.
2. **LLM Extraction**: \`extraction_schema\` is fed to the LLM to extract JSON.
3. **Normalization Rules**: \`normalization_rules\` deterministically correct/enrich the extracted JSON.
4. **Outcome Routing**: The \`intent_status\` is routed via your \`outcome_terminal\`, \`outcome_retry\`, or \`outcome_callback\` buckets.
5. **State Update**: The lead is transitioned to \`completed\` or \`callback_scheduled\` (retry-bucket outcomes also use the callback card, not pending).

For a deep dive into configuration and examples, see [guides/admin_script_guide.md](file:///home/satyam/aakashvani/guides/admin_script_guide.md).

---

## PART 2: CONVERSATIONAL DESIGN

### 1. Core Principles
- **One Question, One Breath:** Never ask two questions in the same turn.
- **Listen First:** Validate the caller's input before pushing the next step.
- **Natural Code-Switching:** Use "Hinglish" or "Marathlish" if the audience is Indian. Pure formal Hindi/Marathi sounds robotic.
- **Emotional Intelligence:** Map out how to react to user tones (e.g., if stressed, soften voice and don't push).

### 2. System Instruction Structure
The \`build_system_instruction(ctx: LeadContext) -> str\` function returns the main prompt. It must include:
- **The Scene & Persona**: Who the agent is, their mood, and the setting.
- **Language Rules**: Explicit instructions on code-switching.
- **Emotional Intelligence**: "If caller sounds rushed: soften immediately, offer to keep it to one quick question or call back."
- **Call Flow (Rules)**: Numbered steps (Rule 1, Rule 2, etc.) for the conversational loop.
- **Guardrails**: Hard boundaries (e.g., "Never quote price over the phone.").
- **Call End Protocol**: Instructions on when to say a warm goodbye and immediately call the \`end_call\` tool.

### 3. Bootstrap Messages
The \`build_bootstrap_messages(ctx: LeadContext) -> list[dict]\` function jumpstarts the conversation. It returns a synthetic user message telling the bot to say its opening line:
\`\`\`python
def build_bootstrap_messages(ctx: LeadContext) -> list[dict]:
    return [{
        "role": "user",
        "content": f"The call has just connected. {ctx.lead_name} has answered. Say ONLY 'Hello... {ctx.lead_name} ji bol rahe hain?' in a warm voice, then stop."
    }]
\`\`\`

### 4. Example: Emotional Responses (from Pyramid Bilingual)
- **Hesitation:** Do not push. "No rush at all -- just sharing info so you have the full picture."
- **Budget Worry:** Never quote a price. "Pricing depends on the exact floorplan. Seeing it in person makes more sense."
- **Annoyance:** Stay calm. "Understood completely. Sorry for the inconvenience. Have a great day!"

---

## PART 3: BOILERPLATE TEMPLATE
Below is the master \`bot_template.py\`. Use this exact structure for all new agents.

\`\`\`python
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
  [ ] 7. Fill in EXTRACTION_SCHEMA (post-call Groq fields — see pyramid_extraction.py)
  [ ] 8. Fill in OUTCOME_EVENT_MAP and bucketing arrays (routing for intent_status)
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


# ── Post-call extraction schema (Groq reads transcript → JSON) ─────────────────
# See sts_scripts/pyramid_extraction.py for a full real-estate example.
EXTRACTION_SCHEMA = {
    "mode": "both",
    "summary_prompt": "Summarise this call in 2-3 sentences. Focus on the lead's interest level and any property preference mentioned.",
    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": [
                "Interested",
                "Not_Interested",
                "Busy",
                "Callback_Requested",
                "Wrong_Requirement",
                "Unknown",
            ],
            "required": True,
            "description": "Call outcome intent.",
        },
        {
            "key": "caller_notes",
            "type": "string",
            "required": False,
            "description": "Other useful facts, or the literal NULL.",
        },
    ],
    "extraction_rules": (
        "Infer only what the transcript supports. "
        "Reply with ONE JSON object matching the field keys."
    ),
}

OUTCOME_EVENT_MAP = {
    "Interested": "lead_qualified",
    "Callback_Requested": "lead_callback_scheduled"
}
OUTCOME_TERMINAL = ["Interested", "Not_Interested", "Wrong_Requirement"]
OUTCOME_RETRY = ["Busy", "Unknown"]
OUTCOME_CALLBACK = ["Callback_Requested"]


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
# =============================================================================
# GEMINI LIVE — COMPLETE SETTINGS REFERENCE
# Pipecat 1.1.0 + google-genai
# =============================================================================

# -----------------------------------------------------------------------------
# GeminiVADParams
# Controls server-side Voice Activity Detection (runs on Google's servers, not local)
# Usage: vad=GeminiVADParams(...) inside GeminiLiveLLMService.Settings
# -----------------------------------------------------------------------------
#
# disabled: bool | None
#   Set True to turn off Gemini's VAD entirely. You'd then need to drive
#   turn-taking manually. Default: None (VAD on)
#
# start_sensitivity: StartSensitivity | None
#   How aggressively Gemini detects the START of speech.
#   START_SENSITIVITY_HIGH  → fires on soft/short sounds like "हा", "हो", "हाँ"  ← use this
#   START_SENSITIVITY_LOW   → only fires on louder, longer speech onset
#   START_SENSITIVITY_UNSPECIFIED → Google default (somewhere in between)
#
# end_sensitivity: EndSensitivity | None
#   How aggressively Gemini detects the END of speech (turn boundary).
#   END_SENSITIVITY_HIGH → cuts the turn quickly after speech stops
#   END_SENSITIVITY_LOW  → waits longer before closing the turn (better for short words) ← use this
#   END_SENSITIVITY_UNSPECIFIED → Google default
#
# prefix_padding_ms: int | None
#   Milliseconds of audio BEFORE detected speech onset to include in the turn.
#   Higher = captures lead-in sounds but eats short words if set too high.
#   Default Google value is ~500ms. Recommended for short Hindi/Marathi words: 200ms
#
# silence_duration_ms: int | None
#   Milliseconds of silence after speech before the turn is considered complete.
#   Lower = snappier response but may cut off slow speakers.
#   Default Google value is ~600ms. Recommended: 400ms
#
# RECOMMENDED CONFIG FOR SHORT HINDI/MARATHI AFFIRMATIVES (हा, हो, हाँ, जी):
# from google.genai.types import StartSensitivity, EndSensitivity
# GEMINI_VAD = GeminiVADParams(
#     start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
#     end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW,
#     prefix_padding_ms=200,
#     silence_duration_ms=400,
# )

# -----------------------------------------------------------------------------
# GeminiLiveLLMService.Settings
# Top-level Pipecat wrapper settings — passed at service init time
# -----------------------------------------------------------------------------
#
# model: str
#   Gemini model to use.
#   "models/gemini-3.1-flash-live-preview"  ← current fast model
#   "models/gemini-2.0-flash-live-001"      ← stable alias if available
#
# temperature: float
#   Randomness of responses. 0.0 = deterministic, 1.0 = creative.
#   Recommended for sales scripts: 0.4–0.6
#
# max_tokens: int
#   Max output tokens per turn. Keep reasonable to avoid runaway responses.
#
# top_p: float
#   Nucleus sampling. Controls diversity. 0.9 is a safe default.
#
# top_k: int
#   Top-k sampling. Limits token selection pool per step.
#
# frequency_penalty: float
#   Penalizes repeating the same tokens. Helps avoid repetitive filler phrases.
#
# presence_penalty: float
#   Penalizes tokens already used anywhere in context. Encourages topic variety.
#
# seed: int
#   Fixed seed for reproducible outputs. Useful for testing, not production.
#
# voice: str
#   TTS voice name.
#   Hindi voices:   "Sulafat", "Aoede", "Charon", "Fenrir", "Kore", "Puck"
#   Test voices at: https://cloud.google.com/text-to-speech/docs/voices
#
# language: Language | str
#   Language for STT transcription and TTS generation.
#   Language.HI_IN  → Hindi
#   Language.MR_IN  → Marathi
#   Pass as pipecat Language enum or raw string "hi-IN", "mr-IN"
#
# modalities: GeminiModalities
#   What output types Gemini returns. For STS: AUDIO only.
#   GeminiModalities.AUDIO
#   GeminiModalities.TEXT
#   GeminiModalities.AUDIO_AND_TEXT  ← useful for debugging (logs what Gemini says)
#
# media_resolution: GeminiMediaResolution
#   Only relevant if sending images/video. Ignore for audio-only STS.
#
# vad: GeminiVADParams | None
#   See GeminiVADParams section above.
#   Set to None to disable VAD entirely.
#
# context_window_compression: ContextWindowCompressionParams | dict
#   Sliding window compression for long calls. When prompt tokens hit
#   trigger_tokens, Google drops oldest turns and retains ~half.
#   system_instruction is always preserved (it's on LiveConnectConfig).
#   {"enabled": True, "trigger_tokens": 20000}  ← default in bot_sts.py
#   Lower trigger_tokens = more aggressive compression = cheaper but less memory
#
# thinking: ThinkingConfig | dict
#   Enables chain-of-thought reasoning before responding.
#   Improves complex decisions (e.g. not-interested vs no-more-questions).
#   COSTS LATENCY — not recommended for real-time STS unless response time > 2s is ok.
#   {"thinking_budget": 1024}  ← token budget for thinking
#
# enable_affective_dialog: bool
#   Gemini adapts its tone to the emotional content of user speech.
#   Sounds frustrated → Diya softens. Sounds excited → Diya matches energy.
#   Recommended: True for sales/support bots.
#
# proactivity: ProactivityConfig | dict
#   Allows Gemini to speak unprompted — e.g. nudge after long silence.
#   Complements the "don't go silent" guardrail in the system prompt.
#   Check ProactivityConfig fields before enabling; behaviour can be surprising.
#
# filter_incomplete_user_turns: bool
#   Filters turns where user started speaking but didn't complete a thought.
#   Set False to let through very short turns like "हा", "जी", "यस".
#   Recommended: False when using START_SENSITIVITY_HIGH
#
# user_turn_completion_config: UserTurnCompletionConfig
#   Fine-grained control over when a user turn is considered "done".
#   Interacts with VAD end_sensitivity. Check Pipecat source for fields.

# -----------------------------------------------------------------------------
# LiveConnectConfig — raw Google API fields
# Not all are surfaced by Pipecat Settings; pass extras via settings.extra={}
# -----------------------------------------------------------------------------
#
# session_resumption: SessionResumptionConfig
#   Lets a session survive a WebSocket drop and resume mid-call.
#   Useful for Indian mobile networks with frequent brief drops.
#   Not yet in Pipecat Settings — would need custom _connect() override.
#
# safety_settings: list[SafetySetting]
#   Adjust content safety thresholds per harm category.
#   Useful if Gemini over-refuses on property/financial terms.
#   Pass via settings.extra if not surfaced directly.
#
# explicit_vad_signal: bool
#   If True, you drive VAD signals manually instead of letting Gemini do it.
#   Only use if you're implementing your own turn detection.
#
# history_config: HistoryConfig
#   Controls how conversation history is managed within the session.
#
# realtime_input_config: RealtimeInputConfig
#   Low-level control over the realtime audio input stream.
#   VAD params ultimately flow through here under the hood.
\`\`\`
`;

const ScriptingGuideModal = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('technical');

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(GUIDE_MARKDOWN);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6">
      <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
        {/* Header */}
        <div className="flex flex-col border-b border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#1C1810]">
          <div className="flex justify-between items-center px-6 py-4">
            <h3 className="font-headline-md text-on-surface dark:text-molten-text flex items-center gap-2">
              <span className="material-symbols-outlined text-primary dark:text-molten-primary">menu_book</span>
              Aakashvani Master Scripting Guide
            </h3>
            <div className="flex items-center gap-3">
              <button 
                onClick={handleCopy}
                title="Copies the full markdown guide for pasting to an AI"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary rounded-lg text-sm font-medium hover:bg-primary/20 dark:hover:bg-molten-primary/20 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">
                  {copied ? 'check' : 'content_copy'}
                </span>
                {copied ? 'Copied Full Guide!' : 'Copy for AI'}
              </button>
              <button 
                onClick={onClose} 
                className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
          </div>
          
          {/* Tabs */}
          <div className="flex px-6 gap-6 text-sm font-medium">
            <button
              onClick={() => setActiveTab('technical')}
              className={`pb-3 px-1 border-b-2 transition-colors ${
                activeTab === 'technical' 
                  ? 'border-primary text-primary dark:border-molten-primary dark:text-molten-primary' 
                  : 'border-transparent text-on-surface-variant hover:text-on-surface dark:text-molten-text-muted dark:hover:text-molten-text'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">integration_instructions</span>
                Technical Reference
              </div>
            </button>
            <button
              onClick={() => setActiveTab('conversational')}
              className={`pb-3 px-1 border-b-2 transition-colors ${
                activeTab === 'conversational' 
                  ? 'border-primary text-primary dark:border-molten-primary dark:text-molten-primary' 
                  : 'border-transparent text-on-surface-variant hover:text-on-surface dark:text-molten-text-muted dark:hover:text-molten-text'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">forum</span>
                Conversational Design
              </div>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto px-8 py-6 space-y-8 text-on-surface dark:text-molten-text bg-arctic-surface dark:bg-[#1A1A24]">
          
          {activeTab === 'technical' && (
            <div className="space-y-8 animate-in fade-in duration-300">
              <section>
                <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg mb-8">
                  <h4 className="text-lg font-bold text-primary dark:text-molten-primary mb-2 flex items-center gap-2">
                    <span className="material-symbols-outlined">smart_toy</span>
                    AI Output Instructions
                  </h4>
                  <p className="text-sm text-on-surface dark:text-molten-text">
                    When copying this guide to an AI, the AI is instructed to <strong>NOT</strong> generate a single Python file. Instead, it will generate the distinct JSON blocks and text components exactly as required by the Admin Script Config form.
                  </p>
                </div>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  1. Script Registration & Structure
                </h4>
                <p className="mb-4 text-on-surface-variant dark:text-molten-text-muted leading-relaxed">
                  Aakashvani scripts can be configured via Python modules or directly in the CMS Script Configs form.
                </p>
                <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                  <ul className="list-disc pl-5 space-y-2 text-sm">
                    <li><strong>Naming:</strong> Use snake_case starting with a letter (e.g., <code>my_script.py</code>).</li>
                    <li><strong>Registration:</strong> Add your script to the environment using <code>STS_SCRIPT=my_script</code> in your <code>.env</code> file.</li>
                    <li><strong>Variables:</strong> The server reads variables from your module to configure the Gemini Live session at connect time.</li>
                  </ul>
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  2. Required Configuration Fields
                </h4>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div>
                    <h5 className="font-bold text-lg mb-2">Gemini Variables</h5>
                    <ul className="space-y-3 text-sm bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                      <li><strong className="text-primary dark:text-molten-primary">SCRIPT_ID:</strong> A unique string identifier (e.g. <code>"pyramid_hi"</code>).</li>
                      <li><strong className="text-primary dark:text-molten-primary">GEMINI_MODEL:</strong> Use <code>"models/gemini-3.1-flash-live-preview"</code> for the lowest latency.</li>
                      <li><strong className="text-primary dark:text-molten-primary">GEMINI_VOICE:</strong> E.g., <code>"Aoede"</code>, <code>"Charon"</code>, <code>"Sulafat"</code>.</li>
                      <li><strong className="text-primary dark:text-molten-primary">GEMINI_LANGUAGE:</strong> E.g., <code>Language.HI_IN</code> or <code>Language.EN_IN</code>.</li>
                      <li><strong className="text-primary dark:text-molten-primary">GEMINI_TEMPERATURE:</strong> Recommend <code>0.4</code> to <code>0.6</code> for strict compliance.</li>
                    </ul>
                  </div>
                  <div>
                    <h5 className="font-bold text-lg mb-2">Voice Activity Detection (VAD)</h5>
                    <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">Critical for capturing short responses in Indian languages ("haan", "ji").</p>
                    <ul className="space-y-3 text-sm bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                      <li><strong className="text-primary dark:text-molten-primary">start_sensitivity:</strong> Must be <code>START_SENSITIVITY_HIGH</code>.</li>
                      <li><strong className="text-primary dark:text-molten-primary">end_sensitivity:</strong> Must be <code>END_SENSITIVITY_LOW</code>.</li>
                      <li><strong className="text-primary dark:text-molten-primary">prefix_padding_ms:</strong> <code>200ms</code>.</li>
                      <li><strong className="text-primary dark:text-molten-primary">silence_duration_ms:</strong> <code>400ms - 650ms</code>.</li>
                    </ul>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  3. Lead Context & Data Schema
                </h4>
                <p className="mb-4 text-sm text-on-surface-variant dark:text-molten-text-muted">
                  The <code>LeadContext</code> object is injected into dynamic functions upon connection. Use these fields to personalize the prompt.
                </p>
                <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E] text-sm font-mono overflow-x-auto text-green-400">
                  ctx.lead_name   // Caller's name (e.g., "Rahul")<br/>
                  ctx.lead_phone  // Caller's E.164 phone (e.g., "+919876543210")<br/>
                  ctx.lead_city   // Caller's city (e.g., "Pune")
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  4. Post-Call Extraction Schema (Required for AI)
                </h4>
                <div className="mb-4 text-sm text-on-surface-variant dark:text-molten-text-muted space-y-2">
                  <p>
                    Aakashvani processes the raw transcript using a Groq LLM against your defined JSON schema.
                    <strong> Note: This is required separately for the AI</strong> and is distinct from the Lead CSV Schema.
                  </p>
                  <p className="text-on-surface dark:text-molten-text mt-2 font-medium">Exactly 1 field is strictly required by the core system:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>
                      <strong><code>intent_status</code></strong> (Format: <code>enum</code> string) — Must be <code>required: True</code>. Constrained to specific system values.
                    </li>
                  </ul>
                  <p>You can add unlimited additional optional fields (e.g. <code>callback_time</code>, <code>caller_notes</code>).</p>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div>
                    <h5 className="font-bold text-lg mb-2">EXTRACTION_SCHEMA</h5>
                    <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30 h-[250px]">
{`EXTRACTION_SCHEMA = {
  "mode": "both",
  "summary_prompt": "Summarise this call in 2-3 sentences. Focus on the lead's interest level and any property preference mentioned.",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": [
        "Interested", 
        "Not_Interested", 
        "Callback_Requested"
      ],
      "required": True,
      "description": "Final caller intent."
    },
    {
      "key": "callback_time",
      "type": "string",
      "required": False
    }
  ],
  "extraction_rules": "Infer only facts."
}`}
                    </pre>
                  </div>
                  <div>
                    <h5 className="font-bold text-lg mb-2">Normalization</h5>
                    <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E] h-[250px] overflow-y-auto">
                      <p className="text-sm mb-2">The system maps specific <code>intent_status</code> enum values to system lead states:</p>
                      <ul className="list-disc pl-5 space-y-1 text-sm">
                        <li><code>Not_Interested</code> → marks lead as <strong>failed</strong>.</li>
                        <li><code>Callback_Requested</code> → marks lead as <strong>callback_scheduled</strong>.</li>
                        <li><code>Busy</code> → marks lead as <strong>callback_scheduled</strong> (for retry).</li>
                        <li><code>Early_Disconnect</code> → marks lead as <strong>callback_scheduled</strong> (short hangup).</li>
                        <li><code>Interested</code> → marks lead as <strong>completed</strong>.</li>
                      </ul>
                      <p className="text-sm mt-4 text-primary dark:text-molten-primary"><strong>Note:</strong> Always include <code>intent_status</code> in your schema if you want automated lead transitions.</p>
                    </div>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  5. Boilerplate Template
                </h4>
                <p className="mb-4 text-sm text-on-surface-variant dark:text-molten-text-muted">
                  Below is the master <code>bot_template.py</code>. Use this exact structure for all new agents.
                </p>
                <div className="bg-black/50 p-4 rounded-lg border border-outline-variant/30 max-h-[600px] overflow-y-auto">
                  <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap">
                    {`"""
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
  [ ] 7. Fill in EXTRACTION_SCHEMA (post-call Groq fields — see pyramid_extraction.py)
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


# ── Post-call extraction schema (Groq reads transcript → JSON) ─────────────────
# See sts_scripts/pyramid_extraction.py for a full real-estate example.
EXTRACTION_SCHEMA = {
    "mode": "both",
    "summary_prompt": "Summarise this call in 2-3 sentences. Focus on the lead's interest level and any property preference mentioned.",
    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": [
                "Interested",
                "Not_Interested",
                "Busy",
                "Callback_Requested",
                "Wrong_Requirement",
                "Unknown",
            ],
            "required": True,
            "description": "Call outcome intent.",
        },
        {
            "key": "caller_notes",
            "type": "string",
            "required": False,
            "description": "Other useful facts, or the literal NULL.",
        },
    ],
    "extraction_rules": (
        "Infer only what the transcript supports. "
        "Reply with ONE JSON object matching the field keys."
    ),
}

OUTCOME_EVENT_MAP = {
    "Interested": "lead_qualified",
    "Callback_Requested": "lead_callback_scheduled"
}
OUTCOME_TERMINAL = ["Interested", "Not_Interested", "Wrong_Requirement"]
OUTCOME_RETRY = ["Busy", "Unknown"]
OUTCOME_CALLBACK = ["Callback_Requested"]


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
# =============================================================================
# GEMINI LIVE — COMPLETE SETTINGS REFERENCE
# Pipecat 1.1.0 + google-genai
# =============================================================================

# -----------------------------------------------------------------------------
# GeminiVADParams
# Controls server-side Voice Activity Detection (runs on Google's servers, not local)
# Usage: vad=GeminiVADParams(...) inside GeminiLiveLLMService.Settings
# -----------------------------------------------------------------------------
#
# disabled: bool | None
#   Set True to turn off Gemini's VAD entirely. You'd then need to drive
#   turn-taking manually. Default: None (VAD on)
#
# start_sensitivity: StartSensitivity | None
#   How aggressively Gemini detects the START of speech.
#   START_SENSITIVITY_HIGH  → fires on soft/short sounds like "हा", "हो", "हाँ"  ← use this
#   START_SENSITIVITY_LOW   → only fires on louder, longer speech onset
#   START_SENSITIVITY_UNSPECIFIED → Google default (somewhere in between)
#
# end_sensitivity: EndSensitivity | None
#   How aggressively Gemini detects the END of speech (turn boundary).
#   END_SENSITIVITY_HIGH → cuts the turn quickly after speech stops
#   END_SENSITIVITY_LOW  → waits longer before closing the turn (better for short words) ← use this
#   END_SENSITIVITY_UNSPECIFIED → Google default
#
# prefix_padding_ms: int | None
#   Milliseconds of audio BEFORE detected speech onset to include in the turn.
#   Higher = captures lead-in sounds but eats short words if set too high.
#   Default Google value is ~500ms. Recommended for short Hindi/Marathi words: 200ms
#
# silence_duration_ms: int | None
#   Milliseconds of silence after speech before the turn is considered complete.
#   Lower = snappier response but may cut off slow speakers.
#   Default Google value is ~600ms. Recommended: 400ms
#
# RECOMMENDED CONFIG FOR SHORT HINDI/MARATHI AFFIRMATIVES (हा, हो, हाँ, जी):
# from google.genai.types import StartSensitivity, EndSensitivity
# GEMINI_VAD = GeminiVADParams(
#     start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
#     end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW,
#     prefix_padding_ms=200,
#     silence_duration_ms=400,
# )

# -----------------------------------------------------------------------------
# GeminiLiveLLMService.Settings
# Top-level Pipecat wrapper settings — passed at service init time
# -----------------------------------------------------------------------------
#
# model: str
#   Gemini model to use.
#   "models/gemini-3.1-flash-live-preview"  ← current fast model
#   "models/gemini-2.0-flash-live-001"      ← stable alias if available
#
# temperature: float
#   Randomness of responses. 0.0 = deterministic, 1.0 = creative.
#   Recommended for sales scripts: 0.4–0.6
#
# max_tokens: int
#   Max output tokens per turn. Keep reasonable to avoid runaway responses.
#
# top_p: float
#   Nucleus sampling. Controls diversity. 0.9 is a safe default.
#
# top_k: int
#   Top-k sampling. Limits token selection pool per step.
#
# frequency_penalty: float
#   Penalizes repeating the same tokens. Helps avoid repetitive filler phrases.
#
# presence_penalty: float
#   Penalizes tokens already used anywhere in context. Encourages topic variety.
#
# seed: int
#   Fixed seed for reproducible outputs. Useful for testing, not production.
#
# voice: str
#   TTS voice name.
#   Hindi voices:   "Sulafat", "Aoede", "Charon", "Fenrir", "Kore", "Puck"
#   Test voices at: https://cloud.google.com/text-to-speech/docs/voices
#
# language: Language | str
#   Language for STT transcription and TTS generation.
#   Language.HI_IN  → Hindi
#   Language.MR_IN  → Marathi
#   Pass as pipecat Language enum or raw string "hi-IN", "mr-IN"
#
# modalities: GeminiModalities
#   What output types Gemini returns. For STS: AUDIO only.
#   GeminiModalities.AUDIO
#   GeminiModalities.TEXT
#   GeminiModalities.AUDIO_AND_TEXT  ← useful for debugging (logs what Gemini says)
#
# media_resolution: GeminiMediaResolution
#   Only relevant if sending images/video. Ignore for audio-only STS.
#
# vad: GeminiVADParams | None
#   See GeminiVADParams section above.
#   Set to None to disable VAD entirely.
#
# context_window_compression: ContextWindowCompressionParams | dict
#   Sliding window compression for long calls. When prompt tokens hit
#   trigger_tokens, Google drops oldest turns and retains ~half.
#   system_instruction is always preserved (it's on LiveConnectConfig).
#   {"enabled": True, "trigger_tokens": 20000}  ← default in bot_sts.py
#   Lower trigger_tokens = more aggressive compression = cheaper but less memory
#
# thinking: ThinkingConfig | dict
#   Enables chain-of-thought reasoning before responding.
#   Improves complex decisions (e.g. not-interested vs no-more-questions).
#   COSTS LATENCY — not recommended for real-time STS unless response time > 2s is ok.
#   {"thinking_budget": 1024}  ← token budget for thinking
#
# enable_affective_dialog: bool
#   Gemini adapts its tone to the emotional content of user speech.
#   Sounds frustrated → Diya softens. Sounds excited → Diya matches energy.
#   Recommended: True for sales/support bots.
#
# proactivity: ProactivityConfig | dict
#   Allows Gemini to speak unprompted — e.g. nudge after long silence.
#   Complements the "don't go silent" guardrail in the system prompt.
#   Check ProactivityConfig fields before enabling; behaviour can be surprising.
#
# filter_incomplete_user_turns: bool
#   Filters turns where user started speaking but didn't complete a thought.
#   Set False to let through very short turns like "हा", "जी", "यस".
#   Recommended: False when using START_SENSITIVITY_HIGH
#
# user_turn_completion_config: UserTurnCompletionConfig
#   Fine-grained control over when a user turn is considered "done".
#   Interacts with VAD end_sensitivity. Check Pipecat source for fields.

# -----------------------------------------------------------------------------
# LiveConnectConfig — raw Google API fields
# Not all are surfaced by Pipecat Settings; pass extras via settings.extra={}
# -----------------------------------------------------------------------------
#
# session_resumption: SessionResumptionConfig
#   Lets a session survive a WebSocket drop and resume mid-call.
#   Useful for Indian mobile networks with frequent brief drops.
#   Not yet in Pipecat Settings — would need custom _connect() override.
#
# safety_settings: list[SafetySetting]
#   Adjust content safety thresholds per harm category.
#   Useful if Gemini over-refuses on property/financial terms.
#   Pass via settings.extra if not surfaced directly.
#
# explicit_vad_signal: bool
#   If True, you drive VAD signals manually instead of letting Gemini do it.
#   Only use if you're implementing your own turn detection.
#
# history_config: HistoryConfig
#   Controls how conversation history is managed within the session.
#
# realtime_input_config: RealtimeInputConfig
#   Low-level control over the realtime audio input stream.
#   VAD params ultimately flow through here under the hood.`}
                  </pre>
                </div>
              </section>

            </div>
          )}

          {activeTab === 'conversational' && (
            <div className="space-y-8 animate-in fade-in duration-300">
              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  1. The Anatomy of a Robust Agent
                </h4>
                <p className="mb-4 text-on-surface-variant dark:text-molten-text-muted leading-relaxed">
                  Writing a conversational prompt is about directing a persona's <strong>emotional intelligence</strong> rather than hardcoding a rigid decision tree.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold mb-2">One Question, One Breath</h5>
                    <p className="text-sm">Never ask two questions simultaneously. Humans answer only the last question heard. Stop completely after asking.</p>
                  </div>
                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold mb-2">Code-Switching is Natural</h5>
                    <p className="text-sm">Force "Hinglish" or "Marathlish". Pure textbook languages sound robotic. Mixing English nouns into regional sentences builds trust.</p>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  2. Building the System Instruction
                </h4>
                <p className="mb-4 text-sm">The <code>build_system_instruction()</code> method must return the master prompt string. Structure it carefully:</p>
                
                <div className="space-y-4">
                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-l-4 border-l-blue-500 border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold text-sm text-blue-500 mb-1">THE SCENE & PERSONA</h5>
                    <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-2">Define mood and setting to shape vocal delivery.</p>
                    <p className="text-xs font-mono">"You are Aryan, a relationship manager in a calm Pune office. Mood: warm professional, zero pressure. Speak like a senior colleague."</p>
                  </div>

                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-l-4 border-l-purple-500 border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold text-sm text-purple-500 mb-1">EMOTIONAL INTELLIGENCE (Crucial)</h5>
                    <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-2">Tell the model exactly how to react to specific caller energy.</p>
                    <ul className="text-xs font-mono space-y-1">
                      <li>• Hesitation: "Do NOT push. Soften voice. 'No rush at all, just sharing info.'"</li>
                      <li>• Budget Worry: "Never quote a price. Empathise first: 'Pricing context matters, let's meet at site.'"</li>
                      <li>• Annoyance: "Stay calm. Acknowledge and exit gracefully."</li>
                    </ul>
                  </div>

                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-l-4 border-l-green-500 border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold text-sm text-green-500 mb-1">CALL FLOW & GUARDRAILS</h5>
                    <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-2">Provide numbered rules (Rule 1: Greeting, Rule 2: Intro, etc.) and explicit guardrails.</p>
                    <ul className="text-xs font-mono space-y-1">
                      <li>• "Rule 1: Say exactly 'Hello... [Name] ji bol rahe hain?' and wait."</li>
                      <li>• "Guardrail: Never fabricate facts outside the Knowledge Base."</li>
                      <li>• "Guardrail: If audio is unclear, guess softly and move forward. Never go silent."</li>
                    </ul>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  3. Session Bootstrapping & Hangup
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h5 className="font-bold text-lg mb-2">Bootstrap Messages</h5>
                    <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">A synthetic first message injected upon connection to force the AI to speak immediately and consistently.</p>
                    <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`def build_bootstrap_messages(ctx):
  return [{
    "role": "user",
    "content": f"The call has just connected. {ctx.lead_name} answered. Execute Rule 1: say ONLY 'Hello... {ctx.lead_name} ji?' in a warm voice. Stop completely."
  }]`}
                    </pre>
                  </div>
                  <div>
                    <h5 className="font-bold text-lg mb-2">Call End Protocol</h5>
                    <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">The model must invoke the <code>end_call</code> tool to hang up. Teach it to say a goodbye first.</p>
                    <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-3 rounded text-xs font-mono border border-outline-variant/30 space-y-2">
                      <p>"When terminal conditions are met: first speak the matching goodbye warmly, then IMMEDIATELY call end_call once."</p>
                      <p className="text-red-400">GOODBYE_HANGUP_MARKERS (Fallback)</p>
                      <p>Always populate the <code>GOODBYE_HANGUP_MARKERS</code> constant in Python with substrings like "aapka din shubh ho" so the server hangs up if the bot forgets the tool.</p>
                    </div>
                  </div>
                </div>
              </section>

            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default ScriptingGuideModal;

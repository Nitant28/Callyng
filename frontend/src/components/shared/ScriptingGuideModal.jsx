import React, { useState } from 'react';

const GUIDE_MARKDOWN = `# Aakashvani CMS Script Template — AI Generation Guide

> **AI OUTPUT INSTRUCTIONS (CRITICAL — follow exactly):**
> You are generating a COMPLETE bot configuration for the Aakashvani CMS Script Config form.
> Do NOT output a Python script. Do NOT wrap everything in a single code block.
> You MUST output your response as **7 clearly separated, labeled sections** — one per form field.
> Each section must be copy-pasteable directly into the corresponding CMS form field.

---

## OUTPUT FORMAT — You MUST produce ALL 7 sections below:

### ▸ SECTION 1: System Instruction Template
**Form field:** \`system_instruction_template\` (plain text, supports {lead_name}, {lead_phone}, {lead_city} template variables)

Output the full system instruction as plain text. This is the master prompt that controls the AI agent's behavior on every call. Use the template variables {lead_name}, {lead_phone}, {lead_city} where appropriate — they are injected at call time.

**Required structure (follow this order):**

\`\`\`
# AUDIO PROFILE: [Agent Name]
## "[Campaign / Product Name]"

## THE SCENE
[Describe setting, emotional tone, mood. This shapes Gemini's vocal delivery.]
[Example: "Diya is in a warm, professional office on a calm weekday morning. She is placing a friendly outbound call to {lead_name} about [topic]. Tone: helpful and low-pressure — a trusted advisor, not a pushy closer."]

### DIRECTOR'S NOTES
[Vocal direction as if briefing a voice actor.]
[Example: Style: Warm, confident, unhurried. Light fillers like "हाँ", "अच्छा" are fine. Pace: Moderate.]

---

## AGENT PERSONA
[Who is the agent? Name, role, company, what they're calling about.]
[Example: "Your name is Diya. You are a relationship manager at XYZ Corp, calling {lead_name} about a 2 BHK flat in Bhukum, Pune."]

## LANGUAGE
RESPOND IN [OUTPUT_LANGUAGE]. YOU MUST RESPOND UNMISTAKABLY IN [OUTPUT_LANGUAGE].
[Add code-switching rules, e.g. "Loanwords like OK/WhatsApp are fine but full sentences must be in Hindi."]

---

## CONVERSATIONAL RULES

**Rule 1 — Opening (one-time):**
[The very first thing the agent says. Single short sentence ending with a question.]
[Example: "नमस्ते, क्या {lead_name} जी से बात हो रही है?"]
Wait for their response before proceeding to Rule 2.

**Rule 2 — Introduction (one-time, only after Rule 1 confirmed):**
[Introduce agent and reason for calling. One sentence. Then pause.]

**Rule 3 — Qualifying question (one-time, only after Rule 2):**
[A single open question to establish intent/interest.]
Ask one question — then stop and wait.

**Rule 4 — Conversational loop (repeat as needed):**
Topics to cover: [list topics — e.g. location, pricing, features, timeline]
One question at a time. Listen first, then respond.

**Rule 5 — Closing pitch (when caller seems satisfied):**
[Soft, low-pressure suggestion toward desired outcome — e.g. site visit, demo, callback.]
If they say no, do not repeat the same question — move on respectfully.

---

## SPECIAL SITUATIONS

**BUSY:**
[What to say — ask for specific callback time]

**NOT INTERESTED:**
[Graceful goodbye — warm, no pressure, thank them]

**CALLBACK REQUEST:**
[Confirm a specific time]

**BROCHURE / INFO REQUEST:**
[Confirm WhatsApp/email and promise to send]

**WRONG REQUIREMENT:**
[Acknowledge, note their requirement, polite goodbye]

**TRUST / "WHERE DID YOU GET MY NUMBER":**
[Explain data source, restate identity, invite questions]

**AUDIO ISSUE (ONE-TIME ONLY — maximum once per call):**
First time only: briefly mention line is unclear. After that, never mention audio again.

---

## HANDLING UNCLEAR INPUT

RULES (non-negotiable):
- Never go silent — always say the next sentence.
- Never repeat audio issue line after first time.
- Never respond entirely in English — stay in [OUTPUT_LANGUAGE].
- Never loop same question more than twice — assume and move forward.

RESPONSE GUIDE:
1. Short affirmatives ("हाँ", "जी", "yes", "ok"): treat as green light — proceed.
2. Garbled / partial: gentle assumption, rephrase simply.
3. Complete silence: soft nudge, then one question.

---

## KNOWLEDGE BASE / DOMAIN FACTS
[List ONLY verified facts as bullet points]
If you don't know a detail, say: "I'll check and call back in 5 minutes."
Never fabricate facts.

---

## GUARDRAILS
- One question at a time — unmistakably never ask two questions in one breath.
- Listen first, respond second.
- [Add domain-specific guardrails]
- If caller says "no" to something, do not ask again.
- Never go silent mid-call.
- Audio issue line: maximum once per call.

---

## CALL ENDING (goodbye + end_call tool)
When terminal conditions are met: first speak matching goodbye warmly,
then IMMEDIATELY call end_call once. Do not call it mid-conversation.

END the call ONLY when:
(1) Last CLEARLY UNDERSTOOD user turn matches a terminal case
(2) At least 4–5 meaningful caller turns have occurred
(3) This turn is delivering the matching goodbye

DO NOT end when:
- Last turn is ambiguous, one word, or STT glitch
- Caller asked a question or requested info
- Any doubt — ask one clarifying question first

## CALL METADATA (internal — do not read aloud)
- Callee: {lead_phone}
- City: {lead_city}
\`\`\`

---

### ▸ SECTION 2: Bootstrap Messages
**Form field:** \`bootstrap_messages_json\` (valid JSON Array)

This fires the moment the call connects. It's a synthetic "user" message that instructs Gemini to say the opening line. Must be a JSON array of message objects.

**Format:**
\`\`\`json
[
  {
    "role": "user",
    "content": "The call has just connected. {lead_name} has answered. Execute Rule 1 from your conversational rules: say ONLY the Rule 1 opening sentence, addressing {lead_name} by name, in a warm voice — then stop and wait for their response. Do not say anything else."
  }
]
\`\`\`

**Rules:**
- Always a JSON array with at least one object
- Each object must have "role" (always "user") and "content" (string)
- Use {lead_name}, {lead_phone}, {lead_city} as template variables
- Keep it short and directive — tell Gemini exactly what ONE thing to say

---

### ▸ SECTION 3: Lead Schema
**Form field:** \`lead_schema\` (valid JSON Object)

Defines the CSV column structure for lead uploads. The system always provides lead_name, lead_phone, lead_city by default.

**Format:**
\`\`\`json
{
  "fields": [
    { "key": "budget", "label": "Budget Range", "type": "string", "required": false },
    { "key": "property_type", "label": "Property Type", "type": "string", "required": false }
  ]
}
\`\`\`

**Rules:**
- Must be a JSON object with a "fields" array
- Each field: key (string), label (string), type (string), required (boolean)
- Use \`{ "fields": [] }\` if no extra lead columns are needed beyond the defaults

---

### ▸ SECTION 4: Extraction Schema
**Form field:** \`extraction_schema\` (valid JSON Object)
**CRITICAL: mode MUST always be "both"**

This tells the post-call Groq LLM what structured data to extract from the call transcript AND to generate a summary.

**Format:**
\`\`\`json
{
  "mode": "both",
  "summary_prompt": "Summarise this call in 2-3 sentences. Focus on the lead's interest level and any key preferences mentioned.",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": ["Interested", "Not_Interested", "Busy", "Callback_Requested", "Wrong_Requirement", "Unknown"],
      "required": true,
      "description": "The final intent of the caller."
    },
    {
      "key": "caller_notes",
      "type": "string",
      "required": false,
      "description": "Other useful facts mentioned by the caller, or null."
    }
  ],
  "extraction_rules": "Infer only what the transcript supports. Reply with ONE JSON object matching the field keys."
}
\`\`\`

**Hard constraints:**
- \`mode\` → MUST be \`"both"\` (generates summary paragraph + structured fields)
- \`intent_status\` field → MUST be present, type MUST be \`"enum"\`, \`required\` MUST be \`true\`
- Valid field types: \`"string"\`, \`"enum"\`, \`"boolean"\`, \`"datetime"\`
- Enum fields MUST have a non-empty \`"values"\` array
- Each field key must be unique
- You can add unlimited additional optional fields (e.g. callback_time, budget_range, preferred_location, site_visit_agreed)
- \`summary_prompt\` → required when mode is "both"; tells the LLM how to summarize
- \`extraction_rules\` → optional guidance string for the LLM

**IMPORTANT — Outcome Routing (done separately in CMS):**
The admin will drag-and-drop each \`intent_status\` enum value into one of three outcome buckets in the CMS UI:
- **Terminal** → Lead completed (no more calls)
- **Retry** → Retry later automatically
- **Callback** → Callback at scheduled time

Every intent_status value must be mapped to exactly one bucket. The AI does NOT need to output these arrays — the admin configures them via the drag-and-drop UI after pasting the extraction schema.

---

### ▸ SECTION 5: Outcome Event Map
**Form field:** \`outcome_event_map\` (valid flat JSON Object — string → string)

Maps specific \`intent_status\` values to webhook event names fired to external automation (e.g. n8n, CRM).
You only need to map intents that require an external trigger.

**Format (flat object, NOT wrapped in any key):**
\`\`\`json
{
  "Interested": "lead_qualified",
  "Callback_Requested": "lead_callback_scheduled"
}
\`\`\`

**Rules:**
- Keys MUST be valid values from your intent_status enum
- Values are the webhook event name strings
- Not every intent needs a mapping — only those that trigger external actions
- Use \`{}\` if no webhook events are needed

---

### ▸ SECTION 6: Normalization Rules
**Form field:** \`normalization_rules\` (valid JSON Array)

Deterministic correction rules applied AFTER AI extraction but BEFORE outcome bucketing. These encode reliable domain logic to fix known LLM inconsistencies — e.g. if the caller gave a callback time but the LLM set intent_status to "Unknown", the rule overrides it to "Callback_Requested".

**Format:**
\`\`\`json
[
  {
    "when": { "field": "callback_time", "truthy": true },
    "and_intent_in": ["", "Unknown", "Busy"],
    "set": { "intent_status": "Callback_Requested" }
  },
  {
    "when": { "field": "site_visit_agreed", "truthy": true },
    "and_intent_in": ["", "Unknown"],
    "set": { "intent_status": "Interested" }
  }
]
\`\`\`

**Rule structure:**
Each rule is a JSON object with:
- \`when\` (required): Condition to match.
  - \`field\` (string): The extraction field to check.
  - \`truthy\` (boolean): If true, fires when the field has a non-empty, non-null value. If false, fires when field is empty/null.
  - OR \`eq\` (any): Fires when the field exactly equals this value.
- \`and_intent_in\` (optional, array of strings): Only fires if the current \`intent_status\` is one of these values. Use \`""\` for empty/missing intent. Omit to fire regardless of current intent.
- \`set\` (required, object): Key-value pairs to overwrite in the extracted data. Use \`null\` to clear a field.

**Truthy evaluation:**
- Boolean \`true\` → truthy
- Non-empty strings (excluding "null", "none", "false", "0", "no") → truthy
- Everything else → falsy

**Rules:**
- Rules are applied in order — later rules can override earlier ones
- Use \`[]\` if no normalization is needed
- Common patterns: callback_time present → set Callback_Requested; site_visit_agreed → set Interested; bhk_preference present → override Wrong_Requirement to Interested

---

### ▸ SECTION 7: Goodbye Hangup Markers
**Form field:** \`goodbye_markers\` (valid JSON Array of strings)

Substrings that trigger an auto-hangup if the bot forgets to call the \`end_call\` tool. This is a safety fallback.

**Format:**
\`\`\`json
[
  "आपका दिन शुभ हो",
  "din shubh ho",
  "मैं अभी भेज देती हूँ",
  "abhi bhej deti hun",
  "ज़रूरत नोट कर ली"
]
\`\`\`

**Rules:**
- Use substrings, not full sentences (more robust to paraphrasing)
- Add both Devanagari AND romanized versions for reliability
- Do NOT add mid-conversation phrases or you'll get early hangups
- Must cover goodbye phrases for: not interested, busy/callback, brochure sent, wrong requirement

---

## FORM FIELDS NOT GENERATED BY AI (set manually in CMS)

These are configured directly in the CMS form, not output by AI:

| Field | Tab | Constraints |
|-------|-----|-------------|
| \`client_id\` | General | Select from dropdown |
| \`script_id\` | General | Lowercase snake_case, starts with letter: \`^[a-z][a-z0-9_]*$\` |
| \`route\` | General | \`"sts"\` or \`"cascaded"\` |
| \`active\` | General | Boolean checkbox |
| \`gemini_model\` | Models | Default: \`"models/gemini-3.1-flash-live-preview"\` |
| \`gemini_voice\` | Models | One of: Aoede, Charon, Fenrir, Kore, Puck, Sulafat, Leda, Orus, Zephyr, Autonoe |
| \`gemini_language\` | Models | BCP-47 code: hi-IN, mr-IN, en-IN, en-US, ta-IN, te-IN, kn-IN, bn-IN, gu-IN, pa-IN |
| \`gemini_temperature\` | Models | 0.0–2.0. Recommended: 0.4–0.6 for scripts |
| \`vad_start_sensitivity\` | Models | \`"HIGH"\` (recommended) or \`"LOW"\` |
| \`vad_end_sensitivity\` | Models | \`"LOW"\` (recommended) or \`"HIGH"\` |
| \`vad_silence_duration_ms\` | Models | Integer, default 800. Recommended: 400–650 |
| \`vad_prefix_padding_ms\` | Models | Integer, default 300. Recommended: 200 |
| \`outcome_terminal\` | Post-call | Drag-and-drop in CMS — intent values where lead is finalized |
| \`outcome_retry\` | Post-call | Drag-and-drop in CMS — intent values that trigger auto-retry |
| \`outcome_callback\` | Post-call | Drag-and-drop in CMS — intent values that schedule a callback |

**However, the AI SHOULD suggest recommended values for model/VAD settings and recommended outcome bucket assignments as a summary table after the 7 sections.**

---

## LEAD CONTEXT VARIABLES

These template variables are injected at call time and can be used in \`system_instruction_template\` and \`bootstrap_messages_json\`:

| Variable | Description | Example |
|----------|-------------|---------|
| \`{lead_name}\` | Caller's name | "Rahul" |
| \`{lead_phone}\` | Caller's E.164 phone | "+919876543210" |
| \`{lead_city}\` | Caller's city | "Pune" |

---

## QUICK CHECKLIST FOR AI OUTPUT

- [ ] Section 1: System Instruction — complete prompt with scene, persona, language, rules, situations, guardrails, call ending
- [ ] Section 2: Bootstrap Messages — JSON array with opening directive
- [ ] Section 3: Lead Schema — JSON object with fields array
- [ ] Section 4: Extraction Schema — JSON with mode="both", intent_status enum (required), summary_prompt
- [ ] Section 5: Outcome Event Map — flat JSON object mapping intents to webhook events
- [ ] Section 6: Normalization Rules — JSON array of deterministic correction rules (or [] if none)
- [ ] Section 7: Goodbye Markers — JSON array of hangup trigger substrings
- [ ] extraction_schema.mode is "both"
- [ ] Suggested model settings table (voice, language, temperature, VAD)
- [ ] Suggested outcome bucket assignments (which intents → terminal / retry / callback)
`;

const ScriptingGuideModal = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('fields');

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(GUIDE_MARKDOWN);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fieldSections = [
    {
      num: 1,
      title: 'System Instruction Template',
      field: 'system_instruction_template',
      tab: 'Prompts',
      type: 'Plain Text',
      icon: 'description',
      color: 'blue',
      required: true,
      description: 'The master prompt controlling the AI agent\u2019s behavior. Supports {lead_name}, {lead_phone}, {lead_city} template variables.',
      structure: [
        'THE SCENE & DIRECTOR\'S NOTES \u2014 setting, mood, vocal direction',
        'AGENT PERSONA \u2014 name, role, company, purpose',
        'LANGUAGE \u2014 output language with code-switching rules',
        'CONVERSATIONAL RULES \u2014 Rule 1-5 (opening \u2192 loop \u2192 close)',
        'SPECIAL SITUATIONS \u2014 busy, not interested, callback, brochure, wrong requirement, trust, audio',
        'HANDLING UNCLEAR INPUT \u2014 response guide for ambiguous turns',
        'KNOWLEDGE BASE \u2014 verified domain facts only',
        'GUARDRAILS \u2014 hard boundaries the agent must never cross',
        'CALL ENDING \u2014 goodbye protocol + end_call tool usage',
      ],
    },
    {
      num: 2,
      title: 'Bootstrap Messages',
      field: 'bootstrap_messages_json',
      tab: 'Prompts',
      type: 'JSON Array',
      icon: 'play_circle',
      color: 'green',
      required: true,
      description: 'Synthetic first message injected on call connect. Tells Gemini exactly what opening line to say.',
      example: `[
  {
    "role": "user",
    "content": "The call has just connected. {lead_name} has answered. Execute Rule 1: say ONLY the opening sentence addressing {lead_name} by name, in a warm voice \u2014 then stop and wait."
  }
]`,
      rules: [
        'Must be a JSON array with at least one object',
        'Each object: { "role": "user", "content": "..." }',
        'Use {lead_name}, {lead_phone}, {lead_city} as template variables',
        'Keep it short \u2014 tell Gemini exactly ONE thing to say',
      ],
    },
    {
      num: 3,
      title: 'Lead Schema',
      field: 'lead_schema',
      tab: 'Advanced',
      type: 'JSON Object',
      icon: 'person',
      color: 'purple',
      required: false,
      description: 'Defines extra CSV columns for lead uploads beyond the defaults (lead_name, lead_phone, lead_city).',
      example: `{
  "fields": [
    { "key": "budget", "label": "Budget Range", "type": "string", "required": false }
  ]
}`,
      rules: [
        'Must be a JSON object with a "fields" array',
        'Use { "fields": [] } if no extra columns needed',
        'Each field: key, label, type (string), required (boolean)',
      ],
    },
    {
      num: 4,
      title: 'Extraction Schema',
      field: 'extraction_schema',
      tab: 'Post-call',
      type: 'JSON Object',
      icon: 'analytics',
      color: 'red',
      required: true,
      description: 'Tells the post-call Groq LLM what structured data to extract from the transcript + how to summarize.',
      example: `{
  "mode": "both",
  "summary_prompt": "Summarise this call in 2-3 sentences.",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": ["Interested", "Not_Interested", "Busy",
                 "Callback_Requested", "Wrong_Requirement",
                 "Unknown"],
      "required": true,
      "description": "Final caller intent."
    },
    {
      "key": "caller_notes",
      "type": "string",
      "required": false,
      "description": "Other useful facts, or null."
    }
  ],
  "extraction_rules": "Infer only what the transcript supports."
}`,
      rules: [
        'mode MUST be "both" (summary + structured fields)',
        'intent_status enum field is REQUIRED with required: true',
        'Valid field types: "string", "enum", "boolean", "datetime"',
        'Enum fields must have a non-empty "values" array',
        'Each field key must be unique',
        'summary_prompt is required when mode is "both"',
        'Add optional fields as needed (callback_time, budget, site_visit_agreed, etc.)',
      ],
      note: 'After pasting, the admin will drag-and-drop each intent_status value into outcome buckets (Terminal / Retry / Callback) in the CMS UI.',
    },
    {
      num: 5,
      title: 'Outcome Event Map',
      field: 'outcome_event_map',
      tab: 'Post-call',
      type: 'JSON Object (flat)',
      icon: 'webhook',
      color: 'amber',
      required: false,
      description: 'Maps intent_status values \u2192 webhook event names for external automation (CRM, n8n).',
      example: `{
  "Interested": "lead_qualified",
  "Callback_Requested": "lead_callback_scheduled"
}`,
      rules: [
        'Flat JSON object: string \u2192 string (no nesting)',
        'Keys must be valid intent_status enum values',
        'Only map intents that trigger external webhook actions',
        'Use {} if no webhook events needed',
      ],
    },
    {
      num: 6,
      title: 'Normalization Rules',
      field: 'normalization_rules',
      tab: 'Post-call',
      type: 'JSON Array',
      icon: 'auto_fix_high',
      color: 'purple',
      required: false,
      description: 'Deterministic correction rules applied AFTER AI extraction, BEFORE outcome bucketing. Fixes known LLM inconsistencies.',
      example: `[
  {
    "when": { "field": "callback_time", "truthy": true },
    "and_intent_in": ["", "Unknown", "Busy"],
    "set": { "intent_status": "Callback_Requested" }
  },
  {
    "when": { "field": "site_visit_agreed", "truthy": true },
    "and_intent_in": ["", "Unknown"],
    "set": { "intent_status": "Interested" }
  }
]`,
      rules: [
        '"when": { "field": "<key>", "truthy": true/false } \u2014 fires when field is non-empty (or empty if false)',
        '"when": { "field": "<key>", "eq": <value> } \u2014 fires when field equals exact value',
        '"and_intent_in": [...] \u2014 optional guard, only fires if current intent_status is in this list (use "" for empty)',
        '"set": { "key": "value" } \u2014 overwrite extracted fields (use null to clear a field)',
        'Rules apply in order \u2014 later rules can override earlier ones',
        'Use [] if no normalization is needed',
      ],
    },
    {
      num: 7,
      title: 'Goodbye Hangup Markers',
      field: 'goodbye_markers',
      tab: 'Advanced',
      type: 'JSON Array',
      icon: 'call_end',
      color: 'rose',
      required: true,
      description: 'Substring triggers for auto-hangup if bot forgets to call end_call tool. Safety fallback.',
      example: `[
  "\u0906\u092a\u0915\u093e \u0926\u093f\u0928 \u0936\u0941\u092d \u0939\u094b",
  "din shubh ho",
  "\u092e\u0948\u0902 \u0905\u092d\u0940 \u092d\u0947\u091c \u0926\u0947\u0924\u0940 \u0939\u0942\u0901",
  "abhi bhej deti hun"
]`,
      rules: [
        'Use substrings, not full sentences',
        'Add both Devanagari AND romanized versions',
        'Do NOT add mid-conversation phrases',
        'Cover: not interested, busy/callback, brochure, wrong requirement goodbyes',
      ],
    },
  ];

  const modelSettings = [
    { field: 'gemini_model', label: 'Model', default: 'models/gemini-3.1-flash-live-preview', note: 'Fastest, lowest latency' },
    { field: 'gemini_voice', label: 'Voice', default: 'Aoede', note: 'Options: Aoede, Charon, Fenrir, Kore, Puck, Sulafat, Leda, Orus, Zephyr, Autonoe' },
    { field: 'gemini_language', label: 'Language', default: 'hi-IN', note: 'hi-IN, mr-IN, en-IN, en-US, ta-IN, te-IN, kn-IN, bn-IN, gu-IN, pa-IN' },
    { field: 'gemini_temperature', label: 'Temperature', default: '0.5', note: '0.4\u20130.6 for scripts, 0.7\u20130.9 for open-ended' },
    { field: 'vad_start_sensitivity', label: 'VAD Start', default: 'HIGH', note: 'HIGH for Indian languages (captures short words)' },
    { field: 'vad_end_sensitivity', label: 'VAD End', default: 'LOW', note: 'LOW waits longer before closing turn' },
    { field: 'vad_silence_duration_ms', label: 'Silence (ms)', default: '400\u2013650', note: 'Lower = snappier but may cut off slow speakers' },
    { field: 'vad_prefix_padding_ms', label: 'Prefix Pad (ms)', default: '200', note: 'Audio before detected speech onset' },
  ];

  const colorMap = {
    blue: { bg: 'bg-blue-500/10', border: 'border-blue-500', text: 'text-blue-500', dot: 'bg-blue-500' },
    green: { bg: 'bg-emerald-500/10', border: 'border-emerald-500', text: 'text-emerald-500', dot: 'bg-emerald-500' },
    purple: { bg: 'bg-purple-500/10', border: 'border-purple-500', text: 'text-purple-500', dot: 'bg-purple-500' },
    red: { bg: 'bg-red-500/10', border: 'border-red-500', text: 'text-red-500', dot: 'bg-red-500' },
    amber: { bg: 'bg-amber-500/10', border: 'border-amber-500', text: 'text-amber-500', dot: 'bg-amber-500' },
    emerald: { bg: 'bg-emerald-500/10', border: 'border-emerald-500', text: 'text-emerald-500', dot: 'bg-emerald-500' },
    rose: { bg: 'bg-rose-500/10', border: 'border-rose-500', text: 'text-rose-500', dot: 'bg-rose-500' },
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6">
      <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
        {/* Header */}
        <div className="flex flex-col border-b border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#1C1810]">
          <div className="flex justify-between items-center px-6 py-4">
            <h3 className="font-headline-md text-on-surface dark:text-molten-text flex items-center gap-2">
              <span className="material-symbols-outlined text-primary dark:text-molten-primary">menu_book</span>
              Script Template Field Guide
            </h3>
            <div className="flex items-center gap-3">
              <button 
                onClick={handleCopy}
                title="Copies the full AI prompt guide \u2014 paste it into any AI to generate all 7 form sections"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary rounded-lg text-sm font-medium hover:bg-primary/20 dark:hover:bg-molten-primary/20 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">
                  {copied ? 'check' : 'content_copy'}
                </span>
                {copied ? 'Copied!' : 'Copy for AI'}
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
            {[
              { key: 'fields', label: 'AI Output Fields', icon: 'format_list_numbered' },
              { key: 'model', label: 'Model & VAD Settings', icon: 'tune' },
              { key: 'rules', label: 'Outcome & Normalization', icon: 'rule' },
              { key: 'design', label: 'Prompt Design', icon: 'forum' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`pb-3 px-1 border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-primary text-primary dark:border-molten-primary dark:text-molten-primary' 
                    : 'border-transparent text-on-surface-variant hover:text-on-surface dark:text-molten-text-muted dark:hover:text-molten-text'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">{tab.icon}</span>
                  {tab.label}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto px-8 py-6 space-y-6 text-on-surface dark:text-molten-text bg-arctic-surface dark:bg-[#1A1A24]">
          
          {activeTab === 'fields' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              {/* Intro banner */}
              <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg">
                <h4 className="text-lg font-bold text-primary dark:text-molten-primary mb-1 flex items-center gap-2">
                  <span className="material-symbols-outlined">smart_toy</span>
                  AI Must Output All 7 Sections
                </h4>
                <p className="text-sm text-on-surface dark:text-molten-text">
                  When you <strong>Copy for AI</strong>, the prompt instructs the AI to generate each form field as a separate, labeled section. 
                  Each section is directly copy-pasteable into the corresponding CMS form field.
                </p>
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-2">
                  <strong>Note:</strong> Outcome routing (terminal / retry / callback buckets) is configured via <strong>drag-and-drop</strong> in the CMS Post-call tab after pasting the extraction schema. The AI only needs to suggest which intents go where.
                </p>
              </div>

              {/* Field cards */}
              {fieldSections.map(section => {
                const c = colorMap[section.color] || colorMap.blue;
                return (
                  <div key={section.num} className={`border rounded-lg overflow-hidden ${c.border}/30 dark:${c.border}/20`}>
                    {/* Card header */}
                    <div className={`px-5 py-3 ${c.bg} flex items-center justify-between`}>
                      <div className="flex items-center gap-3">
                        <div className={`w-7 h-7 rounded-full ${c.dot} flex items-center justify-center text-white text-xs font-bold`}>
                          {section.num}
                        </div>
                        <div>
                          <h5 className={`font-bold ${c.text}`}>{section.title}</h5>
                          <div className="flex items-center gap-2 text-xs text-on-surface-variant dark:text-molten-text-muted mt-0.5">
                            <code className="bg-black/10 dark:bg-white/10 px-1.5 py-0.5 rounded">{section.field}</code>
                            <span>&bull;</span>
                            <span>{section.type}</span>
                            <span>&bull;</span>
                            <span className="text-on-surface-variant dark:text-molten-text-muted">{section.tab} tab</span>
                          </div>
                        </div>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${section.required ? 'bg-red-500/15 text-red-600 dark:text-red-400' : 'bg-gray-500/15 text-gray-600 dark:text-gray-400'}`}>
                        {section.required ? 'REQUIRED' : 'OPTIONAL'}
                      </span>
                    </div>
                    {/* Card body */}
                    <div className="px-5 py-4 bg-surface-container-lowest dark:bg-[#141210] space-y-3">
                      <p className="text-sm text-on-surface-variant dark:text-molten-text-muted">{section.description}</p>
                      
                      {/* Structure list (for system instruction) */}
                      {section.structure && (
                        <div>
                          <h6 className="text-xs font-bold text-on-surface dark:text-molten-text mb-2 uppercase tracking-wide">Required Structure</h6>
                          <ol className="list-decimal pl-5 space-y-1 text-xs text-on-surface-variant dark:text-molten-text-muted">
                            {section.structure.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {/* Example */}
                      {section.example && (
                        <div>
                          <h6 className="text-xs font-bold text-on-surface dark:text-molten-text mb-1 uppercase tracking-wide">Example</h6>
                          <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30 max-h-[200px]">
                            {section.example}
                          </pre>
                        </div>
                      )}

                      {/* Rules */}
                      {section.rules && (
                        <div>
                          <h6 className="text-xs font-bold text-on-surface dark:text-molten-text mb-1 uppercase tracking-wide">Constraints</h6>
                          <ul className="space-y-1 text-xs">
                            {section.rules.map((rule, i) => (
                              <li key={i} className="flex items-start gap-2 text-on-surface-variant dark:text-molten-text-muted">
                                <span className="material-symbols-outlined text-[14px] mt-0.5 text-primary dark:text-molten-primary shrink-0">chevron_right</span>
                                {rule}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Extra note (e.g. drag-and-drop for extraction schema) */}
                      {section.note && (
                        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
                          <span className="material-symbols-outlined text-[16px] mt-0.5 shrink-0">info</span>
                          {section.note}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {activeTab === 'model' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg">
                <h4 className="text-lg font-bold text-primary dark:text-molten-primary mb-1 flex items-center gap-2">
                  <span className="material-symbols-outlined">tune</span>
                  Model & VAD Settings
                </h4>
                <p className="text-sm text-on-surface dark:text-molten-text">
                  These are configured directly in the CMS <strong>Models</strong> tab, not generated by AI. The AI should suggest recommended values.
                </p>
              </div>

              <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="bg-surface dark:bg-[#1C1810] border-b border-outline-variant dark:border-[#2A345E]">
                      <th className="px-4 py-3 font-bold text-on-surface-variant dark:text-molten-text-muted text-xs uppercase tracking-wide">Field</th>
                      <th className="px-4 py-3 font-bold text-on-surface-variant dark:text-molten-text-muted text-xs uppercase tracking-wide">Default</th>
                      <th className="px-4 py-3 font-bold text-on-surface-variant dark:text-molten-text-muted text-xs uppercase tracking-wide">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modelSettings.map((s, i) => (
                      <tr key={s.field} className={`border-b border-outline-variant/50 dark:border-[#2A345E]/50 ${i % 2 === 0 ? '' : 'bg-surface dark:bg-[#1C1810]/50'}`}>
                        <td className="px-4 py-3">
                          <code className="text-xs bg-black/10 dark:bg-white/10 px-1.5 py-0.5 rounded font-bold">{s.field}</code>
                          <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-0.5">{s.label}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-primary dark:text-molten-primary font-bold">{s.default}</td>
                        <td className="px-4 py-3 text-xs text-on-surface-variant dark:text-molten-text-muted">{s.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <section>
                <h4 className="text-lg font-bold mb-3 text-primary dark:text-molten-primary">Available Voices</h4>
                <div className="flex flex-wrap gap-2">
                  {['Aoede', 'Charon', 'Fenrir', 'Kore', 'Puck', 'Sulafat', 'Leda', 'Orus', 'Zephyr', 'Autonoe'].map(v => (
                    <span key={v} className="px-3 py-1.5 bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-full text-sm font-medium">{v}</span>
                  ))}
                </div>
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-2">Hindi recommendation: <strong>Sulafat</strong> (warm female), <strong>Aoede</strong> (neutral female). Test multiple voices \u2014 quality varies by language.</p>
              </section>

              <section>
                <h4 className="text-lg font-bold mb-3 text-primary dark:text-molten-primary">Supported Languages</h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                  {[
                    { code: 'hi-IN', name: 'Hindi' },
                    { code: 'mr-IN', name: 'Marathi' },
                    { code: 'en-IN', name: 'English (India)' },
                    { code: 'en-US', name: 'English (US)' },
                    { code: 'en-GB', name: 'English (UK)' },
                    { code: 'ta-IN', name: 'Tamil' },
                    { code: 'te-IN', name: 'Telugu' },
                    { code: 'kn-IN', name: 'Kannada' },
                    { code: 'bn-IN', name: 'Bengali' },
                    { code: 'gu-IN', name: 'Gujarati' },
                    { code: 'pa-IN', name: 'Punjabi' },
                  ].map(l => (
                    <div key={l.code} className="flex items-center gap-2 px-3 py-2 bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm">
                      <code className="text-primary dark:text-molten-primary font-bold text-xs">{l.code}</code>
                      <span className="text-on-surface-variant dark:text-molten-text-muted">{l.name}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h4 className="text-lg font-bold mb-3 text-primary dark:text-molten-primary">VAD Tuning Guide</h4>
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-sm">
                  <p className="font-bold text-amber-700 dark:text-amber-300 mb-2">{'\u26A0\uFE0F'} Critical for Indian Languages</p>
                  <p className="text-on-surface-variant dark:text-molten-text-muted mb-3">
                    Short affirmatives like \u0939\u093e\u0901, \u0939\u094b, \u0939\u093e, \u091c\u0940 are ~150\u2013200ms bursts. Default settings swallow them entirely.
                  </p>
                  <div className="bg-black/50 p-3 rounded text-xs font-mono text-green-400">
                    vad_start_sensitivity: HIGH  \u2190 fires on soft/short speech<br/>
                    vad_end_sensitivity: LOW     \u2190 waits longer before closing turn<br/>
                    vad_prefix_padding_ms: 200   \u2190 captures lead-in sounds<br/>
                    vad_silence_duration_ms: 400  \u2190 snappy but captures short words
                  </div>
                </div>
              </section>
            </div>
          )}

          {activeTab === 'rules' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              {/* Outcome Routing section */}
              <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg">
                <h4 className="text-lg font-bold text-primary dark:text-molten-primary mb-1 flex items-center gap-2">
                  <span className="material-symbols-outlined">rule</span>
                  Outcome Routing & Normalization
                </h4>
                <p className="text-sm text-on-surface dark:text-molten-text">
                  After the AI extracts <code>intent_status</code> from the transcript, two things happen in sequence:
                  <strong> normalization rules</strong> correct the extraction, then <strong>outcome routing</strong> determines the lead state.
                </p>
              </div>

              {/* Visual flow */}
              <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] p-6">
                <h5 className="font-bold text-sm mb-4 text-on-surface dark:text-molten-text">Post-Call Pipeline Flow</h5>
                <div className="flex flex-col sm:flex-row items-center gap-3 text-xs font-medium">
                  {[
                    { label: 'Call Ends', icon: 'call_end', color: 'bg-gray-500' },
                    { label: 'Transcript', icon: 'description', color: 'bg-blue-500' },
                    { label: 'LLM Extraction', icon: 'analytics', color: 'bg-purple-500' },
                    { label: 'Normalization', icon: 'auto_fix_high', color: 'bg-amber-500' },
                    { label: 'Outcome Routing', icon: 'route', color: 'bg-emerald-500' },
                    { label: 'State Update', icon: 'check_circle', color: 'bg-green-500' },
                  ].map((step, i) => (
                    <React.Fragment key={step.label}>
                      <div className={`${step.color} text-white px-3 py-2 rounded-lg flex items-center gap-1.5 shrink-0`}>
                        <span className="material-symbols-outlined text-[16px]">{step.icon}</span>
                        {step.label}
                      </div>
                      {i < 5 && <span className="material-symbols-outlined text-on-surface-variant dark:text-molten-text-muted text-[20px] rotate-90 sm:rotate-0">arrow_forward</span>}
                    </React.Fragment>
                  ))}
                </div>
              </div>

              {/* Outcome Routing - Drag and Drop */}
              <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] p-5">
                <h5 className="font-bold text-sm mb-2 text-on-surface dark:text-molten-text flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px] text-primary dark:text-molten-primary">drag_indicator</span>
                  Outcome Routing (Drag & Drop in CMS)
                </h5>
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-4">
                  After pasting the extraction schema, the CMS shows all <code>intent_status</code> enum values as draggable pills.
                  The admin drags each value into one of three buckets. <strong>Every value must be in exactly one bucket.</strong>
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="rounded-lg border-2 border-emerald-500/30 p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                      <h6 className="font-bold text-emerald-600 dark:text-emerald-400">Terminal</h6>
                    </div>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-3">Lead \u2192 <strong>Completed</strong>. No more calls.</p>
                    <div className="flex flex-wrap gap-1.5">
                      {['Interested', 'Not_Interested', 'Wrong_Requirement'].map(v => (
                        <span key={v} className="px-2 py-1 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 rounded text-xs font-medium">{v}</span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border-2 border-amber-500/30 p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-3 h-3 rounded-full bg-amber-500"></span>
                      <h6 className="font-bold text-amber-600 dark:text-amber-400">Retry</h6>
                    </div>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-3">Lead \u2192 <strong>Pending</strong>, then Failed after max retries.</p>
                    <div className="flex flex-wrap gap-1.5">
                      {['Busy', 'Unknown'].map(v => (
                        <span key={v} className="px-2 py-1 bg-amber-500/10 text-amber-700 dark:text-amber-300 rounded text-xs font-medium">{v}</span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border-2 border-blue-500/30 p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                      <h6 className="font-bold text-blue-600 dark:text-blue-400">Callback</h6>
                    </div>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-3">Lead \u2192 <strong>Callback Scheduled</strong>.</p>
                    <div className="flex flex-wrap gap-1.5">
                      {['Callback_Requested', 'Early_Disconnect'].map(v => (
                        <span key={v} className="px-2 py-1 bg-blue-500/10 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">{v}</span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                    <p className="text-xs font-bold text-red-600 dark:text-red-400 mb-1">{'\u274C'} Unmapped Intent</p>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">A value not in any bucket blocks saving</p>
                  </div>
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                    <p className="text-xs font-bold text-red-600 dark:text-red-400 mb-1">{'\u274C'} Overlapping Buckets</p>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">Same value in two buckets blocks saving</p>
                  </div>
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                    <p className="text-xs font-bold text-red-600 dark:text-red-400 mb-1">{'\u274C'} Stale/Orphan Value</p>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">Bucket value not in intent_status enum</p>
                  </div>
                </div>
              </div>

              {/* Normalization Rules */}
              <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] p-5">
                <h5 className="font-bold text-sm mb-2 text-on-surface dark:text-molten-text flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px] text-purple-500">auto_fix_high</span>
                  Normalization Rules (Post-call tab)
                </h5>
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-4">
                  Deterministic corrections applied <strong>after</strong> AI extraction but <strong>before</strong> outcome bucketing.
                  Encodes reliable domain logic to fix known LLM inconsistencies. Rules are applied in order.
                </p>

                <div className="mb-4">
                  <h6 className="text-xs font-bold text-on-surface dark:text-molten-text mb-2 uppercase tracking-wide">Rule Shape</h6>
                  <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`{
  "when": { "field": "callback_time", "truthy": true },
  "and_intent_in": ["", "Unknown", "Busy"],
  "set": { "intent_status": "Callback_Requested" }
}`}
                  </pre>
                </div>

                <div className="space-y-2">
                  <h6 className="text-xs font-bold text-on-surface dark:text-molten-text uppercase tracking-wide">Rule Fields</h6>
                  <ul className="space-y-2 text-xs">
                    {[
                      { key: 'when.field', desc: 'The extraction field to check (e.g. "callback_time", "site_visit_agreed")' },
                      { key: 'when.truthy', desc: 'If true, fires when field is non-empty/non-null. If false, fires when empty/null.' },
                      { key: 'when.eq', desc: 'Alternative to truthy \u2014 fires when field exactly equals this value.' },
                      { key: 'and_intent_in', desc: 'Optional guard \u2014 only fires if current intent_status is in this list. Use "" for empty/missing.' },
                      { key: 'set', desc: 'Key-value pairs to overwrite in extracted data. Use null to clear a field.' },
                    ].map((item) => (
                      <li key={item.key} className="flex items-start gap-2">
                        <code className="bg-black/10 dark:bg-white/10 px-1.5 py-0.5 rounded font-bold text-primary dark:text-molten-primary shrink-0">{item.key}</code>
                        <span className="text-on-surface-variant dark:text-molten-text-muted">{item.desc}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="mt-4">
                  <h6 className="text-xs font-bold text-on-surface dark:text-molten-text mb-2 uppercase tracking-wide">Common Patterns</h6>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                      { trigger: 'callback_time is non-empty', action: 'Set intent to Callback_Requested', guard: 'Only if intent is Unknown/Busy/empty' },
                      { trigger: 'site_visit_agreed is true', action: 'Set intent to Interested', guard: 'Only if intent is Unknown/empty' },
                      { trigger: 'bhk_preference is non-empty', action: 'Set intent to Interested', guard: 'Only if intent is Wrong_Requirement/Unknown' },
                      { trigger: 'location_preference is non-empty', action: 'Set intent to Interested', guard: 'Only if intent is Wrong_Requirement/Unknown' },
                    ].map((p, i) => (
                      <div key={i} className="bg-surface dark:bg-[#1C1810] rounded-lg p-3 border border-outline-variant/50 dark:border-[#2A345E]/50">
                        <p className="text-xs font-bold text-on-surface dark:text-molten-text">{p.trigger}</p>
                        <p className="text-xs text-emerald-600 dark:text-emerald-400">\u2192 {p.action}</p>
                        <p className="text-xs text-on-surface-variant dark:text-molten-text-muted italic">{p.guard}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Extraction schema hard constraints */}
              <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] p-5">
                <h5 className="font-bold text-sm mb-3 text-on-surface dark:text-molten-text">Extraction Schema Hard Constraints</h5>
                <ul className="space-y-2 text-xs">
                  {[
                    { rule: 'mode must be "both"', detail: 'Always generates both a summary paragraph and structured field extraction' },
                    { rule: 'intent_status field is mandatory', detail: 'Must be type "enum" with required: true and non-empty values array' },
                    { rule: 'Valid field types', detail: '"string", "enum", "boolean", "datetime"' },
                    { rule: 'Each field key must be unique', detail: 'No duplicate keys in the fields array' },
                    { rule: 'summary_prompt is required', detail: 'Must be present when mode is "both" \u2014 guides the LLM summarization' },
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="material-symbols-outlined text-[14px] mt-0.5 text-primary dark:text-molten-primary shrink-0">check_circle</span>
                      <div>
                        <span className="font-bold text-on-surface dark:text-molten-text">{item.rule}</span>
                        <span className="text-on-surface-variant dark:text-molten-text-muted ml-1">\u2014 {item.detail}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {activeTab === 'design' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg">
                <h4 className="text-lg font-bold text-primary dark:text-molten-primary mb-1 flex items-center gap-2">
                  <span className="material-symbols-outlined">forum</span>
                  Conversational Design Tips
                </h4>
                <p className="text-sm text-on-surface dark:text-molten-text">
                  Writing a conversational prompt is about directing a persona&#39;s <strong>emotional intelligence</strong> rather than hardcoding a rigid decision tree.
                </p>
              </div>

              {/* Core principles */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { title: 'One Question, One Breath', desc: 'Never ask two questions simultaneously. Humans answer only the last question heard. Stop completely after asking.', icon: 'mic' },
                  { title: 'Code-Switching is Natural', desc: 'Force "Hinglish" or "Marathlish". Pure textbook languages sound robotic. Mix English nouns into regional sentences.', icon: 'translate' },
                  { title: 'Listen First', desc: 'Validate the caller\'s input before pushing the next step. Acknowledgment builds trust.', icon: 'hearing' },
                  { title: 'Emotional Intelligence', desc: 'Map out reactions to caller tones: if stressed \u2192 soften; if excited \u2192 match energy; if annoyed \u2192 exit gracefully.', icon: 'psychology' },
                ].map(p => (
                  <div key={p.title} className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold mb-2 flex items-center gap-2">
                      <span className="material-symbols-outlined text-primary dark:text-molten-primary text-[18px]">{p.icon}</span>
                      {p.title}
                    </h5>
                    <p className="text-sm text-on-surface-variant dark:text-molten-text-muted">{p.desc}</p>
                  </div>
                ))}
              </div>

              {/* System instruction sections */}
              <section>
                <h4 className="text-lg font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  System Instruction Architecture
                </h4>
                <div className="space-y-3">
                  {[
                    { section: 'THE SCENE & PERSONA', color: 'blue', desc: 'Define mood, setting, and vocal delivery. Who is the agent?', example: '"Diya is in a warm, professional office. Tone: helpful advisor, zero pressure."' },
                    { section: 'EMOTIONAL INTELLIGENCE', color: 'purple', desc: 'Tell the model exactly how to react to specific caller energy.', example: 'Hesitation \u2192 "Do NOT push. Soften voice." Budget Worry \u2192 "Never quote price."' },
                    { section: 'CONVERSATIONAL RULES', color: 'green', desc: 'Numbered rules (Rule 1-5) from opening to closing pitch.', example: 'Rule 1: "Say exactly \'Hello... {lead_name} ji?\' and wait."' },
                    { section: 'GUARDRAILS', color: 'red', desc: 'Hard boundaries. Use "unmistakably" for critical ones.', example: '"Never fabricate facts." "One question at a time \u2014 unmistakably."' },
                    { section: 'CALL ENDING', color: 'amber', desc: 'Goodbye protocol + end_call tool invocation.', example: '"First speak goodbye warmly, then IMMEDIATELY call end_call once."' },
                  ].map(s => {
                    const c = colorMap[s.color] || colorMap.blue;
                    return (
                      <div key={s.section} className={`bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-l-4 ${c.border} border-outline-variant dark:border-[#2A345E]`}>
                        <h5 className={`font-bold text-sm ${c.text} mb-1`}>{s.section}</h5>
                        <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-2">{s.desc}</p>
                        <p className="text-xs font-mono bg-black/5 dark:bg-white/5 px-2 py-1 rounded">{s.example}</p>
                      </div>
                    );
                  })}
                </div>
              </section>

              {/* Bootstrap + Hangup */}
              <section>
                <h4 className="text-lg font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  Session Bootstrapping & Hangup
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold text-sm mb-2 flex items-center gap-2">
                      <span className="material-symbols-outlined text-emerald-500 text-[18px]">play_circle</span>
                      Bootstrap Messages
                    </h5>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">Synthetic first message injected on connect. Forces Gemini to speak immediately.</p>
                    <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`[{
  "role": "user",
  "content": "The call has just connected.
  {lead_name} answered. Execute Rule 1:
  say ONLY 'Hello... {lead_name} ji?'
  in a warm voice. Stop completely."
}]`}
                    </pre>
                  </div>
                  <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                    <h5 className="font-bold text-sm mb-2 flex items-center gap-2">
                      <span className="material-symbols-outlined text-rose-500 text-[18px]">call_end</span>
                      Goodbye Hangup Markers
                    </h5>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">Safety fallback \u2014 auto-hangup if bot forgets end_call tool.</p>
                    <div className="text-xs space-y-2">
                      <p className="font-bold">Rules:</p>
                      <ul className="list-disc pl-4 space-y-1 text-on-surface-variant dark:text-molten-text-muted">
                        <li>Use substrings, not full sentences</li>
                        <li>Add both Devanagari + romanized versions</li>
                        <li>Never add mid-conversation phrases</li>
                        <li>Cover all goodbye scenarios</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </section>

              {/* Template variables */}
              <section>
                <h4 className="text-lg font-bold mb-3 text-primary dark:text-molten-primary">Template Variables</h4>
                <div className="bg-surface-container-lowest dark:bg-[#141210] rounded-lg border border-outline-variant dark:border-[#2A345E] overflow-hidden">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="bg-surface dark:bg-[#1C1810] border-b border-outline-variant dark:border-[#2A345E]">
                        <th className="px-4 py-2 text-xs font-bold uppercase tracking-wide text-on-surface-variant dark:text-molten-text-muted">Variable</th>
                        <th className="px-4 py-2 text-xs font-bold uppercase tracking-wide text-on-surface-variant dark:text-molten-text-muted">Description</th>
                        <th className="px-4 py-2 text-xs font-bold uppercase tracking-wide text-on-surface-variant dark:text-molten-text-muted">Example</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      <tr className="border-b border-outline-variant/50 dark:border-[#2A345E]/50">
                        <td className="px-4 py-2 font-mono text-primary dark:text-molten-primary font-bold text-xs">{'{lead_name}'}</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">Caller&#39;s name</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">&quot;Rahul&quot;</td>
                      </tr>
                      <tr className="border-b border-outline-variant/50 dark:border-[#2A345E]/50">
                        <td className="px-4 py-2 font-mono text-primary dark:text-molten-primary font-bold text-xs">{'{lead_phone}'}</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">Caller&#39;s E.164 phone</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">&quot;+919876543210&quot;</td>
                      </tr>
                      <tr>
                        <td className="px-4 py-2 font-mono text-primary dark:text-molten-primary font-bold text-xs">{'{lead_city}'}</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">Caller&#39;s city</td>
                        <td className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted">&quot;Pune&quot;</td>
                      </tr>
                    </tbody>
                  </table>
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

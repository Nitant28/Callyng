# Cascade script — AI generation prompt

**How to use:** Copy everything below the line into ChatGPT / Claude / Cursor, then paste the campaign brief (product, language, persona, facts). Paste each numbered SECTION into the matching CMS field. Turn **Live tools** on. Turn **Transfer calling** on only if you have an E.164 desk number.

The same prompt is on **Copy for AI** in the admin Cascade Guide.

---

# ROLE
You generate paste-ready Aakashvani CMS fields for route=cascaded (STT→LLM→TTS on 8 kHz PSTN).
You are NOT writing a Python bot. You are NOT writing an STS/Gemini Live script.

The human message after this prompt is the campaign brief (product, language, persona, facts).
Use ONLY those facts in KNOWLEDGE BASE. Invent no prices, inventory, or company details.

# HARD RULES
1. Output exactly 8 sections with the headings below. Nothing before SECTION 1. Nothing after the checklist.
2. Each section body is copy-pasteable into the named CMS field. No markdown fences around SECTION 1 (plain text). JSON sections must be valid JSON only (no commentary inside the JSON).
3. Allowed live tools: ONLY `end_call`, `push_lead_data`, `transfer_call`. Never invent hangup, save_lead, transfer_to, dial, destination, phone.
4. `transfer_call` arguments: optional `reason` (string) ONLY. Forbidden keys: destination, number, to, phone, transfer_number.
5. `end_call` arguments: none (empty object / no args).
6. Never put `Transferred` in extraction `intent_status` or outcome_event_map. That outcome is set by the platform after transfer_call.
7. Always include the TOOLS block in SECTION 1 (gated by "only if listed in your tools"). Do not omit transfer protocol even if the brief does not mention transfer — operators enable it later in CMS.
8. Template variables allowed: {lead_name} {lead_phone} {lead_city} only.

# TOOL CONTRACT (must appear inside SECTION 1 as a heading "## TOOLS")

Copy this block into the system instruction. You may translate hold-lines and examples to the campaign language. Do not rename tools. Do not add tools. Do not change argument names.

## TOOLS
You may call a tool only if it is in your available tool list.

end_call — always available. No arguments.
  Speak the final goodbye first. Then call end_call exactly once.
  Never mid-call. Never before goodbye. Never twice.

push_lead_data — only if listed. Call exactly once on a NORMAL hangup (not after transfer).
  Then speak goodbye. Then end_call.
  Arguments (JSON):
  {
    "intent_status": "<Interested|Not_Interested|Busy|Callback_Requested|Wrong_Requirement|Unknown>",
    "bhk_preference": "<e.g. 2BHK> or \"NULL\"",
    "location_preference": "<area> or \"NULL\"",
    "callback_time": "<string or omit>",
    "language_used": "<Hindi|Marathi|English>"
  }
  Required: intent_status, bhk_preference, location_preference.
  Unknown collected fields MUST be the string NULL (not empty, not omit required keys).

transfer_call — only if listed. Cold-transfer to a human. Destination is NOT an argument.
  Optional: { "reason": "<short why>" }
  When the caller clearly asks for a human / executive / "transfer karo":
    1. Speak one hold line (do not say the destination number).
    2. Call transfer_call.
    3. Stop. Do not end_call. Do not push_lead_data after transfer.
  If transfer_call is NOT listed: offer a callback. Never pretend you transferred.

DECISION TABLE (use this, do not improvise):
| Situation | Speak | Then call |
|---|---|---|
| Caller wants a human AND transfer_call is listed | 1 hold sentence | transfer_call only |
| Normal end (done / not interested / busy after time taken) | — | push_lead_data (if listed), then goodbye, then end_call |
| transfer_call NOT listed but caller wants a human | offer callback, then goodbye | push_lead_data (if listed), then end_call |
| Ambiguous last turn / STT glitch | one clarifying question | no tool |

# OUTPUT — 8 SECTIONS

Use these headings exactly:

## SECTION 1 — system_instruction_template
(plain text)

Must contain, in this order:
AUDIO PROFILE; THE SCENE; DIRECTOR'S NOTES; AGENT PERSONA; LANGUAGE;
TOOLS (the contract above, translated hold-lines only);
CONVERSATIONAL STEPS (Step 1 = one Hindi/campaign-language question using {lead_name});
SPECIAL SITUATIONS (busy, not interested, human request, wrong requirement, trust, audio-once);
CALL ENDING (normal hangup order);
KNOWLEDGE BASE (brief facts only);
GUARDRAILS;
CALL METADATA (internal; do not read {lead_phone} / {lead_city} aloud).

## SECTION 2 — bootstrap_messages_json
JSON array only:
[{"role":"user","content":"The call has just connected. {lead_name} has answered. Execute Step 1: say ONLY the Step 1 opening sentence, addressing {lead_name} — then stop and wait. Do not say anything else."}]

## SECTION 3 — lead_schema
JSON object only. Default: {"fields":[]}. Add fields only if the brief needs extra CSV columns.

## SECTION 4 — extraction_schema
JSON object only. mode MUST be "both". Must include required enum field intent_status.
intent_status values MUST be a subset of:
Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown
NEVER include Transferred.
Include summary_prompt. Optional extra fields only if the brief needs them.

## SECTION 5 — outcome_event_map
JSON object only. Keys = intent_status values that should fire a webhook. Do not map Transferred.
Use {} if none.

## SECTION 6 — normalization_rules
JSON array only. Use [] unless the brief needs deterministic corrections.

## SECTION 7 — goodbye_markers
JSON array of short substrings (Devanagari AND romanized). Terminal goodbyes only. Do not include transfer hold-lines.

## SECTION 8 — cascade_live_tools
JSON array only. Paste into Advanced → Call actions → Live tools.
Unless the brief defines extra log-only tools, output EXACTLY this (do not rename keys):

```json
[
  {
    "name": "push_lead_data",
    "description": "Call this before ending every call to save lead qualification data. Always call this regardless of outcome. Do not call after transfer_call.",
    "properties": {
      "intent_status": {
        "type": "string",
        "description": "Call outcome: Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown"
      },
      "bhk_preference": {
        "type": "string",
        "description": "BHK preference, or the string NULL if not collected"
      },
      "location_preference": {
        "type": "string",
        "description": "Preferred location, or the string NULL if not collected"
      },
      "callback_time": {
        "type": "string",
        "nullable": true,
        "description": "Requested callback time if busy; omit or null if none"
      },
      "language_used": {
        "type": "string",
        "description": "Language used in call: Hindi, Marathi, English"
      }
    },
    "required": ["intent_status", "bhk_preference", "location_preference"]
  }
]
```

Do NOT put end_call or transfer_call in this JSON. Those are registered by the platform, not this array.

# OPERATOR NOTE (do not output this as a CMS field)
After paste: turn Live tools ON. Turn Transfer calling ON only when an E.164 desk number exists.
Save fails if Live tools is on and this JSON is empty, or Transfer is on and the number is invalid.

# SELF-CHECK (print as a final bullet list, not a CMS field)
- [ ] 8 sections, exact headings
- [ ] SECTION 1 contains ## TOOLS with end_call, push_lead_data, transfer_call and the decision table
- [ ] No invented tool names or transfer destination args
- [ ] extraction intent_status has no Transferred
- [ ] SECTION 8 is valid JSON and only push_lead_data (unless brief explicitly added another named tool)

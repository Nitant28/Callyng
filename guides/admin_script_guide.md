# Admin Script Configuration Guide

## 1. Overview
A `script_config` defines everything about how an AI bot behaves on a call—from the underlying language models, VAD settings, and voice providers, to the exact instructions, dynamic extraction schema, and post-call routing rules. Every `bot_config` links to a specific `script_config`. When a campaign runs, it uses the script configuration to instruct the dialer and manage post-call data extraction.

## 2. API Endpoints
The following internal endpoints are available to admins (all require `Authorization: Bearer <admin_secret>`):

| Endpoint | Method | Purpose |
|---|---|---|
| `/internal/script-configs/template?route=sts\|cascaded` | GET | Returns a complete, create-ready template payload for the specified route. |
| `/internal/script-configs?client_id={uuid}&active_only={bool}` | GET | Lists configurations (filters out CLI sandbox rows). |
| `/internal/script-configs/{id}?client_id={uuid}` | GET | Fetches a single configuration. |
| `/internal/script-configs` | POST | Creates a new configuration and its first revision. |
| `/internal/script-configs/{id}?client_id={uuid}` | PATCH | Partially updates a configuration and creates a new revision. |
| `/internal/script-configs/{id}/revisions?client_id={uuid}` | GET | Lists up to the last 5 revisions of a configuration. |
| `/internal/script-configs/{id}/rollback?client_id={uuid}` | POST | Rolls back the configuration to a specific `version`. |
| `/internal/script-configs/{id}/test` | POST | Dry-runs the post-call extraction engine with a provided mock transcript. |
| `/internal/script-configs/{id}/dial-test` | POST | Initiates a live dialer test call to a specified phone number using a synthetic campaign. |

## 3. Field Reference
Every `script_config` contains over 30 configurable fields.

### Identity
- `script_id` (string): Unique identifier. Must match `^[a-z][a-z0-9_]*$`.
- `route` (string): Either `"sts"` (Speech-to-Speech via Gemini Live) or `"cascaded"` (STT → LLM → TTS).
- `active` (boolean): Whether this configuration is available for new campaigns.

### Gemini Live & Voice
- `gemini_model` (string): The Gemini model path (e.g., `"models/gemini-3.1-flash-live-preview"`).
- `gemini_voice` (string): The selected voice (e.g., `"Aoede"`).
- `gemini_language` (string): The BCP47 language code (e.g., `"hi-IN"`).
- `gemini_temperature` (float): The LLM temperature (e.g., `0.5`).

### VAD (Voice Activity Detection)
- `vad_start_sensitivity` (string): `"HIGH"` or `"LOW"`.
- `vad_end_sensitivity` (string): `"HIGH"` or `"LOW"`.
- `vad_silence_duration_ms` (integer): Milliseconds of silence to trigger turn completion (default: `800`).
- `vad_prefix_padding_ms` (integer): Milliseconds to pad the start of audio (default: `300`).

### System Prompts
- `system_instruction_template` (string): The main prompt. Supports `{lead_name}`, `{lead_phone}`, and `{lead_city}` substitution.
- `bootstrap_messages_json` (list): Optional JSON array of messages to preload into the conversation history.
- `goodbye_markers` (list): Phrases that indicate the AI has ended the call.

### Cascade Pipeline (For `route="cascaded"`)
- `cascade_stt_provider` / `cascade_stt_model` (string): STT settings (e.g., `"sarvam"`, `"saarika:v2.5"`).
- `cascade_llm_provider` / `cascade_llm_model` (string): Core LLM settings (e.g., `"groq"`, `"llama-3.3-70b-versatile"`).
- `cascade_tts_provider` / `cascade_tts_voice` (string): TTS settings (e.g., `"cartesia"`, `"sonic-3"`).
- `cascade_live_tools` (list): JSON array of tool definitions injected into the cascade context (see Section 7).

### Post-Call Data & Flow
- `extraction_schema` (dict): Defines what structured data the post-call extractor pulls from the transcript (see Section 4).
- `normalization_rules` (list): Declarative rules to correct/patch extraction outputs (see Section 5).
- `outcome_terminal` / `outcome_retry` / `outcome_callback` (list): Buckets defining the state-machine transition for each `intent_status` (see Section 6).
- `outcome_event_map` (dict): Maps specific `intent_status` values to webhook events.
- `lead_schema` (dict): Extensible schema tracking the expected fields for a lead.

## 4. `extraction_schema` Deep Dive
The extraction schema instructs the post-call LLM (usually Groq) on how to parse the transcript.

### Modes
- `"fields"`: Only extracts specific predefined JSON fields.
- `"summary"`: Only writes a free-form paragraph summary.
- `"both"`: Extracts both structured fields and a conversational summary.

### Example Schema (Pyramid Both Mode)
```json
{
  "mode": "both",
  "summary_prompt": "Provide a 2-3 sentence summary covering intent, budget, and site visits.",
  "extraction_rules": "Trust the assistant's confirmation if user audio is garbled.",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "required": true,
      "values": ["Interested", "Not_Interested", "Busy", "Callback_Requested", "Wrong_Requirement", "Unknown"]
    },
    {
      "key": "bhk_preference",
      "type": "string",
      "required": false
    },
    {
      "key": "site_visit_agreed",
      "type": "boolean",
      "required": false
    }
  ]
}
```
**Supported field types**: `"string"`, `"enum"`, `"boolean"`, `"datetime"`. All enum fields must define a `values` array.

## 5. `normalization_rules` Deep Dive
Normalization rules allow you to declaratively patch logical inconsistencies in the extracted JSON before it hits the state machine.

**IMPORTANT FALLBACK BEHAVIOR:** If `normalization_rules` is empty (`[]`), the system runs a generic fallback that infers callbacks and site visits. If `normalization_rules` is **non-empty**, that generic fallback **is completely skipped**. Your explicit config takes total control.

### Rule Syntax
```json
{
  "when": {"field": "callback_time", "truthy": true},
  "and_intent_in": ["", "Unknown", "Busy", "Wrong_Requirement"],
  "set": {"intent_status": "Callback_Requested"}
}
```
- `when.field`: The field to check.
- `when.truthy`: Evaluates true if the field is present and non-empty (supports string representations of truth).
- `when.eq`: Checks exact equality.
- `and_intent_in`: (Optional) Only apply this rule if the current `intent_status` is in this list.
- `set`: The dictionary of fields to overwrite/patch if the rule matches.

### Full Pyramid Normalization Example
```json
[
  {
    "when": {"field": "callback_time", "truthy": true},
    "and_intent_in": ["", "Unknown", "Busy", "Wrong_Requirement"],
    "set": {"intent_status": "Callback_Requested"}
  },
  {
    "when": {"field": "bhk_preference", "truthy": true},
    "and_intent_in": ["Wrong_Requirement", "Unknown", ""],
    "set": {"intent_status": "Interested", "caller_notes": null}
  },
  {
    "when": {"field": "location_preference", "truthy": true},
    "and_intent_in": ["Wrong_Requirement", "Unknown", ""],
    "set": {"intent_status": "Interested", "caller_notes": null}
  },
  {
    "when": {"field": "site_visit_agreed", "truthy": true},
    "and_intent_in": ["", "Unknown"],
    "set": {"intent_status": "Interested"}
  }
]
```

## 6. Outcome Bucket Mapping
Every value listed in the `intent_status` enum must be mapped to exactly **one** of three state-machine buckets.

- `outcome_terminal`: Lead is marked `completed` (e.g., `["Interested", "Not_Interested"]`).
- `outcome_retry`: Outcomes in this bucket route to **`callback_scheduled`** status (purple card) with `retry_delay_minutes` — e.g. `["Busy", "Unknown", "Wrong_Requirement", "No_Answer", ...]`. If max attempts are reached, status becomes `failed`.
- `outcome_callback`: Lead is marked `callback_scheduled` (e.g., `["Callback_Requested", "Early_Disconnect"]`).

The API strictly validates that no `intent_status` values are missing or duplicated across buckets.

## 7. `cascade_live_tools`
For `cascaded` route bots, you can inject tools that the LLM can call mid-conversation (e.g., to save lead data before ending the call).

### Example
```json
[
  {
    "name": "push_lead_data",
    "description": "Call this before ending every call to save lead qualification data.",
    "properties": {
      "intent_status": { "type": "string", "description": "Yes, No, Busy, Callback, Unclear" },
      "bhk_preference": { "type": "string", "description": "2BHK, 3BHK, NULL" }
    },
    "required": ["intent_status", "bhk_preference"]
  }
]
```

## 8. Creating a New Bot Script
1. Create a script module in `sts_scripts/` (for STS) or `cascade_scripts/` (for cascade).
2. Define the required attributes:
   - STS: `GEMINI_MODEL`, `EXTRACTION_SCHEMA`, etc.
   - Cascade: `SYSTEM_PROMPT_TEMPLATE`, `EXTRACTION_SCHEMA`, `CASCADE_LIVE_TOOLS`.
3. If defining domain-specific logic, define `normalization_rules` locally.
4. Export the script using `script_module_export.py` → `export_module(route, module_stem)`.
5. Register it into the database via `POST /internal/script-configs` (or via the Admin UI).
6. Create a `bot_config` that links to this new script configuration.

## 9. Post-Call Flow Summary
How all these fields come together after a call ends:
1. **Transcription**: Call completes and the transcript is saved.
2. **Extraction**: `extract_post_call()` queries the Groq LLM using your `extraction_schema` and `extraction_rules`.
3. **Normalization**: `normalize_post_call_extraction()` patches the resulting JSON by executing your `normalization_rules` sequentially.
4. **Transition**: `resolve_post_call_transition()` checks which bucket (`terminal`, `retry`, `callback`) the resulting `intent_status` falls into, and updates the `leads` table accordingly.
5. **Webhooks**: If the `intent_status` matches a key in your `outcome_event_map`, the system fires the corresponding webhook event.

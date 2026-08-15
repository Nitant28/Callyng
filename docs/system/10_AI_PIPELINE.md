# 10 — AI Pipeline

---

## Routes

| Route | Module | Stack | When |
|-------|--------|-------|------|
| `sts` | `bot_sts.py` | Google Gemini Live (STT+LLM+TTS unified) | default `BOT_ROUTE` |
| `cascaded` | `bot_cascade.py` | Sarvam STT + Groq LLM + Cartesia TTS | per bot_config |

Per-call route resolved in `server._resolve_bot` from `body._pg.route` or module default.

---

## Script resolution (3 tiers) — `script_runtime.py`

1. **Prefetched `script_config`** — dialer renders DB config with lead template vars,
   stores in Redis; `/ws` pops as `_prefetched_config`. Highest priority.
2. **`_pg.script_id`** — `importlib` loads `sts_scripts.<id>` or `cascade_scripts.<id>`.
3. **Env default** — `STS_SCRIPT` / `CASCADE_SCRIPT`.

`build_post_call_snapshot` written to `call_logs.call_data` at call start for
extraction/normalization/outcome buckets during post-call.

---

## STS scripts (`sts_scripts/`)

Each module defines (verified `pyramid_mr.py` pattern + `bot_template.py`):
- `GEMINI_MODEL`, `GEMINI_VOICE`, `GEMINI_LANGUAGE`, `GEMINI_VAD` settings
- `SYSTEM_INSTRUCTION` / persona text with `{lead_name}` placeholders
- `EXTRACTION_SCHEMA` (or imports from `pyramid_extraction.py`)
- `LEAD_SCHEMA` for CSV validation
- `GOODBYE_MARKERS` for hangup fallback

Shared extraction: `pyramid_extraction.py` — `PYRAMID_EXTRACTION_SCHEMA`,
`PYRAMID_NORMALIZATION_RULES`, `PYRAMID_CASCADE_LIVE_TOOLS`.

---

## Dynamic script configs (`script_configs` table)

Admin-managed via `/internal/script-configs`. Fields include:
- Gemini model/voice/language/temperature/VAD
- `system_instruction_template` (safe `string.Template`)
- `bootstrap_messages_json`, `goodbye_markers`
- Cascade provider/model overrides
- `extraction_schema`, `lead_schema`
- `normalization_rules`, `outcome_terminal/retry/callback`, `outcome_event_map`

Rendered per call by `script_prefetch.render_script_config` substituting lead fields.

---

## Prompt construction

- **Lead context:** `LeadContext.from_body(body)` → `lead_name`, `lead_phone`, `lead_city`.
- **Template vars:** lead `metadata` keys + core lead fields injected via
  `string.Template` (NOT `.format(**metadata)` — injection-safe, per schema comment).
- **Bootstrap:** `bootstrap_messages_json` seeds initial LLM context turns.
- **Live tools (STS):** `end_call` tool (`call_limits.end_call_function_schema`).
- **Live tools (cascade):** `cascade_live_tools` e.g. `push_lead_data` (Pyramid).

---

## Runtime (STS call) — `bot_sts.run_bot`

```
resolve_sts_runtime(body) → StsRuntime
GeminiLiveLLMService(system_instruction, tools, settings)
Pipeline: transport.in → user_aggregator → llm → transport.out → end_gate → usage_tap → assistant_aggregator
TranscriptBuffer registered on aggregators
attach_pipeline_finalize → on end: extract + process_post_call
schedule_max_call_duration + end_call handler + goodbye fallback
```

Context window compression: `GEMINI_CONTEXT_COMPRESSION`, `GEMINI_CWC_TRIGGER_TOKENS`.

---

## Memory

- **In-call:** Pipecat `LLMContext` + Gemini context window compression (sliding window).
- **Cross-call:** none. Each attempt is stateless except lead `metadata`/`extraction`
  on the lead row.
- **Redis pgctx:** ephemeral per `session_call_id` for post-call correlation.

---

## Extraction — `post_call_extract.py`

1. Transcript formatted for LLM (merge consecutive same-role turns, filter ultra-short).
2. System prompt from `build_extraction_system_prompt(extraction_schema)`.
3. Groq chat completion (`POST_CALL_MODEL`, default `llama-3.3-70b-versatile`).
4. Parse JSON (handles markdown fences).
5. `normalize_post_call_extraction` applies declarative rules from script config
   or `PYRAMID_NORMALIZATION_RULES`.
6. `intent_status` becomes the canonical outcome.

---

## Outcome classification — `post_call_processor`

Buckets from script snapshot or defaults:
- **terminal:** `Interested`, `Not_Interested` → lead `completed`
- **callback:** `Callback_Requested`, `Early_Disconnect` → `callback_scheduled`
- **retry:** `Busy`, `Unknown`, `Wrong_Requirement` → retry or fail by attempts

`apply_early_disconnect_policy`: callee hangup <30s + weak intent → `Early_Disconnect`.

Webhook mapping: `n8n_webhook.outcome_to_event` + optional `outcome_event_map` override.

---

## Language handling

- STS: `gemini_language` per script (e.g. `mr-IN`, `hi-IN`); Pipecat maps via
  `language_to_gemini_language`.
- Cascade: Sarvam STT language from script config.
- Extraction schema includes `language_used` enum field (Pyramid).
- Post-call extraction is text-based (Groq) — works across Hindi/Marathi/English
  in transcript.

---

## Script loading at dial time

```
concurrent_dialer.fire_call
  → build _pg context (client, campaign, lead, bot_config ids, route, script_id, schemas)
  → script_prefetch.prefetch_for_call(call_id, lead, bot, script_config?)
  → body_data embedded in Plivo answer URL → /ws
```

---

## Cost tracking

- STS: `pricing_sts.compute_sts_cost_inr` from Gemini token usage (internal; stored
  `cost_usd` on call_log — **not shown to client**).
- Client billing: `credits_charged` only (setup + pro-rata minutes × `credits_per_minute`).

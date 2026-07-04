# 18 — Code Index

One paragraph per important file. Root = `aakashvani/`.

---

## Entry & server

**`server.py`** — FastAPI application entry: lifespan (Postgres, Redis, SQLite,
stale-sweep, campaign auto-resume), CORS, slowapi rate limiting, telephony
endpoints (`/start`, `/answer`, `/ws`, Plivo webhooks), Gemini prewarm, bot
dispatch, and API router registration.

**`background_tasks.py`** — Registry of fire-and-forget asyncio tasks with strong
references so post-call work isn't garbage-collected; drained on shutdown.

---

## Voice bots

**`bot_sts.py`** — Pipecat pipeline for Gemini Live (speech-to-speech): builds
`GeminiLiveLLMService`, transcript buffer, usage metrics, call limits, and
attaches post-call finalization on pipeline end.

**`bot_cascade.py`** — Pipecat pipeline chaining Sarvam STT, Groq LLM, and
Cartesia TTS for the cascaded route; same transcript/post-call hooks as STS.

**`bot.py`** — Local dev runner harness for Pipecat (not production path).

---

## Call pipeline

**`call_transcript.py`** — Captures live transcript turns, stores pg context in
Redis, finalizes pipeline output, triggers Groq extraction and
`process_post_call`, and writes parallel SQLite logs.

**`post_call_processor.py`** — Authoritative post-call state machine: maps
extraction outcomes to lead status transitions, computes ceiling billing, settles
campaign budget reservations, increments counters, and fires n8n webhooks.

**`post_call_extract.py`** — Formats transcript for Groq, runs structured
extraction against `extraction_schema`, parses JSON, and applies declarative
normalization rules.

**`call_outcomes.py`** — Canonical outcome constants and Plivo hangup status
mapping; defines TERMINAL/RETRY/CALLBACK sets used by post-call logic.

**`call_limits.py`** — Max call duration watchdog, `end_call` LLM tool schema,
goodbye-phrase hangup fallback, and speech-end gating for graceful hangup.

**`call_metrics.py`** — Pipecat `MetricsFrame` tap accumulating LLM token and
TTS character usage per call.

**`pricing_sts.py`** — Approximate Gemini Live INR cost from token counts and env
USD/INR rates (internal analytics).

**`lead_context.py`** — Small dataclass extracting `lead_name`, `lead_phone`,
`lead_city` from telephony body payloads for prompt injection.

---

## Script system

**`script_runtime.py`** — Resolves STS/cascade runtime configs from prefetched DB
configs, Python script modules, or env defaults; builds post-call snapshots and
outcome bucket sets.

**`script_prefetch.py`** — Renders `script_configs` with lead template
substitution, caches in Redis for the `/ws` hot path, and sweeps stale entries.

**`sts_scripts/pyramid_extraction.py`** — Shared Pyramid real-estate extraction
schema, normalization rules, and cascade live-tool definitions for Hindi/Marathi bots.

**`sts_scripts/pyramid_{mr,hi,bilingual}.py`** — Language-specific Gemini Live
personas for Pyramid Parkland Nxt campaigns.

**`sts_scripts/bot_template.py`** — Skeleton for new STS script modules.

**`cascade_scripts/prowave.py`** — Cascade-route persona script.

---

## Telephony & webhooks

**`telephony.py`** — Plivo REST client helpers: place outbound calls, fetch cash
credits balance, build public callback URLs from ngrok/host headers.

**`plivo_hangup.py`** — Handles Plivo hangup webhooks: records hangup metadata,
settles unanswered calls, applies callee-hangup callback policy, triggers
abandoned-session recovery.

**`recording.py`** — Starts Plivo call recording, handles recording webhook,
stores `plivo:`/`local:`/`r2` keys on call_logs, resolves playable URLs.

**`n8n_webhook.py`** — HMAC-signed outbound POSTs to per-client n8n workflows;
maps outcomes to events (`lead_qualified`, etc.) and sends campaign-completed
notifications.

**`compliance.py`** — TRAI outbound window check (9am–9pm IST) and
`next_compliant_time` calculator used by dialer and lead upload.

**`call_log_db.py`** — SQLite parallel transcript/usage log (Phase 0 artifact);
still written on every call.

---

## API layer

**`api/auth.py`** — `require_admin` and `get_client_from_token` FastAPI
dependencies; SHA-256 API key lookup; pool accessor with 503 on missing DB.

**`api/guards.py`** — `require_campaign_modifiable` and `require_lead_editable`
409 guards for mutating routes.

**`api/script_config_validation.py`** — Validates/normalizes script_config payloads
and provides `default_template(route)` for the admin CMS.

**`api/routes/internal.py`** — Admin `/internal/*` routes: clients, credits,
bots, campaigns, calls, stats, health, webhooks, reconcile.

**`api/routes/internal_script_configs.py`** — Admin script-config CMS: CRUD,
revisions, rollback, template, dial-test, extraction test.

**`api/routes/campaigns.py`** — Client campaign management: list/create/patch,
lead upload, start/stop/cancel, release-stuck, stats.

**`api/routes/leads.py`** — Client lead CRUD, manual status transitions with
enforced transition table.

**`api/routes/calls.py`** — Client call log list/detail and recording stream proxy.

**`api/routes/credits.py`** — Client credit balance endpoint (also login validation).

---

## Data layer

**`db/postgres.py`** — All multi-tenant PostgreSQL access (~3150 lines): pool
management, clients, credits, bots, campaigns, leads, call_logs, script_configs,
dialer claim/settle, counters, budget, webhooks.

**`db/redis_client.py`** — Async Redis pool init/get/close and URL helper for
slowapi.

**`db/warmup_state.py`** — Redis-backed Gemini prewarm pending/ready signaling per
call_id.

**`db/schema/*.sql`** — Raw DDL for initial schema and incremental compat layers.

---

## Dialer

**`dialer/concurrent_dialer.py`** — Per-campaign asyncio dialer loop: claim leads,
budget/balance/compliance guards, fire Plivo calls, track tasks in app.state.

**`dialer/dialer_lock.py`** — Redis distributed lock ensuring one dialer worker
per campaign.

**`dialer/cost_guard.py`** — Pauses dialing when campaign remaining budget falls
below minimum threshold.

**`dialer/plivo_balance.py`** — Cached Plivo account USD balance guard.

**`dialer/maintenance.py`** — Stale `in_progress` call_log sweeper loop.

---

## Lead upload

**`lead_upload/parser.py`** — CSV/XLSX parsing via pandas.

**`lead_upload/validator.py`** — Validates uploaded rows against `lead_schema`.

**`lead_upload/normaliser.py`** — Phone number normalization to E.164.

---

## Frontend (reference implementation)

**`frontend/src/App.jsx`** — React Router setup for client `/app/*` and admin
`/admin/*` routes with auth guards and layout wrappers.

**`frontend/src/api/client.js`** — Axios client with Bearer auth interceptor and
401 redirect.

**`frontend/src/api/admin.js`** — Axios admin client with `X-Admin-Key` and
`/admin→/internal` path rewrite.

**`frontend/src/contexts/AdminAuthContext.jsx`** — Admin key state + logout callback
registration.

**`frontend/src/contexts/AdminDataContext.jsx`** — Cached clients and bot_configs
maps for admin UI.

**`frontend/src/pages/client/*`** — Client Dashboard, CampaignDetail, CallLogs,
Login, Settings.

**`frontend/src/pages/admin/*`** — Full admin console pages.

**`frontend/src/components/shared/CallTranscriptDrawer.jsx`** — Call detail drawer
with live polling and recording playback.

---

## Migrations & ops

**`alembic/versions/*.py`** — Versioned schema migrations 001–010.

**`scripts/start-local.ps1`** — Windows one-command local stack bootstrap
(verified referenced in RUN_LOCAL.md).

**`tests/conftest.py`** — Pytest session fixtures: real DB/Redis pools, TRAI
mock, seed cleanup.

**`tests/test_*.py`** — Integration and unit tests per subsystem (see
`16_TESTING_GUIDE.md`).

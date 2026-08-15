# 02 — Folder Explanation

Every folder is described with: **why it exists**, **entry points**, and **how
it communicates** with the rest of the system. Root = `aakashvani/`.

---

## Root-level modules (not a folder, but the core)

These top-level `.py` files are the backend brain. They are imported directly
(flat module namespace; `tests/conftest.py` inserts repo root on `sys.path`).

| File | Why it exists | Entry point? |
|------|---------------|--------------|
| `server.py` | FastAPI app: lifespan, middleware, telephony webhooks, `/ws`, router registration, dialer auto-resume | **YES** — `uvicorn server:app` / `python server.py` |
| `bot.py` | Local dev bot runner (Pipecat runner harness) | dev only |
| `bot_sts.py` | STS (Gemini Live) Pipecat pipeline; `bot(runner_args)` is the WS entry | invoked by `/ws` |
| `bot_cascade.py` | Cascaded (Sarvam STT + Groq LLM + Cartesia TTS) pipeline | invoked by `/ws` |
| `call_transcript.py` | Captures live transcript, finalizes pipeline, dispatches post-call | called by bots |
| `post_call_processor.py` | Lead state machine, billing, counters, settlement, webhook | called by `call_transcript` |
| `post_call_extract.py` | Groq extraction + declarative normalization | called by `call_transcript` |
| `call_outcomes.py` | Canonical outcome vocabulary + Plivo→outcome mapping | imported widely |
| `script_runtime.py` | 3-tier script resolution; builds runtime dataclasses | called by bots |
| `script_prefetch.py` | Renders+caches script_config in Redis per call | called by dialer & `/ws` |
| `lead_context.py` | `LeadContext` dataclass (lead_name/phone/city) | called by bots/dialer |
| `call_limits.py` | Max-call watchdog, `end_call` tool schema, goodbye-hangup fallback | called by bots |
| `call_metrics.py` | Pipecat usage-metrics tap/accumulator | called by bots |
| `pricing_sts.py` | Gemini Live approximate INR cost | called by `call_transcript` |
| `compliance.py` | TRAI 9am–9pm IST window check | called by dialer + lead/campaign routes |
| `telephony.py` | Plivo Call API, cash-credit fetch, public URL builders | called by dialer |
| `plivo_hangup.py` | `/plivo-hangup` webhook logic | called by `server.py` |
| `recording.py` | Plivo recording start + `/plivo-recording` webhook + R2 helpers | called by `server.py` |
| `n8n_webhook.py` | Signed outbound webhooks + outcome→event map | called by post-call |
| `call_log_db.py` | SQLite transcript log (Phase 0, parallel to Postgres) | called by `call_transcript` |
| `background_tasks.py` | Strong-ref registry for fire-and-forget tasks (graceful shutdown) | imported widely |

**How they communicate:** synchronous Python imports + shared `app.state`
(pool, redis, dialer_tasks, session, background_tasks). Cross-request state
(prewarm, locks, prefetch, pg-context) flows through **Redis**, not memory,
because the dialer task and the `/ws` handler are different async contexts.

---

## `api/` — HTTP API layer

**Why:** isolates request/response, auth, validation, and guards from business
logic and persistence. Routers are mounted by `server._register_api_routes()`.

- `api/auth.py` — `require_admin` (checks `X-Admin-Key` == `ADMIN_API_KEY`),
  `get_client_from_token` (validates Bearer key → client row), `_pool_from_request`.
- `api/guards.py` — `require_campaign_modifiable` (409 unless draft/paused),
  `require_lead_editable` (409 if lead is `calling`).
- `api/script_config_validation.py` — validates/normalizes script_config payloads,
  `default_template(route)`.
- `api/routes/`:
  - `internal.py` — admin API (`/internal/*`): clients, credits, bot_configs,
    campaigns, webhooks, calls, stats, health, reconcile, release-stuck.
  - `internal_script_configs.py` — admin script-config CMS (`/internal/script-configs/*`).
  - `campaigns.py` — client campaign + lead-upload API (`/api/campaigns/*`).
  - `leads.py` — client lead CRUD (`/api/campaigns/{id}/leads/*`).
  - `calls.py` — client call logs + recordings (`/api/calls/*`).
  - `credits.py` — client credit balance (`/api/credits`).

**Communicates with:** `db/postgres.py` (all persistence), `dialer/` (start/stop
loops), `compliance.py`, `lead_upload/`, Redis (via `db/redis_client.py`).

---

## `db/` — persistence layer

**Why:** single place for connection pooling and all SQL. Routes never write raw
SQL except through these helpers (with minor exceptions inside route files that
acquire `pool` directly for stats).

- `db/postgres.py` — the largest module: `init_pool`/`close_pool`, JSONB codec,
  `record_to_dict`, and **all** multi-tenant CRUD + business queries (clients,
  credits ledger, bot_configs, campaigns, leads, call_logs, script_configs,
  dialer claim/settle, counters, budget settlement).
- `db/redis_client.py` — `init_redis`/`get_redis`/`close_redis`.
- `db/warmup_state.py` — Gemini prewarm signaling keyed by call_id.
- `db/schema/*.sql` — raw DDL (001 initial … 006 script_configs) applied via
  alembic `op.execute(open(...).read())`.

**Communicates with:** PostgreSQL, Redis. Imported by `api/`, `dialer/`, bots,
post-call modules, `server.py`.

---

## `dialer/` — outbound dialing engine

**Why:** orchestrates concurrent outbound calls per campaign with budget,
balance, compliance, and concurrency limits.

- `concurrent_dialer.py` — `run_campaign_dialer(campaign_id)`: the asyncio loop
  that claims leads (`claim_leads_for_dialer`, `FOR UPDATE SKIP LOCKED`), checks
  guards, fires Plivo calls, respects `max_concurrent_calls`. `start_campaign`/
  `stop_campaign` register tasks in `app.state.dialer_tasks`.
- `dialer_lock.py` — Redis lock (`dialer_lock:<campaign_id>`) so only one worker
  dials a campaign.
- `cost_guard.py` — `check_campaign_budget` (remaining ≥ this campaign's reservation).
- `plivo_balance.py` — cached Plivo cash-credit guard (`PLIVO_MIN_BALANCE_USD`).
- `maintenance.py` — `stale_call_log_loop` finalizes orphaned `in_progress` logs.

**Communicates with:** `telephony.py` (fire call), `db/postgres.py` (claim/settle),
`script_prefetch.py` (render config), Redis (lock), `compliance.py`.

---

## `lead_upload/` — CSV/XLSX ingestion

**Why:** parse, validate and normalize uploaded lead files before bulk insert.

- `parser.py` — read CSV/XLSX (pandas) into rows.
- `validator.py` — validate against the bot's `lead_schema` (required fields,
  types).
- `normaliser.py` — phone normalization (E.164 / Indian 10-digit), trimming.

**Communicates with:** `api/routes/campaigns.py` (`upload_leads`), `db/postgres.py`
(`bulk_insert_leads`). **Not verified in full from source** in this pass for
exact function signatures — see `api/routes/campaigns.py` upload handler for the
authoritative call sequence.

---

## `sts_scripts/` — Gemini Live (STS) personas

**Why:** static, code-defined bot personas + extraction schema for the STS route.

- `bot_template.py` — template/skeleton for a new STS script.
- `pyramid_hi.py`, `pyramid_mr.py`, `pyramid_bilingual.py` — Pyramid Parkland Nxt
  (real-estate) personas in Hindi / Marathi / bilingual.
- `pyramid_extraction.py` — shared `PYRAMID_EXTRACTION_SCHEMA`,
  `PYRAMID_NORMALIZATION_RULES`, cascade live tool defs.
- `lead_schema_pyramid.py` — lead CSV schema for Pyramid campaigns.

A script module exposes the persona/system instruction, Gemini settings, and an
`EXTRACTION_SCHEMA`. Resolved by `script_runtime.resolve_sts_runtime`.

---

## `cascade_scripts/` — cascaded pipeline personas

**Why:** personas for the STT+LLM+TTS cascade route.

- `prowave.py` — the cascade persona/script.

Resolved by `script_runtime.resolve_cascade_runtime`.

---

## `alembic/` — migrations

**Why:** versioned schema evolution. `alembic/versions/001…010`:
- 001 initial schema, 002 compat columns, 003 campaign settlement,
  004 max_call_minutes, 005 credit ledger, 006 script_configs (these wrap the
  raw `db/schema/*.sql`), 007 remove DNC + recompute counters,
  008 pyramid normalization rules backfill, 009 call_log indexes,
  010 early-disconnect outcome + check-constraint update.

Run with `alembic upgrade head` (config `alembic.ini`).

---

## `scripts/` — operational CLI scripts

**Why:** one-off/ops tooling (seeding, backfills, manual dial tests). Entry
points are run manually with `uv run python scripts/<name>.py`.
**Not verified per-file** in this pass — inspect individually before relying on.

---

## `tests/` — pytest suite

**Why:** integration tests against a real Postgres+Redis using FastAPI
`ASGITransport`. `conftest.py` initializes pools, seeds, and cleans up
non-seed rows after the session; `mock_is_call_allowed` patches the compliance
gate so tests aren't time-dependent. See `16_TESTING_GUIDE.md`.

---

## `frontend/` — React SPA

**Why:** the existing client + admin UI (being rebuilt; this is the reference).

```
frontend/src/
├── App.jsx                # routes + providers (ToastProvider > AdminAuthProvider > AdminDataProvider)
├── main.jsx               # ReactDOM root
├── api/
│   ├── client.js          # axios instance, Bearer auth, 401/403 → /login
│   └── admin.js           # axios instance, X-Admin-Key, /admin→/internal rewrite, apiFetch helper
├── contexts/
│   ├── ToastContext.jsx
│   ├── AdminAuthContext.jsx   # admin key in localStorage
│   └── AdminDataContext.jsx   # clients + bot_configs cache/maps
├── hooks/                 # useTheme, etc.
├── components/shared/     # ui/, Guards.jsx, CallTranscriptDrawer.jsx, CanvasBackground, layouts
└── pages/
    ├── client/            # Login, Dashboard, CampaignDetail, CallLogs, Settings
    └── admin/             # AdminLogin, AdminOverview, AdminClients, AdminClientDetail,
                           # AdminBotConfigs, AdminScriptConfigs, AdminCampaigns,
                           # AdminCalls, AdminDiagnostics, AdminWebhooks
```

**Communicates with backend** only through `api/client.js` (`VITE_API_BASE_URL`,
Bearer) and `api/admin.js` (`X-Admin-Key`, path rewrite). Routing guards
(`Guards.jsx`) gate `/app/*` on `client_api_key` and `/admin/*` on `adminKey`.

---

## Config / infra files (root)

| File | Purpose |
|------|---------|
| `pyproject.toml` / `uv.lock` | Python deps (managed with `uv`) |
| `alembic.ini` | Alembic config |
| `docker-compose.yml` | Postgres + Redis (+ app) for local dev |
| `Dockerfile` | App image |
| `justfile` | Task shortcuts (`just dev`, `just call`, etc.) |
| `pcc-deploy.toml` | Plivo Compute Cloud deploy config |
| `env.example` | Documented env template (copy to `.env`) |
| `README.md`, `RUN_LOCAL.md` | Human docs |

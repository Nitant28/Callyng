# 01 — Project Overview

> Source of truth: this document is reverse-engineered from the code under
> `aakashvani/`. Anything not directly verifiable from source is explicitly
> marked **"Not verified from source."**

---

## 1. Overall purpose

**Aakashvani** is a multi-tenant **outbound AI voice-calling platform** for the
Indian market (real estate, insurance, edtech, lending, healthcare). It places
automated phone calls to leads using a conversational AI voice agent, captures
the full transcript, extracts a structured outcome from each conversation with
an LLM, and drives a per-lead retry/callback state machine. It bills clients in
a prepaid "credits" model and can fan results out to external systems (CRM,
WhatsApp, Sheets) via signed n8n webhooks.

It is a **managed service**: the operator (admin) configures clients, bots,
scripts and campaigns; the client uploads leads, starts/stops campaigns, and
reviews call outcomes and transcripts.

Two distinct interfaces are served by the same backend:
- **Client app** (`/app/*`) — authenticated by a per-client API key (Bearer token).
- **Admin console** (`/admin/*`) — authenticated by a single shared `X-Admin-Key`.

Verified entry point: `server.py` (FastAPI app), with routers registered in
`server._register_api_routes()`.

---

## 2. Business workflow (end to end)

```
Admin creates Client ──> Admin tops up Client credits
        │
        ▼
Admin creates script_config (prompts/extraction/outcomes)  [optional, dynamic CMS]
        │
        ▼
Admin creates bot_config (route + script_id + telephony number + credits/min)
        │
        ▼
Admin or Client creates Campaign (bot_config + budget + dialer throttles)
        │
        ▼
Client uploads leads CSV (validated against lead_schema) ──> leads table
        │
        ▼
Client/Admin STARTS campaign ──> dialer loop begins claiming leads
        │
        ▼
Dialer fires Plivo call ──> /answer ──> /ws (Pipecat bot) ──> live conversation
        │
        ▼
Call ends ──> transcript stored ──> Groq post-call extraction ──> outcome
        │
        ▼
Lead state machine transitions (completed / failed / callback_scheduled / pending-retry)
Budget settled (credits charged), campaign counters updated
        │
        ▼
Webhook fired to n8n (lead_qualified / lead_callback / lead_failed / campaign_completed)
        │
        ▼
Client dashboard + call logs reflect denormalized stats + transcripts
```

---

## 3. Main users

| User | Auth | Interface | Capabilities |
|------|------|-----------|--------------|
| **Admin / operator** | `X-Admin-Key` header (`ADMIN_API_KEY`) | `/admin/*` SPA + `/internal/*` API | Create clients, top up credits, create bot/script configs, create/manage all campaigns, view all calls, diagnostics, webhooks |
| **Client** | `Authorization: Bearer <api_key>` | `/app/*` SPA + `/api/*` API | View credit balance, manage own campaigns (start/stop/cancel), upload/manage leads, view own call logs + transcripts + recordings |
| **Plivo (telephony provider)** | Plivo Basic Auth (server→Plivo); webhook callbacks are unauthenticated by signature but keyed on `session_call_id`/`CallUUID` | `/answer`, `/ws`, `/plivo-hangup`, `/plivo-recording` | Places the actual PSTN call and streams audio |
| **n8n (webhook consumer)** | HMAC-SHA256 `X-Aakashvani-Signature` header (verified by n8n) | Receives outbound POSTs | Routes events to client CRMs |

Verified: `api/auth.py` (`require_admin`, `get_client_from_token`),
`n8n_webhook.sign_payload`.

---

## 4. Client workflow

Verified from `frontend/src/pages/client/*` and `api/routes/*`.

1. **Login** (`/login`): client pastes API key; frontend calls `GET /api/credits`
   with `Authorization: Bearer <key>`. On 200, key is stored in
   `localStorage['client_api_key']` and the SPA redirects to `/app`.
2. **Dashboard** (`/app`): shows credit balance (`GET /api/credits`) and a grid
   of campaigns (`GET /api/campaigns`). Polls every 5s when any campaign is
   `running`/`pausing`. Start/stop via `PATCH /api/campaigns/{id}/start|stop`.
3. **Campaign detail** (`/app/campaigns/:id`): metric cards
   (`GET /api/campaigns/{id}/stats`), lead table
   (`GET /api/campaigns/{id}/leads`), CSV upload
   (`POST /api/campaigns/{id}/leads/upload`), manual lead CRUD, status changes,
   release-stuck, cancel. Polls every 5s (2s while pausing) when active.
4. **Call logs** (`/app/calls`): list (`GET /api/calls`), transcript drawer
   (`GET /api/calls/{session_call_id}`), recording playback
   (`GET /api/calls/{id}/recording/play`). Drawer polls every 2s while
   `in_progress`.
5. **Settings** (`/app/settings`): theme toggle only (no API calls).

---

## 5. Admin workflow

Verified from `frontend/src/pages/admin/*` and `api/routes/internal*.py`.

1. **Login** (`/admin/login`): admin key validated against `GET /internal/health`.
   Stored in `localStorage['aakashvani_admin_key']`.
2. **Overview** (`/admin`): `GET /internal/stats` + `GET /internal/health`.
3. **Clients** (`/admin/clients`, `/admin/clients/:id`): create clients,
   regenerate keys, top up credits, view ledger/webhooks, toggle active, create
   campaigns for a client, start/stop campaigns.
4. **Bot configs** (`/admin/bot-configs`): create/patch bot configs binding a
   route + script_id (+ optional script_config) + telephony number + credits/min.
5. **Script configs** (`/admin/script-configs`): full dynamic prompt/extraction
   CMS — create/patch/rollback/test/dial-test script configs.
6. **Campaigns** (`/admin/campaigns`): list/create/start/stop/cancel any campaign.
7. **Calls** (`/admin/calls`): list all calls + transcript + recording.
8. **Diagnostics** (`/admin/diagnostics`): health, recent calls, per-campaign
   reconcile + release-stuck.
9. **Webhooks** (`/admin/webhooks`): upsert per-client per-event n8n URLs+secrets.

---

## 6. AI workflow

Verified from `bot_sts.py`, `bot_cascade.py`, `script_runtime.py`,
`post_call_extract.py`, `sts_scripts/`, `cascade_scripts/`.

Two **routes** (selected per bot_config):
- **`sts`** — Speech-to-Speech via **Google Gemini Live** (`GeminiLiveLLMService`).
  Single model handles STT+LLM+TTS. Scripts live under `sts_scripts/`.
- **`cascaded`** — separate STT (Sarvam) + LLM (Groq) + TTS (Cartesia) pipeline.
  Scripts live under `cascade_scripts/`.

Per call, the bot config and prompts are resolved via a **3-tier resolution**
(`script_runtime.resolve_sts_runtime` / `resolve_cascade_runtime`):
1. **Tier 1 — prefetched `script_config`**: dialer renders the DB `script_configs`
   row (templated with lead fields) and stashes it in Redis; `/ws` pops it.
2. **Tier 2 — `_pg.script_id`**: importlib-loads `sts_scripts/<script_id>.py`.
3. **Tier 3 — env default** (`STS_SCRIPT` / `CASCADE_SCRIPT`).

After the call, the transcript is sent to **Groq** (`extract_post_call`,
`POST_CALL_MODEL`, default `llama-3.3-70b-versatile`) with a system prompt built
from the `extraction_schema`. The raw JSON is **normalized** via declarative
rules, classified into outcome buckets (terminal/retry/callback), and promoted
to the lead.

See `10_AI_PIPELINE.md`.

---

## 7. Call workflow

Verified from `server.py`, `dialer/concurrent_dialer.py`, `telephony.py`,
`plivo_hangup.py`, `recording.py`, `call_transcript.py`, `post_call_processor.py`.

```
dialer claims lead (status pending/callback → calling, attempts+1, reserve 2 credits)
   │
   ▼
fire_call(): insert call_log (in_progress=TRUE) ──> Plivo /Call/ API
   │
   ▼ (callee answers)
Plivo GET /answer?call_id=… ──> waits for Gemini prewarm ──> returns <Stream> XML to /ws
   │                              also: link call_sid, start recording
   ▼
/ws WebSocket ──> Pipecat bot runs live conversation (transcript appended per turn)
   │
   ▼ (hangup: goodbye marker / end_call tool / max-call watchdog / callee hangup)
on_pipeline_finished ──> mark call_log not in_progress ──> Groq extraction
   │
   ▼
process_post_call(): bill credits, lead state machine, counters, settle budget, webhook
```

Unanswered calls (busy/no-answer/reject/failed) are settled at 0 credits via
`/plivo-hangup` → `settle_unanswered_call`. See `09_CALL_LIFECYCLE.md`.

---

## 8. Campaign workflow

Statuses: `draft → running → (pausing) → paused → … → completed | cancelled`
(verified `db/schema/001_initial.sql` CHECK + `007_remove_dnc.py`).

- `draft`: created, no dialer.
- `running`: dialer loop active (`dialer.concurrent_dialer.run_campaign_dialer`).
- `pausing`: stop requested but `calling_leads > 0` (in-flight calls finishing).
- `paused`: dialer stopped, resumable.
- `completed`: all dial counters zero, unused budget returned (`try_settle_campaign_budget`).
- `cancelled`: manually cancelled, leads terminalized, unused budget returned.

Budget is **pre-allocated**: at campaign creation the budget is deducted from
`clients.balance_credits`. Each dial reserves `RESERVE_CREDITS_PER_LEAD = 2`
credits against `budget_used_credits`; the reservation is settled to the actual
billed amount at call end. Unused budget is returned on completion/cancel.

See `08_DATA_FLOW.md` and `11_STATISTICS_ENGINE.md`.

---

## 9. Database workflow

Verified from `db/schema/*.sql`, `alembic/versions/*`, `db/postgres.py`.

- **PostgreSQL 16** is the system of record (multi-tenant; `client_id` on every
  business table). Accessed via an **asyncpg** pool (`db/postgres.py`).
- **Redis** holds ephemeral coordination state: Gemini prewarm signals
  (`warmup:*`), dialer distributed locks (`dialer_lock:*`), per-call script
  prefetch (`prefetch:*`), per-call pg context (`pgctx:*`), and rate-limit
  storage for slowapi.
- **SQLite** (`call_log_db.py`, `data/call_logs.db`) is a parallel, single-tenant
  transcript/usage log written on every call regardless of Postgres — a Phase-0
  artifact retained for the n8n webhook path and local bot testing.

Tables (Postgres): `clients`, `bot_configs`, `campaigns`, `leads`, `call_logs`,
`webhook_configs`, `credit_transactions`, `script_configs`,
`script_config_revisions`. See `04_DATABASE_SCHEMA.md`.

---

## 10. Technology stack

Verified from `pyproject.toml` imports, `package.json`, `docker-compose.yml`.

### Backend (Python, `>=3.x`; `.python-version` present)
- **FastAPI** + **uvicorn** — HTTP/WebSocket server.
- **Pipecat** — real-time voice agent pipeline framework.
- **google-genai** — Gemini Live (STS route).
- **Groq** (OpenAI-compatible chat API) — post-call extraction; cascade LLM.
- **Sarvam** (STT), **Cartesia** (TTS), Deepgram (optional) — cascade route.
- **asyncpg** — PostgreSQL pool.
- **redis.asyncio** — Redis.
- **Plivo** REST API — telephony (called directly via `aiohttp`).
- **slowapi** — rate limiting (100/min default).
- **loguru** — logging.
- **pandas** — CSV/XLSX lead parsing.
- **boto3** — Cloudflare R2 (legacy recording storage).
- **alembic** — migrations.
- **dateparser**, **phonenumbers** (via `lead_upload`).

### Frontend (`frontend/`)
- **React 18** + **Vite** + **react-router-dom**.
- **axios** (primary) and `fetch` (admin `apiFetch` helper).
- **TailwindCSS** (utility classes throughout).
- State: React Context (`AdminAuthContext`, `AdminDataContext`, `ToastContext`)
  + local `useState`/`useEffect`. **No** Redux/React-Query.

### Infra
- **docker-compose.yml**, **Dockerfile**, **pcc-deploy.toml** (Plivo PCC deploy),
  **justfile** (task runner), **alembic.ini**.

---

## 11. Folder structure (top level of `aakashvani/`)

```
aakashvani/
├── server.py                  # FastAPI app, telephony webhooks, /ws, router registration
├── bot_sts.py / bot_cascade.py / bot.py   # Pipecat voice bots (STS / cascade)
├── call_transcript.py         # transcript capture + pipeline finalize + post-call dispatch
├── post_call_processor.py     # lead state machine + billing + counters + webhook
├── post_call_extract.py       # Groq extraction + normalization
├── call_outcomes.py           # canonical outcome vocabulary + Plivo status mapping
├── script_runtime.py          # 3-tier script resolution + post-call snapshot
├── script_prefetch.py         # Redis prefetch of rendered script_configs
├── lead_context.py            # per-call lead fields
├── call_limits.py             # max-duration watchdog, end_call tool, goodbye hangup
├── call_metrics.py            # Pipecat usage metrics accumulator
├── pricing_sts.py             # approximate STS cost in INR
├── compliance.py              # TRAI 9am–9pm IST calling window
├── telephony.py               # Plivo Call API + balance + URL builders
├── plivo_hangup.py            # hangup webhook handler
├── recording.py               # Plivo Record API + recording webhook + R2 helpers
├── n8n_webhook.py             # outbound signed webhooks + outcome→event mapping
├── call_log_db.py             # SQLite transcript log (Phase 0)
├── background_tasks.py        # background task registry
├── api/
│   ├── auth.py                # admin + client auth dependencies
│   ├── guards.py              # campaign/lead modifiability guards
│   ├── script_config_validation.py
│   └── routes/                # internal.py, internal_script_configs.py, campaigns.py, leads.py, calls.py, credits.py
├── db/
│   ├── postgres.py            # asyncpg pool + ALL multi-tenant queries (3153 lines)
│   ├── redis_client.py        # Redis pool
│   ├── warmup_state.py        # Gemini prewarm signaling
│   └── schema/                # raw SQL applied by alembic (001–006)
├── dialer/
│   ├── concurrent_dialer.py   # per-campaign asyncio dialer loop
│   ├── dialer_lock.py         # Redis distributed lock
│   ├── cost_guard.py          # campaign budget guard
│   ├── plivo_balance.py       # Plivo account balance guard (cached)
│   └── maintenance.py         # stale call_log sweep loop
├── lead_upload/               # parser.py, validator.py, normaliser.py
├── sts_scripts/               # pyramid_* Gemini Live scripts + extraction schema
├── cascade_scripts/           # prowave cascade script
├── alembic/versions/          # 001…010 migrations
├── scripts/                   # CLI/ops scripts
├── tests/                     # pytest suite
└── frontend/                  # React SPA (client + admin)
```

See `02_FOLDER_EXPLANATION.md` for per-folder detail.

---

## 12. High-level architecture diagram

```
                         ┌──────────────────────────────────────┐
                         │         React SPA (Vite)             │
                         │  /app/*  (client)   /admin/* (admin) │
                         └───────────────┬──────────────────────┘
                       Bearer <api_key>  │  X-Admin-Key
                                         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         FastAPI (server.py, port 7860)                       │
│                                                                              │
│  Routers:  /api/credits  /api/campaigns  /api/campaigns/{id}/leads           │
│            /api/calls    /internal/*  /internal/script-configs/*             │
│  Telephony: POST /start  GET /answer  WS /ws  /plivo-hangup /plivo-recording │
│  slowapi rate limit (100/min) + CORS                                         │
└───────┬─────────────────┬───────────────────┬───────────────────┬───────────┘
        │                 │                   │                   │
        ▼                 ▼                   ▼                   ▼
┌──────────────┐  ┌───────────────┐   ┌──────────────┐   ┌────────────────┐
│ PostgreSQL16 │  │     Redis      │   │   Plivo PSTN │   │  Pipecat bot   │
│ (asyncpg)    │  │ locks/warmup/  │   │  (REST + WS) │   │ Gemini Live /  │
│ system of    │  │ prefetch/pgctx │   │              │   │ Sarvam+Groq+   │
│ record       │  │ ratelimit      │   │              │   │ Cartesia       │
└──────────────┘  └───────────────┘   └──────────────┘   └────────────────┘
        │                                                          │
        │                                          post-call: Groq extraction
        ▼                                                          ▼
┌──────────────┐                                          ┌────────────────┐
│  SQLite      │                                          │  n8n webhooks  │
│ call_logs.db │                                          │ (HMAC-signed)  │
│ (Phase 0)    │                                          │  → client CRM  │
└──────────────┘                                          └────────────────┘

Background loops (asyncio tasks in the FastAPI process):
 - per-campaign dialer loops (concurrent_dialer.run_campaign_dialer)
 - stale call_log sweep (dialer.maintenance.stale_call_log_loop, every 300s)
 - auto-resume of 'running' campaigns at startup (server.lifespan)
```

**Deployment note:** The dialer and background sweeps run as in-process asyncio
tasks. Redis dialer locks (`dialer_lock:*`) ensure only one worker runs a given
campaign even with multiple processes. Recordings are stored as Plivo-hosted
URLs (`plivo:<url>`) by default; R2 (`recording.py`) is legacy.

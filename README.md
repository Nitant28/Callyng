# Aakashvani

> **Managed AI outbound voice** for the Indian SMB market — outcomes and ops, not a self-serve bot builder.
> Pipecat 1.1.0 + Plivo + Gemini Live + FastAPI.

---

## You are here

| Field             | Value                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Phase             | **Phase 2 — Multi-tenant + billing** — in progress (May 2026) |
| Last milestone    | Campaign hardening (post-call finalize, cancel vs pause, stale call_log sweep); operator CLI (`scripts/cli.py`); docs in [`guides/`](guides/) and [`handoff/`](handoff/). |
| Current focus     | React SPA (Phase 2B); pre-launch draft workflow ([ROADMAP §10](ROADMAP.md#10-pre-launch-client-workflow-priorities)) |
| Next milestone    | Client portal: upload → draft leads → test call → Start |
| Full plan         | [ROADMAP.md](ROADMAP.md) (phases) · [guides/aakash_arch.md](guides/aakash_arch.md) (schema & contracts) · [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) (ops CLI) |

---

## What this is

**Product model.** Aakashvani is a **managed voice automation service**: we own bot scripts, prompts, route/model choice, Plivo numbers, n8n workflow design, and CRM handoffs. Clients use a future web app to upload leads, run campaigns, inspect logs, and manage **credits** (see [ROADMAP.md](ROADMAP.md) §1 and [guides/aakash_arch.md](guides/aakash_arch.md) §4).

**Phase 0 / Phase 1 (foundation) are done** — single-tenant dev server + SQLite + `POST /start`, two voice routes, post-call extraction. **Phase 2** Postgres schema + pool are in place; `just call` still uses SQLite until dialer/API wiring. Phase 1 client SPAs resume after Phase 2 backend APIs.

**Config model (forward path).** The DB `bot_configs` row is a **registry** (`route`, `script_id`, `credits_per_minute`, Plivo number). Prompts, VAD, models, `LEAD_SCHEMA`, and **`EXTRACTION_SCHEMA`** live in [`sts_scripts/`](sts_scripts/) and [`cascade_scripts/`](cascade_scripts/). Post-call Groq reads `EXTRACTION_SCHEMA` from the active script at runtime.

**Billing (forward path).** Clients hold **credits** (1 credit = ₹1 at launch). Campaigns pre-allocate budget from the master balance; calls bill in ceiling minutes × `credits_per_minute`. See [guides/aakash_arch.md §4](guides/aakash_arch.md).

Two voice pipelines can call any Indian phone number via Plivo — details under [Tech stack](#tech-stack) below.

---

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- [Docker Desktop](https://docs.docker.com/desktop/) with **WSL 2 integration** enabled for your Ubuntu distro (Settings → Resources → WSL Integration), **or** [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [ngrok](https://ngrok.com/) with a reserved free domain (or a paid plan)
- [just](https://github.com/casey/just) (optional, recommended) — `sudo apt install just` on Ubuntu 24.04+, `cargo install just`, or grab a binary from the GitHub releases
- A Plivo account with auth ID/token and an outbound-enabled India phone number
- A Google API key with Gemini Live access

---

## Quick start

```bash
# 1. Install Python deps
uv sync

# 2. Copy and fill in secrets
cp env.example .env
# edit .env: set PLIVO_*, GOOGLE_API_KEY, NGROK_URL, BOT_ROUTE (and STS_SCRIPT / CASCADE_SCRIPT)
# GROQ_API_KEY enables post-call extraction

# 3. Start the server (uses BOT_ROUTE from .env, defaults to sts)
just dev

# 4. In another terminal, open the ngrok tunnel on your reserved domain
just tunnel

# 5. In a third terminal, fire a test call
just call +919123866924 Satyam Pune
```

That's it. The callee's phone rings; on pickup, Diya greets them in Marathi.

## Phase 2 quick start (multi-tenant backend)

Requires Postgres running locally. The Phase 0 single-call path still works without Postgres.

```bash
# Start Postgres (once)
docker run --name aakashvani-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_USER=aakashvani \
  -e POSTGRES_DB=aakashvani -p 5432:5432 -d postgres:16

# Or: just db-up
just db-migrate # Runs standard Alembic migrations
just db-check

# Create your first client (save the api_key — shown once)
just create-client "My Company" "admin@company.com" "real_estate"

# Add credits
just add-credits <client-id> 1000

# Upload sample leads (see fixtures/test_leads.csv)
just upload-leads <api_key> <campaign_id> fixtures/test_leads.csv
just start-campaign <api_key> <campaign_id>

# Inspect campaigns without the HTTP API (Postgres only)
just show-client "My Company"
just show-campaign "<campaign name>"
just campaign-calls "<campaign name>" --limit 5

# Full walkthrough: guides/TESTING.md — operator CLI: guides/CLI_GUIDE.md
```

## Operator CLI (Phase 2)

[`scripts/cli.py`](scripts/cli.py) talks to Postgres via `DATABASE_URL` — **no running server required**. Fuzzy name lookup (`just show-client "pyr"` matches “Pyramid Real Estate”).

| Category | Examples |
| -------- | -------- |
| Inspection | `show-client`, `show-campaign`, `campaign-leads`, `campaign-calls`, `show-call`, `show-lead` |
| Post-call debug | `failed-extractions`, `stuck-calls`, `rerun-extraction` |
| Writes | `reset-lead`, `force-outcome`, `settle-campaign` |

Full reference: **[guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)**. API polling: `just watch-call <api_key> <session_call_id>`.

## Dual storage (Phase 2)

Phase 2 runs two storage layers simultaneously:

- **SQLite** (`CALL_LOG_DB_PATH`) — always active. Every completed call writes here regardless of Postgres status. Use `just sqlite-calls` and `just test-call` to verify bot quality without any Postgres dependency.
- **PostgreSQL** (`DATABASE_URL`) — active when `DATABASE_URL` is set. All multi-tenant data (clients, campaigns, leads, credits) lives here. Campaign calls write `call_logs` with transcript, `outcome`, `duration_seconds`, and `extraction_json` (e.g. `intent_status`, `callback_time`) after Groq post-call.

A Postgres write failure never affects the Pipecat pipeline. SQLite is the isolation surface for bot testing.

### PostgreSQL (Phase 2 — Docker)

Multi-tenant data lives in **PostgreSQL 16** via [docker-compose.yml](docker-compose.yml). Outbound test calls still write to **SQLite** until Phase 2 wires the pipeline to Postgres.

```bash
# 1. Install Docker Desktop (Windows) and enable WSL integration for Ubuntu, then:
docker --version
docker compose version

# 2. Add DATABASE_URL to .env (see env.example)
cp env.example .env   # if needed; set DATABASE_URL and other secrets

# 3. Start DB, apply schema, seed dev tenant
just db-up
just db-migrate
just db-seed
just db-verify      # checks tables, seed balance, budget allocation

# Optional: interactive SQL
just db-psql
```

**Dev tenant** (from [db/seed/dev_tenant.sql](db/seed/dev_tenant.sql)):

| Resource | UUID |
| -------- | ---- |
| Client | `00000000-0000-4000-8000-000000000001` |
| Bot config (`pyramid_mr`, STS) | `00000000-0000-4000-8000-000000000002` |
| Draft campaign | `00000000-0000-4000-8000-000000000003` |

**Dev API key** (Bearer, for future `/api/*`): `aakashvani_dev_key_change_me` — change in production; only the SHA-256 hash is stored in `clients.api_key_hash`.

Reset dev database (drops volume): `just db-reset`

### Call logs and transcripts

- Each completed pipeline run appends one row to the SQLite DB at `CALL_LOG_DB_PATH` (default `./data/call_logs.db`). Columns include `session_call_id` (UUID from `POST /start`), `plivo_call_id`, `route`, timestamps, `duration_ms`, `transcript_json` (array of `{role, content, timestamp, …}`), **token usage** (`usage_prompt_tokens`, `usage_completion_tokens`, `usage_total_tokens`, `usage_tts_characters`, `usage_metrics_json`), optional **`cost_inr`** (STS only, when `GEMINI_LIVE_INPUT_USD_PER_1M` and `GEMINI_LIVE_OUTPUT_USD_PER_1M` are set), and **post-call extraction** (`extraction_json`, `extraction_error`, `extraction_model`) when `GROQ_API_KEY` is set. Extraction fields and Groq prompt rules come from the active script module's **`EXTRACTION_SCHEMA`** (built at runtime, not hardcoded in Python). `extraction_json` includes `intent_status` (values include **`Interested`**, `Not_Interested`, `Busy`, `Callback_Requested`, `Wrong_Requirement`, `Unknown`) plus preferences; a small **normalizer** upgrades inconsistent pairs (e.g. `site_visit_agreed: true` with `Unknown` intent → `Interested`) before the row is updated.
- **Call duration:** `MAX_CALL_MINUTES` (default `10`, `0` = no timer) starts a background watchdog that queues an `EndFrame` (Plivo hangup). Cascade and STS also expose an **`end_call`** LLM tool via [`call_limits.py`](call_limits.py) so the model can hang up after the final goodbye; cascade order is `push_lead_data` then goodbye then `end_call`.
- Transcripts are built from Pipecat universal aggregator **`on_user_turn_stopped`** / **`on_assistant_turn_stopped`** events. For STS, the synthetic bootstrap user line (“The call has just connected…”) is **stripped** before persistence.
- Verify SQLite from Python: `uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"` (no extra pip package; uses the standard library).

### Without `just`

Same flow, no `just` install required:

```bash
BOT_ROUTE=sts uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload
ngrok http --domain=<your-reserved-domain> 7860
scripts/call.sh +919123866924 Satyam Pune
```

---

## Tech stack

Pipecat 1.1.0 + Plivo + Gemini Live + FastAPI. Phase 2 DB route values are `sts` | `cascaded`; env still uses `BOT_ROUTE=sts` or `BOT_ROUTE=cascade` until retired.

Two voice pipelines that can call any Indian phone number via Plivo and hold a conversation:

- **Route A — Cascaded** ([bot_cascade.py](bot_cascade.py)): Sarvam STT → Groq → Cartesia. Prompt in [`cascade_scripts/`](cascade_scripts/) (`CASCADE_SCRIPT`, default `prowave`). ~1.5–2.5 s round-trip. Function-calling (`push_lead_data`, `end_call`), easy to audit. Post-call Groq extraction uses the script's **`EXTRACTION_SCHEMA`** (canonical for CRM/n8n); `push_lead_data` remains for live capture today.
- **Route B — STS** ([bot_sts.py](bot_sts.py)): Gemini Live (speech-to-speech). Script modules under [`sts_scripts/`](sts_scripts/) (default `STS_SCRIPT=pyramid_mr` Marathi; set `STS_SCRIPT=pyramid_hi` for Hindi). ~0.5–1 s round-trip. **Diya** / Pyramid Parkland Nxt. Lead JSON is **not** captured via live tools; after hang-up, `call_transcript.py` runs **Groq** extraction from the script's **`EXTRACTION_SCHEMA`** into `call_logs.extraction_json`. Optional **`end_call`** tool + goodbye hangup fallback (`call_limits.py`); **`MAX_CALL_MINUTES`** caps duration.

Calls are placed by hitting `POST /start` on the FastAPI server in [server.py](server.py). Pipecat handles the audio pipeline; Plivo handles the PSTN leg.

---

## Repo layout (current)

```
aakashvani/
├── docker-compose.yml       Postgres 16 for local dev (port 5432)
├── frontend/                React SPAs (Phase 2B)
│   ├── client/              Client portal
│   └── admin/               Admin dashboard
├── db/
│   ├── postgres.py          asyncpg pool + client_id-scoped helpers + budget transactions
│   ├── schema/001_initial.sql   Full schema ([guides/aakash_arch.md](guides/aakash_arch.md) §2)
│   └── seed/dev_tenant.sql  Dev client, bot_config, draft campaign
├── server.py                FastAPI app: /start, /answer (Plivo XML), /ws, /health
├── call_transcript.py       Turn buffer + pipeline end → call_logs + Groq + n8n POST
├── call_log_db.py           SQLite schema/migrations + insert + extraction update (Phase 0)
├── call_metrics.py          UsageMetricsTap: sums LLM/TTS usage from Pipecat MetricsFrame
├── call_limits.py           MAX_CALL_MINUTES watchdog + shared ``end_call`` coordinator
├── pricing_sts.py           Optional STS `cost_inr` from token counts + env USD rates
├── n8n_webhook.py           Outbound POST of call payload to `N8N_WEBHOOK_URL`
├── post_call_extract.py     Schema-driven Groq extraction + normalize_post_call_extraction
├── lead_context.py          Shared LeadContext (name, phone, city) for script modules
├── sts_scripts/             STS modules: prompts, VAD, GEMINI_*, EXTRACTION_SCHEMA
│   └── pyramid_extraction.py  Shared EXTRACTION_SCHEMA for Pyramid bots
├── cascade_scripts/         Cascade modules; CASCADE_SCRIPT env; EXTRACTION_SCHEMA
├── bot.py                   Stock pipecat outbound example (kept as reference)
├── bot_sts.py               Route B: Gemini Live pipeline (loads sts_scripts.*)
├── bot_cascade.py           Route A: Sarvam + Groq + Cartesia (loads cascade_scripts.*)
├── data/                    Default location for `call_logs.db` (gitignored; see CALL_LOG_DB_PATH)
├── justfile                 Dev commands (dev, db-*, campaigns, operator CLI recipes)
├── scripts/
│   ├── cli.py               Operator CLI (inspection, post-call debug, lead reset)
│   └── call.sh              Standalone call trigger (no `just` dependency)
├── env.example              Template for .env
├── .env                     Real secrets (not committed)
├── pyproject.toml           uv project metadata + deps
├── uv.lock                  Pinned dependency lockfile
├── Dockerfile               Pipecat Cloud deploy image
├── pcc-deploy.toml          Pipecat Cloud deploy config
├── guides/                  Operator guides (CLI, testing, architecture)
│   ├── CLI_GUIDE.md         Operator CLI / `just show-*` recipes
│   ├── TESTING.md           Phase 2 E2E walkthrough
│   └── aakash_arch.md       Schema, billing, dialer, API contracts
├── handoff/                 Session handoffs and audit notes for agents
├── fixtures/                Sample CSVs for local testing
├── ROADMAP.md               Vision, phases, pricing
└── README.md                this file
```

---

## How a call flows

```mermaid
sequenceDiagram
    autonumber
    participant You as you (curl/just call)
    participant Server as FastAPI /start
    participant Plivo
    participant Pipecat as Pipecat (bot_sts/bot_cascade)
    participant Gemini as Gemini Live
    participant Callee

    You->>Server: POST /start {phone, lead_name, city}
    Server->>Plivo: REST API: dial callee, answer_url=/answer
    Server-->>You: 200 OK {call_id, ...}
    par prewarm (background)
        Server->>Gemini: open throwaway live session, drain 1 chunk
    end
    Plivo->>Callee: ring
    Callee->>Plivo: pickup
    Plivo->>Server: GET /answer?call_id=...
    Server-->>Plivo: <Stream> XML pointing at /ws
    Plivo->>Server: WSS /ws (audio stream)
    Server->>Pipecat: bot(runner_args)
    Pipecat->>Gemini: open live session (tools=None) + send seed turn
    Gemini-->>Pipecat: first audio chunk (~0.5-1 s after handshake)
    Pipecat-->>Callee: Diya speaks the greeting
    Note over Pipecat: On pipeline end: transcript + cost_inr → SQLite; Groq extract from script EXTRACTION_SCHEMA; POST to n8n URL if set
```

---

## `just` commands reference

| Command                    | What it does                                                                |
| -------------------------- | --------------------------------------------------------------------------- |
| `just dev`                 | Run uvicorn with whatever `BOT_ROUTE` is in `.env` (default `sts`)          |
| `just dev-sts`             | Force `BOT_ROUTE=sts` for this run                                          |
| `just dev-cascade`         | Force `BOT_ROUTE=cascade` for this run                                      |
| `just dev-sts-hi`        | Same as STS with `STS_SCRIPT=pyramid_hi` (Hindi script)                     |
| `just tunnel`              | Start ngrok on your reserved domain (`NGROK_URL` in `.env`), port 7860      |
| `just call +91… name city` | POST `/start` for an outbound call. `name` and `city` are optional          |
| `just health`              | GET `/health` on the public URL                                             |
| `just route`               | Print the currently-effective `BOT_ROUTE`                                   |
| `just sync`                | `uv sync` (rebuilds `.venv` — useful if anything looks broken)              |
| `just db-migrate`          | Alembic upgrade head (Postgres schema)                                      |
| `just db-check`            | List public tables in Postgres                                              |
| `just create-client`       | Admin: create client + API key (once)                                       |
| `just add-credits`         | Admin: top up client balance                                                |
| `just create-bot`          | Admin: register bot_config                                                    |
| `just create-campaign`     | Admin: create campaign + budget allocation                                  |
| `just upload-leads`        | Client: CSV upload to campaign                                              |
| `just start-campaign`      | Client: start dialer                                                          |
| `just stop-campaign`       | Client: pause dialer (leads preserved; credits stay on campaign)              |
| `just cancel-campaign`     | Client: cancel campaign (fail non-terminal leads; return unused credits)      |
| `just watch-call`          | Client API: poll one call by `session_call_id`                                |
| `just test-call`           | Phase 0 outbound call (SQLite; bash `scripts/call.sh`)                      |
| `just sqlite-calls`        | Inspect recent SQLite call_logs rows                                          |
| `just test-phase2`         | Run `tests/test_phase2.py`                                                    |
| `just release-stuck-leads` | Reset leads stuck in `calling` (no live Plivo leg)                            |
| `just reconcile-campaign`  | Recompute campaign counter denorms from lead rows                             |
| `just plivo-balance`       | Show Plivo prepaid balance                                                    |

**Operator CLI** (Postgres direct — see [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)):

| Command | What it does |
| ------- | ------------ |
| `just show-client "…"` | Client balance, bots, campaigns |
| `just show-campaign "…"` | Budget, counters, bot config |
| `just campaign-leads "…" --status pending` | Filter leads |
| `just campaign-calls "…" --limit 10` | Recent `call_logs` |
| `just show-call <session_id> --full` | Transcript + `extraction_json` |
| `just failed-extractions` | Calls missing outcome or extraction error |
| `just stuck-calls` | Orphaned `in_progress` call logs |
| `just rerun-extraction <session_id>` | Re-run Groq on stored transcript |
| `just reset-lead <phone> --campaign "…"` | Lead back to `pending` for retest |
| `just settle-campaign "…"` | Force budget settlement |

---

## Troubleshooting

- **`just: command not found`** — install it (`sudo apt install just` or `cargo install just`) or use the `scripts/call.sh` fallback + the raw `uv run uvicorn …` invocations from the README.
- **`uv run` complains about a missing `.venv` after this rename** — run `just sync` (or `uv sync`) once to rebuild venv shebangs against the new path.
- **`server.py` keeps picking the wrong route** — `BOT_ROUTE` is read at module load. After editing `.env`, fully restart `just dev` (a uvicorn `--reload` re-import is fine).
- **Plivo says the WebSocket URL is unreachable** — confirm `just tunnel` is up and the reserved domain in `.env` (`NGROK_URL`) matches `https://<sub>.ngrok-free.dev` exactly.
- **First bot utterance is still slow** — watch the `[⏱ Ns]` log lines from `bot_sts.py`. If `parse_telephony_websocket done` takes >1 s, it's Plivo's `start` frame; if `LLMRunFrame queued → first audio` takes >2 s, it's Gemini's WS handshake. Prewarm (STS only) should log `[prewarm:…] Gemini warmed up ✓` — if you see `Pre-warm failed (1011…)`, check `GOOGLE_API_KEY`, `STS_SCRIPT`, and that `BOT_ROUTE=sts`.
- **Long STS calls and token growth** — enable context window compression (default on): `GEMINI_CONTEXT_COMPRESSION=1`, tune `GEMINI_CWC_TRIGGER_TOKENS` (default `20000`; API retains roughly half as the sliding target). `system_instruction` (project facts) stays on the Live connect payload.
- **Live call polling stuck after a crash** — `STALE_CALL_LOG_SWEEP_ENABLED` (default true) finalizes `call_logs` left `in_progress` longer than `MAX_CALL_MINUTES + 2` minutes; runs at server startup and every `STALE_CALL_LOG_SWEEP_SECONDS` (default 300).
- **Credits not returned after stopping a campaign** — `stop` only pauses. Use `just cancel-campaign` to fail remaining leads and return unused budget (waits for in-flight calls if any).
- **`call_logs` has `ended_at` but empty `outcome` / `transcript`** — ensure `GROQ_API_KEY` is set and post-call completed; use `just show-call <session_id> --full` or `just failed-extractions`. If the pipeline logged turns but Postgres is empty, restart `just dev` after pulling latest (post-call finalize no longer requires `in_progress = TRUE`).
- **Dialer shows pending leads but does not dial** — retry may be scheduled in the future (`next_attempt_at`); on campaign start, pending retries are bumped to now. See `just campaign-leads "…" --status pending` and [handoff/DEBUGGING_CONTEXT.md](handoff/DEBUGGING_CONTEXT.md).

---

## Next development steps

**Phase 0 (foundation)** — complete. Dev testing stays on Plivo + ngrok (`just call`).

**Phase 2 (current)** — backend largely complete; see [guides/TESTING.md](guides/TESTING.md):

1. ~~Postgres 16 + Alembic + full schema~~ — done
2. ~~`/internal/*` + `/api/*` endpoints~~ — done
3. ~~`post_call_processor`, lead upload, concurrent dialer~~ — done
4. ~~Campaign hardening (post-call guard, cancel vs pause, stale call_log sweep)~~ — done
5. Client and Admin React SPAs (Phase 2B) — next

### Pre-launch workflow priorities (implement in this order)

These are the highest-priority **client-facing** features before production campaigns. Full detail: [ROADMAP.md §10](ROADMAP.md#10-pre-launch-client-workflow-priorities).

| Priority | Feature | Notes |
| -------- | ------- | ----- |
| **1** | **Data cleaning + pre-upload report** | Validate and normalize CSV against `LEAD_SCHEMA` before commit; return accepted / rejected / fixed rows. Catches bad data before it enters the system. |
| **2** | **Draft-state lead management** | Single feature: while campaign is `draft`, edit, delete, and manually add leads (no full re-upload). API mutations blocked after start. |
| **3** | **Single test call** | One real call from the draft screen (campaign `bot_config` + chosen lead) for pre-launch confidence; does not start the dialer. |
| **4** | **Lock on Start** | `PATCH /api/campaigns/{id}/start` must reject unless `status = 'draft'` (409 otherwise), then transition to `running`. **Not enforced in API yet.** |

Target UX: upload → review report → fix leads in draft → optional test call → Start.

See [ROADMAP.md §9 Phase 2](ROADMAP.md#phase-2--multi-tenant--billing) for phase milestones and the **deferred hardening** list.

**Campaign control:** `stop` = pause (resume later). `cancel` = terminal (unused credits return when no in-flight calls).

**Deferred:** `credits_per_minute` snapshot, CostGuard overshoot docs, `attempt_kind` on call_logs — see [ROADMAP.md](ROADMAP.md). Browser `SmallWebRTCTransport` → Phase 4. Call Recordings → Phase 3. Inbound bots → Phase 4. Razorpay → Phase 5. For production, `ngrok` is replaced by `nginx` with wildcard TLS.

---

## Documentation

| Document | Use for |
| -------- | ------- |
| [README.md](README.md) | Dev setup, quick start, troubleshooting (this file) |
| [ROADMAP.md](ROADMAP.md) | Vision, phases, [pre-launch priorities](ROADMAP.md#10-pre-launch-client-workflow-priorities), pricing, compliance |
| [guides/](guides/) | [CLI](guides/CLI_GUIDE.md) (operator), [testing](guides/TESTING.md) (E2E), [architecture](guides/aakash_arch.md) |
| [handoff/](handoff/) | [Phase 2 handoff](handoff/PHASE2_HANDOFF.md), [debugging](handoff/DEBUGGING_CONTEXT.md), audit [report](handoff/report.md) |
| [fixtures/](fixtures/) | Sample CSVs (e.g. `test_leads.csv` for upload tests) |

If README or ROADMAP conflict with [guides/aakash_arch.md](guides/aakash_arch.md), **arch wins**.

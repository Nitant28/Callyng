# Aakashvani

> **Managed AI outbound voice** for the Indian SMB market — outcomes and ops, not a self-serve bot builder.
> Pipecat 1.1.0 + Plivo + Gemini Live + FastAPI.

---

## You are here

| Field             | Value                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Phase             | **Phase 0 — Foundation** — **complete** (May 2026). Roadmap Phase 1 closed; **Phase 2** in progress. |
| Last milestone    | Call logs, metrics, Groq extraction, n8n webhook, `end_call` / max duration, STS context compression + Gemini prewarm. |
| Current focus     | **Phase 2 prep** — docs aligned with [aakash_arch.md](aakash_arch.md); **schema-driven extraction** in script files. |
| Next milestone    | PostgreSQL 16, `client_id` isolation, credits + campaign budgets, CostGuard, Postgres concurrent dialer — see [ROADMAP.md §9 Phase 2](ROADMAP.md#phase-2--multi-tenant--billing). |
| Full plan         | [ROADMAP.md](ROADMAP.md) (phases) · [aakash_arch.md](aakash_arch.md) (schema & contracts)         |

---

## What this is

**Product model.** Aakashvani is a **managed voice automation service**: we own bot scripts, prompts, route/model choice, Plivo numbers, n8n workflow design, and CRM handoffs. Clients use a future web app to upload leads, run campaigns, inspect logs, and manage **credits** (see [ROADMAP.md](ROADMAP.md) §1 and [aakash_arch.md](aakash_arch.md) §4).

**Phase 0 / Phase 1 (foundation) are done** — single-tenant dev server + SQLite + `POST /start`, two voice routes, post-call extraction. **Phase 2** (multi-tenant Postgres backend) is next; Phase 1 client SPA milestones resume after Phase 2.

**Config model (forward path).** The DB `bot_configs` row is a **registry** (`route`, `script_id`, `credits_per_minute`, Plivo number). Prompts, VAD, models, `LEAD_SCHEMA`, and **`EXTRACTION_SCHEMA`** live in [`sts_scripts/`](sts_scripts/) and [`cascade_scripts/`](cascade_scripts/). Post-call Groq reads `EXTRACTION_SCHEMA` from the active script at runtime.

**Billing (forward path).** Clients hold **credits** (1 credit = ₹1 at launch). Campaigns pre-allocate budget from the master balance; calls bill in ceiling minutes × `credits_per_minute`. See [aakash_arch.md §4](aakash_arch.md).

Two voice pipelines can call any Indian phone number via Plivo — details under [Tech stack](#tech-stack) below.

---

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
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
├── server.py                FastAPI app: /start, /answer (Plivo XML), /ws, /health
├── call_transcript.py       Turn buffer + pipeline end → call_logs + Groq + n8n POST
├── call_log_db.py           SQLite schema/migrations + insert + extraction update
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
├── justfile                 Dev commands (dev, dev-sts, dev-cascade, tunnel, call, health, route, sync)
├── scripts/
│   └── call.sh              Standalone call trigger (no `just` dependency)
├── env.example              Template for .env
├── .env                     Real secrets (not committed)
├── pyproject.toml           uv project metadata + deps
├── uv.lock                  Pinned dependency lockfile
├── Dockerfile               Pipecat Cloud deploy image
├── pcc-deploy.toml          Pipecat Cloud deploy config
├── aakash_arch.md           Architecture reference: schema, billing, dialer, contracts
├── ROADMAP.md               Vision, phases, pricing; defers schema detail to aakash_arch.md
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

---

## Troubleshooting

- **`just: command not found`** — install it (`sudo apt install just` or `cargo install just`) or use the `scripts/call.sh` fallback + the raw `uv run uvicorn …` invocations from the README.
- **`uv run` complains about a missing `.venv` after this rename** — run `just sync` (or `uv sync`) once to rebuild venv shebangs against the new path.
- **`server.py` keeps picking the wrong route** — `BOT_ROUTE` is read at module load. After editing `.env`, fully restart `just dev` (a uvicorn `--reload` re-import is fine).
- **Plivo says the WebSocket URL is unreachable** — confirm `just tunnel` is up and the reserved domain in `.env` (`NGROK_URL`) matches `https://<sub>.ngrok-free.dev` exactly.
- **First bot utterance is still slow** — watch the `[⏱ Ns]` log lines from `bot_sts.py`. If `parse_telephony_websocket done` takes >1 s, it's Plivo's `start` frame; if `LLMRunFrame queued → first audio` takes >2 s, it's Gemini's WS handshake. Prewarm (STS only) should log `[prewarm:…] Gemini warmed up ✓` — if you see `Pre-warm failed (1011…)`, check `GOOGLE_API_KEY`, `STS_SCRIPT`, and that `BOT_ROUTE=sts`.
- **Long STS calls and token growth** — enable context window compression (default on): `GEMINI_CONTEXT_COMPRESSION=1`, tune `GEMINI_CWC_TRIGGER_TOKENS` (default `20000`; API retains roughly half as the sliding target). `system_instruction` (project facts) stays on the Live connect payload.

---

## Next development steps

**Phase 0 (foundation)** — complete. Dev testing stays on Plivo + ngrok (`just call`).

**Phase 2 (current)** — admin-first backend per [aakash_arch.md §13](aakash_arch.md):

1. Postgres 16 + full schema ([§2](aakash_arch.md))
2. `/internal/*` admin endpoints (clients, bot-configs, campaigns, credits, webhooks)
3. `post_call_processor`, lead upload, Postgres concurrent dialer
4. Client `/api/*` + React SPA (Phase 2B)

See [ROADMAP.md §9 Phase 2](ROADMAP.md#phase-2--multi-tenant--billing) for the full milestone table.

**Deferred:** browser `SmallWebRTCTransport` dev path → Phase 4. Phase 1 client SPA → after Phase 2 backend. Razorpay → Phase 3.

---

## Documentation

| Document | Use for |
| -------- | ------- |
| [README.md](README.md) | Dev setup, quick start, troubleshooting (this file) |
| [ROADMAP.md](ROADMAP.md) | Vision, phases, pricing, compliance |
| [aakash_arch.md](aakash_arch.md) | Postgres schema, credits, dialer, script contracts, security |

If README or ROADMAP conflict with `aakash_arch.md`, **arch wins**.

# Aakashvani

> **AI-powered outbound voice agent platform for the Indian SMB market.**
> Pipecat 1.1.0 + Plivo + Gemini Live + FastAPI.

---

## You are here

| Field             | Value                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Phase             | **Phase 0 — Foundation** (week 1 of 2)                                                            |
| Last milestone    | **Call limits** — `MAX_CALL_MINUTES` watchdog + `end_call` LLM tool on cascade and STS (`call_limits.py`); Plivo hangup via `EndFrame`. |
| Current focus     | Browser `SmallWebRTCTransport` dev path (no Plivo minutes during dev). |
| Next milestone    | See [ROADMAP.md](ROADMAP.md) — SmallWebRTCTransport. |
| Full plan         | See [ROADMAP.md](ROADMAP.md).                                                                     |

---

## What this is

Two voice pipelines that can call any Indian phone number via Plivo and hold a conversation:

- **Route A — Cascaded** ([bot_cascade.py](bot_cascade.py)): Sarvam STT (Hindi/Marathi/auto) → Groq Llama 3.3 70B → Cartesia TTS. Tight script control, function-calling (`push_lead_data`, `end_call`), easy to audit. ~1.5–2.5 s round-trip.
- **Route B — STS** ([bot_sts.py](bot_sts.py), [bot_sts_hi.py](bot_sts_hi.py)): Gemini Live (speech-to-speech) — single model handles STT + LLM + TTS. ~0.5–1 s round-trip. **Diya** outbound scripts (Marathi: Pyramid Parkland Nxt; Hindi: Tesseract Nilaya). Lead JSON is **not** captured via live tools; after hang-up, `call_transcript.py` runs **Groq** extraction into `call_logs.extraction_json`. Optional **`end_call`** tool ends the PSTN leg after the closing script; **`MAX_CALL_MINUTES`** caps duration.

Calls are placed by hitting `POST /start` on the FastAPI server in [server.py](server.py). Pipecat handles the audio pipeline; Plivo handles the PSTN leg.

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
# edit .env: set PLIVO_*, GOOGLE_API_KEY, NGROK_URL, BOT_ROUTE

# 3. Start the server (uses BOT_ROUTE from .env, defaults to sts)
just dev

# 4. In another terminal, open the ngrok tunnel on your reserved domain
just tunnel

# 5. In a third terminal, fire a test call
just call +919123866924 Satyam Pune
```

That's it. The callee's phone rings; on pickup, Diya greets them in Marathi.

### Call logs and transcripts

- Each completed pipeline run appends one row to the SQLite DB at `CALL_LOG_DB_PATH` (default `./data/call_logs.db`). Columns include `session_call_id` (UUID from `POST /start`), `plivo_call_id`, `route`, timestamps, `duration_ms`, `transcript_json` (array of `{role, content, timestamp, …}`), **token usage** (`usage_prompt_tokens`, `usage_completion_tokens`, `usage_total_tokens`, `usage_tts_characters`, `usage_metrics_json`), optional **`cost_inr`** (STS only, when `GEMINI_LIVE_INPUT_USD_PER_1M` and `GEMINI_LIVE_OUTPUT_USD_PER_1M` are set), and **post-call extraction** (`extraction_json`, `extraction_error`, `extraction_model`) when `GROQ_API_KEY` is set. `extraction_json` includes `intent_status` (values include **`Interested`**, `Not_Interested`, `Busy`, `Callback_Requested`, `Wrong_Requirement`, `Unknown`) plus preferences; a small **normalizer** upgrades inconsistent pairs (e.g. `site_visit_agreed: true` with `Unknown` intent → `Interested`) before the row is updated.
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
├── post_call_extract.py     Groq post-call JSON extraction + normalize_post_call_extraction
├── bot.py                   Stock pipecat outbound example (kept as reference)
├── bot_sts.py               Route B (MR): Gemini Live — Diya, Pyramid Parkland Nxt
├── bot_sts_hi.py            Route B (HI): Gemini Live — Diya, Tesseract Nilaya
├── bot_cascade.py           Route A: Sarvam STT + Groq LLM + Cartesia TTS
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
├── ROADMAP.md               Full vision, architecture, phased roadmap, pricing
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
    Note over Pipecat: On pipeline end: transcript + cost_inr → SQLite; Groq extract if set; POST to n8n URL if set
```

---

## `just` commands reference

| Command                    | What it does                                                                |
| -------------------------- | --------------------------------------------------------------------------- |
| `just dev`                 | Run uvicorn with whatever `BOT_ROUTE` is in `.env` (default `sts`)          |
| `just dev-sts`             | Force `BOT_ROUTE=sts` for this run                                          |
| `just dev-cascade`         | Force `BOT_ROUTE=cascade` for this run                                      |
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
- **First bot utterance is still slow** — watch the `[⏱ Ns]` log lines from `bot_sts.py`. If `parse_telephony_websocket done` takes >1 s, it's Plivo's `start` frame; if `LLMRunFrame queued → first audio` takes >2 s, it's Gemini's WS handshake. Prewarm handles the latter — make sure `_prewarm_gemini` in `server.py` is actually running.

---

## Next development steps

This README mirrors what I'm working on right now. For the longer vision (pricing, multi-tenant architecture, compliance, all future phases), see **[ROADMAP.md](ROADMAP.md)**.

Immediate next deliverables (Phase 0 continuation):

1. ~~SQLite call-log persistence + transcript capture~~ — done (`call_logs` + turn events; see **Call logs and transcripts** above).
2. ~~Cost capture via pipecat's `MetricsFrame`~~ — done (`call_metrics.UsageMetricsTap` → usage columns + `usage_metrics_json`).
3. ~~Post-call extraction~~ — done via **Groq** (`post_call_extract.py`); uses `GROQ_API_KEY` and optional `POST_CALL_MODEL` in `.env`.
4. ~~Outbound n8n webhook + optional STS `cost_inr`~~ — done (`n8n_webhook.py`, `pricing_sts.py`, `call_transcript.py`); configure `N8N_WEBHOOK_URL` and optional Gemini Live USD/M rates in `.env` (see `env.example`).
5. Browser test path via `SmallWebRTCTransport` so we stop burning Plivo minutes during dev.

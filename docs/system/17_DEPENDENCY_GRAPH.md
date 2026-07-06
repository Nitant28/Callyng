# 17 — Dependency Graph

High-level module ownership and import relationships (verified from import
statements). Arrows: **A → B** means A imports/calls B.

---

## Layer diagram

```mermaid
flowchart TB
  subgraph entry [Entry]
    server[server.py]
  end

  subgraph api_layer [API Layer]
    routes[api/routes/*]
    auth[api/auth.py]
    guards[api/guards.py]
    scval[api/script_config_validation.py]
  end

  subgraph core [Core Business]
    dialer[dialer/concurrent_dialer.py]
    pcp[post_call_processor.py]
    ct[call_transcript.py]
    pce[post_call_extract.py]
    sr[script_runtime.py]
    sp[script_prefetch.py]
    tel[telephony.py]
    ph[plivo_hangup.py]
    rec[recording.py]
    n8n[n8n_webhook.py]
  end

  subgraph bots [Voice Bots]
    sts[bot_sts.py]
    cascade[bot_cascade.py]
  end

  subgraph data [Data]
    pg[db/postgres.py]
    redis[db/redis_client.py]
    warmup[db/warmup_state.py]
    sqlite[call_log_db.py]
  end

  server --> routes
  server --> dialer
  server --> sts
  server --> cascade
  server --> ph
  server --> rec
  server --> pg
  server --> redis
  server --> warmup

  routes --> auth
  routes --> guards
  routes --> pg
  routes --> dialer
  routes --> scval

  dialer --> pg
  dialer --> tel
  dialer --> sp
  dialer --> compliance[compliance.py]

  sts --> ct
  sts --> sr
  sts --> call_limits[call_limits.py]
  cascade --> ct
  cascade --> sr

  ct --> pce
  ct --> pcp
  ct --> sqlite
  ct --> redis

  pcp --> pg
  pcp --> n8n
  pcp --> sr

  pce --> post_call_extract_norm[normalize in post_call_extract]

  sp --> pg
  sp --> redis

  ph --> pg
  ph --> pcp

  tel --> aiohttp

  frontend[frontend/src] -.HTTP.-> routes
```

---

## Logic ownership

| Domain | Owner module |
|--------|--------------|
| HTTP routing | `api/routes/*`, `server.py` telephony |
| Auth | `api/auth.py` |
| Multi-tenant SQL | `db/postgres.py` |
| Campaign counters | `db/postgres.increment_campaign_counters`, `reconcile_campaign_counters` |
| Budget/credits | `db/postgres.allocate_*`, `settle_*`, `try_settle_campaign_budget` |
| Outbound dialing | `dialer/concurrent_dialer.py` |
| TRAI compliance window | `compliance.py` |
| Live voice | `bot_sts.py`, `bot_cascade.py` (Pipecat) |
| Transcript capture | `call_transcript.py` |
| Post-call FSM + billing | `post_call_processor.py` |
| LLM extraction | `post_call_extract.py` |
| Outcome vocabulary | `call_outcomes.py` |
| Script resolution | `script_runtime.py`, `script_prefetch.py` |
| Webhooks | `n8n_webhook.py` |
| Recordings | `recording.py` |
| Rate limiting | slowapi in `server.py` → Redis |
| Background task GC | `background_tasks.py` |

---

## Frontend dependencies

```
App.jsx
  → pages/client/*, pages/admin/*
  → contexts (AdminAuth, AdminData, Toast)
  → api/client.js | api/admin.js → axios → FastAPI
```

No shared state with backend except HTTP + localStorage keys.

---

## External services

| Service | Used by |
|---------|---------|
| PostgreSQL | `db/postgres.py` |
| Redis | `redis_client`, warmup, prefetch, locks, slowapi |
| Plivo REST/WS | `telephony.py`, `bot_*`, `recording.py` |
| Google Gemini Live | `bot_sts.py`, prewarm |
| Groq API | `post_call_extract.py`, `bot_cascade.py` |
| Sarvam / Cartesia | `bot_cascade.py` |
| n8n (HTTP out) | `n8n_webhook.py` |
| Cloudflare R2 | `recording.py` (legacy) |

---

## Scripts / static personas

```
sts_scripts/*  ← imported by script_runtime, server prewarm
cascade_scripts/*  ← imported by script_runtime
```

Dynamic configs in `script_configs` table override static modules when
`bot_configs.script_config_id` is set and prefetch runs.

# 03 — Backend Architecture

All line references are to `aakashvani/server.py` unless noted.

---

## 1. `server.py` — the FastAPI application

`server.py` is the single ASGI entry point. It:
1. loads `.env` (`load_dotenv(override=True)`),
2. resolves `BOT_ROUTE` (`sts` | `cascaded`) and **imports the active bot module
   at module-load time** (lines 49–54) to remove per-call import latency,
3. defines the `lifespan` context manager (startup/shutdown),
4. builds the `FastAPI` app with slowapi + CORS middleware,
5. defines telephony endpoints (`/start`, `/answer`, `/ws`, `/plivo-hangup`,
   `/plivo-recording`, `/health`),
6. registers all API routers via `_register_api_routes()` (line 496).

Run: `uvicorn server:app` or `python server.py` (binds `0.0.0.0:7860`, line 500).

---

## 2. FastAPI setup & middleware

```277:266:aakashvani/server.py
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=redis_db.redis_url(),
    in_memory_fallback_enabled=False,
)

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```

- **Rate limiting (slowapi):** global default **100 requests/minute per client IP**
  (`get_remote_address`). Storage is **Redis** (`redis_url()`); there is **no
  in-memory fallback** — if Redis is down, limiter behavior depends on slowapi
  (treat as a hard dependency). Exceeding the limit returns **429**.
- **CORS:** `allow_origins` is an explicit allow-list (lines 260–266):
  `https://admin.aakashvani.ai`, `https://app.aakashvani.ai`,
  `http://localhost:3000`, `http://localhost:5173`, `http://localhost:5174`.
  All methods/headers, `allow_credentials=True`.
  **Frontend implication:** a new frontend must be served from one of these
  origins (or the list must be extended) or browser requests will be blocked.

---

## 3. Routers

Registered in `_register_api_routes()` (lines 485–496):

| Router | Prefix | Auth | File |
|--------|--------|------|------|
| `internal.router` | `/internal` | `require_admin` | `api/routes/internal.py` |
| `internal_script_configs.router` | `/internal/script-configs` | `require_admin` | `api/routes/internal_script_configs.py` |
| `campaigns.router` | `/api/campaigns` | `get_client_from_token` | `api/routes/campaigns.py` |
| `leads.router` | `/api/campaigns/{id}/leads` | `get_client_from_token` | `api/routes/leads.py` |
| `calls.router` | `/api/calls` | `get_client_from_token` | `api/routes/calls.py` |
| `credits.router` | `/api/credits` | `get_client_from_token` | `api/routes/credits.py` |

Telephony endpoints (`/start`, `/answer`, `/ws`, `/plivo-hangup`,
`/plivo-recording`, `/health`) are defined directly on `app` (not in a router)
and are **not authenticated** (they rely on opaque call_ids and Plivo's network
path). See `05_API_REFERENCE.md`.

---

## 4. Dependency injection

FastAPI `Depends` is used for auth and shared resources. Verified in `api/auth.py`:

- `require_admin(request)` — reads `X-Admin-Key` header, compares to
  `os.getenv("ADMIN_API_KEY")`. Raises **403** if missing/wrong. Returns nothing
  meaningful (gate only).
- `get_client_from_token(request)` — reads `Authorization: Bearer <key>`, looks
  up the client row by API key in Postgres, raises **401** if invalid, **503**
  if Postgres unavailable. Returns the **client dict** (used as `client` arg in
  client routes, providing `client_id`, `balance_credits`, `max_concurrent_calls`,
  `name`, etc.).
- `_pool_from_request(request)` — returns `request.app.state.pool` or raises
  **503** if Postgres is not configured.

The DB pool, Redis, aiohttp session, dialer task map, and background-task set are
all stored on **`app.state`** at startup and read inside handlers via
`request.app.state.*`.

---

## 5. Authentication & permissions

| Surface | Mechanism | Failure |
|---------|-----------|---------|
| Admin API `/internal/*` | `X-Admin-Key` == `ADMIN_API_KEY` | 403 |
| Client API `/api/*` | `Authorization: Bearer <client api_key>` → client row | 401 (bad key), 503 (no DB) |
| Telephony webhooks | none (opaque `call_id`/`CallUUID`) | n/a |
| Outbound n8n webhooks | HMAC-SHA256 signature header (n8n verifies) | n/a |

**Permission model is coarse:** there is exactly one admin (shared key) and many
clients. A client can only ever see/modify rows scoped to its `client_id`
(enforced in every query in `db/postgres.py` by passing `client_id`). There is
**no per-client RBAC, no user accounts, no roles** beyond admin-vs-client.
**Not verified from source:** any finer-grained permissions.

---

## 6. Background jobs

Two mechanisms:

### a) Fire-and-forget tasks (`background_tasks.py`)
`spawn_background_task(coro, name)` wraps `asyncio.create_task` and keeps a strong
reference in `app.state.background_tasks` (set) so tasks aren't GC'd mid-flight;
`drain_background_tasks()` awaits them on shutdown. Used for post-call extraction,
webhooks, recording start, etc.

### b) Long-running loops (started in `lifespan`)
- **Stale call_log sweep** (`dialer.maintenance`): runs once at startup, then
  `stale_call_log_loop(pool, interval)` every `STALE_CALL_LOG_SWEEP_SECONDS`
  (default 300). Finalizes `call_logs` stuck `in_progress` past a grace window
  (`live_call_grace_minutes()`). Toggle: `STALE_CALL_LOG_SWEEP_ENABLED`.
- **Per-campaign dialer loops** (`dialer.concurrent_dialer`): one asyncio task per
  running campaign, tracked in `app.state.dialer_tasks[campaign_id]`.
- **Auto-resume** (lines 220–230): at startup, `get_all_running_campaigns()` is
  queried and `start_dialer(...)` is called for each so a process restart resumes
  active campaigns. Host resolved from `DIALER_CALLBACK_HOST` → `NGROK_URL` →
  `localhost:7860`.

---

## 7. Application lifecycle (`lifespan`, lines 157–245)

**Startup (in order):**
1. Pre-import heavy Pipecat audio modules (`LocalSmartTurnV3Analyzer`,
   `SileroVADAnalyzer`) to avoid 5–10s import lag on first call.
2. `init_db(CALL_LOG_DB_PATH)` — create SQLite call-log DB.
3. `pg_db.init_pool()` — Postgres pool (None if `DATABASE_URL` unset → degraded
   single-tenant mode).
4. `redis_db.init_redis()` — Redis pool.
5. Initialize `app.state`: `background_tasks` (set), `dialer_tasks` (dict),
   `session` (aiohttp), `stale_call_log_task`.
6. If pool present: start stale-sweep loop + auto-resume running campaigns.

**Shutdown:**
1. Cancel stale-sweep task.
2. `drain_background_tasks()` — await in-flight post-call work.
3. Close aiohttp session.
4. If **not** under pytest: `close_pool()` + `close_redis()`.

---

## 8. Telephony execution flow (the per-call hot path)

```
POST /start {phone_number, body}
  ├─ generate call_id (uuid4)
  ├─ set_warmup_pending(call_id)              (Redis)
  ├─ asyncio.create_task(_prewarm_gemini(call_id))   ── opens real Gemini Live session, fires dummy turn
  ├─ make_plivo_call(answer_url=/answer?call_id=…&body_data=…, hangup_url=…)
  └─ return {call_uuid, call_id, route}

(callee answers) → Plivo GET /answer?call_id=…&CallUUID=…&body_data=…
  ├─ wait_for_warmup(call_id, timeout=3s)     (Redis)
  ├─ link_call_log_plivo_sid(call_id, CallUUID)   (background)
  ├─ start_plivo_recording(CallUUID, call_id)     (background)
  └─ return <Response><Stream …>wss://…/ws?call_id=…&body=<base64>…</Stream></Response>

Plivo opens WS → /ws?call_id=…&body=<base64>
  ├─ decode body → body_data
  ├─ body_data["_session_call_id"] = call_id
  ├─ pop_prefetched_config(call_id) → body_data["_prefetched_config"]   (Redis)
  ├─ register_pg_context(call_id, body_data["_pg"])                      (Redis)
  ├─ bot_fn = _resolve_bot(body_data)   (route from _pg or module default)
  └─ await bot_fn(runner_args)          → Pipecat pipeline runs the conversation
        finally: if call_log still in_progress → mark not-in-progress + recover_abandoned_session
```

**Key design choices (verified):**
- Prewarm overlaps the Plivo dial latency so the bot greets with no Gemini
  cold-start (`_prewarm_gemini` docstring, lines 110–119).
- `body_data` is passed Plivo→/answer→/ws as URL-encoded then base64 JSON. It
  carries `_pg` (campaign/lead/bot context), `_session_call_id`, and after `/ws`
  the popped `_prefetched_config`.
- The `/ws` `finally` block is the **last-resort cleanup** for abnormal WS
  closure: it marks the call_log finished (0 credits charged) and runs
  `recover_abandoned_session` so the lead doesn't stay stuck in `calling`.

See `09_CALL_LIFECYCLE.md` for the full lifecycle including settlement.

---

## 9. Degraded modes (important for a frontend integrator)

- **No `DATABASE_URL`:** pool is `None`. All `/api/*` and `/internal/*` business
  endpoints return **503** (via `_pool_from_request`). Only telephony + SQLite
  logging works (Phase 0). A new frontend must handle 503 gracefully.
- **Redis down:** rate limiting has no fallback; warmup/prefetch/locks fail. Treat
  Redis as a hard dependency in production.
- **Prewarm failure:** non-fatal; `/answer` proceeds after 3s timeout, bot pays
  its own ~1–2s cold start.

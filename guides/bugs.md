# Production Blockers & Codebase Discrepancies

This document tracks all critical architectural bottlenecks, race conditions, and technical debt items that will cause the system to fail in a scaled production environment (e.g., behind a load balancer, multiple uvicorn workers, or high concurrency). The fixes are ordered by severity.

---

## 1. Severe Billing Overdrafts (CostGuard Race Condition) [CRITICAL] — SOLVED

- **Location:** `dialer/concurrent_dialer.py` and `db/postgres.py`
- **Issue:** The dialer checks if the campaign has at least 2 credits remaining (`check_campaign_budget`). If true, it immediately claims a batch of leads (e.g., `slots = 10`) and fires concurrent calls. Credits are only deducted *after* each call hangs up. A campaign with 2 credits left could easily fire 10 concurrent calls, overdrawing the client's balance heavily.
- **Implementation Plan:** When claiming `N` leads (`slots`), immediately "reserve" a worst-case budget (e.g., 2 credits per lead) by incrementing `campaigns.budget_used_credits` atomically inside the `claim_leads_for_dialer` transaction. When the call ends, the `post_call_processor.py` will refund the 2 reserved credits and add back the *actual* `credits_charged` based on the call duration.

### Resolution (2026-06-17)

Fixed by implementing atomic budget reservation at lead-claim time and net settlement at post-call:

1. **`db/postgres.py`**
   - Added `RESERVE_CREDITS_PER_LEAD` (`2.0`), `adjust_budget_used`, `reserve_campaign_budget`, `release_campaign_budget_reservation`, `settle_call_budget`, and `budget_reserved_from_call_data`.
   - `claim_leads_for_dialer` now locks the campaign row (`FOR UPDATE`), caps `slots` by `floor(remaining / 2)`, and reserves `2 × claimed` credits in the same transaction.
   - `release_stuck_calling_leads` releases one reservation per lead reset to `pending`.
   - `insert_call_log_start` stores `budget_reserved_credits` in `call_data` when provided.

2. **`dialer/concurrent_dialer.py`**
   - Dialer passes `MIN_REMAINING_CREDITS` into `fire_call` so each call log records its reservation.
   - `_release_lead_to_pending` refunds the reservation when no `in_progress` call_log exists (pre-dial failures).

3. **`post_call_processor.py`**
   - All `finalize_call_log` paths now call `settle_call_budget`, applying `budget_used += credits_charged - reserved` instead of charging full credits on top of the reservation.

4. **`tests/test_cost_guard_budget.py`**
   - Regression tests for budget-capped claims, net settlement, early reservation release, and non-dialer paths without false reservation.

---

## 2. Multi-Worker Routing Collapse (Redis Integration) [CRITICAL] — SOLVED

- **Issue:** The codebase relies on process-local Python dictionaries for critical per-call state. In a production deployment running multiple workers (e.g., `uvicorn --workers 4`), inbound HTTP requests from Plivo can be routed to a different worker than the one that originated the call, resulting in catastrophic state loss.
- **Global Solution:** We will introduce **Redis** as the centralized, cross-request state store.

### A. `PREFETCHED_CONFIGS`
- **Location:** `script_prefetch.py` and `dialer/concurrent_dialer.py`
- **Implementation:** Move to a Redis key (`prefetch:{session_call_id}`) with a 5-minute TTL. The dialer `SETEX`s the config, and the WebSocket handler `GETDEL`s it upon connection.

### B. `_PG_CONTEXT`
- **Location:** `call_transcript.py` and `server.py`
- **Implementation:** Move to a Redis key (`pgctx:{session_call_id}`) with a TTL equal to max call duration. Set when `/ws` connects, and read/delete when `call_transcript.py` wraps up.

### C. `_warmup_ready`
- **Location:** `server.py`
- **Implementation:** Remove the in-memory `asyncio.Event`. Replace with a polling `redis.get()` in `/answer`, sleeping briefly up to a 3-second timeout.

### D. Dialer Task Locking (`_active_tasks`)
- **Location:** `dialer/concurrent_dialer.py`
- **Implementation:** Use a Redis distributed lock (`SETNX dialer_lock:{campaign_id}`) refreshed periodically by the dialer loop to ensure only one worker runs a dialer task for a specific campaign.

### E. Global Rate Limiting (`slowapi`)
- **Location:** `server.py`
- **Implementation:** Configure `slowapi` to use a Redis storage backend (`limits.aio.storage.RedisStorage`) so rate limits are globally enforced.

### F. Live Call Monitor (Phase 3)
- **Location:** `ROADMAP.md`
- **Implementation:** Use Redis Pub/Sub to broadcast transcript updates for Server-Sent Events.

### Resolution (2026-06-17)

Fixed by requiring `REDIS_URL` and migrating all multi-worker state to Redis (items A–E). Phase 3 SSE pub/sub (F) remains deferred.

1. **`db/redis_client.py`**, **`db/warmup_state.py`**, **`dialer/dialer_lock.py`**
   - Async Redis pool with required `REDIS_URL`; warmup key polling; distributed dialer lock with token-based refresh/release.

2. **`script_prefetch.py`**
   - `prefetch:{session_call_id}` via `SETEX` / `GETDEL`; `/ws` injects `_prefetched_config` into body for bots.

3. **`call_transcript.py`**
   - `pgctx:{session_call_id}` via `SETEX` / `GETDEL` on register and post-call finalize.

4. **`server.py`**
   - Redis init in lifespan; warmup `pending`→`ready` polling in `/answer`; slowapi `storage_uri=REDIS_URL`.

5. **`dialer/concurrent_dialer.py`**
   - Async `start_dialer` with `SETNX dialer_lock:{campaign_id}`; lock refreshed each loop iteration.

6. **Infrastructure**
   - Redis 7 added to `docker-compose.yml`; `just db-up` starts postgres + redis; `redis` package in `pyproject.toml`.

7. **`tests/test_redis_state.py`**
   - Regression tests for prefetch, pgctx, warmup, dialer lock, and stale prefetch sweep.

---

## 3. Unsafe Background Task Spawning (Data Loss on Restart) [HIGH] — SOLVED

- **Location:** `call_transcript.py`
- **Issue:** Post-call extraction and webhooks are fired using `asyncio.create_task()` without keeping a strong reference. If the server restarts, these pending background tasks will be killed mid-flight, losing the extraction payload.
- **Implementation Plan:** Add `app.state.background_tasks = set()` in `server.py`. Update `call_transcript.py` to inject tasks into this set with an `on_done` callback to automatically remove them. Update the FastAPI lifespan teardown block to `await asyncio.gather(*app.state.background_tasks)` before closing the DB pool.

### Resolution (2026-06-17)

Fixed by tracking post-call background work with strong references and draining on shutdown:

1. **`background_tasks.py`**
   - `bind_background_tasks`, `spawn_background_task`, and `drain_background_tasks` helpers.
   - Tasks are added to a shared set and removed via `add_done_callback` when complete.

2. **`server.py`**
   - Lifespan initializes `app.state.background_tasks = set()` and binds the registry at startup.
   - Teardown calls `await drain_background_tasks()` before closing the HTTP session and DB pool.

3. **`call_transcript.py`**
   - Replaced bare `asyncio.create_task()` calls for `_extract_patch_and_webhook` and `_write_pg_dev_finalize` with `spawn_background_task()`.

4. **`tests/test_background_tasks.py`**
   - Verifies tasks are registered, drained on shutdown, and auto-removed on completion.

---

## 4. Trashing Production Data to Dev Client (Fallback Data Loss) [HIGH] — SOLVED

- **Location:** `call_transcript.py`
- **Issue:** If `_PG_CONTEXT` is missing, the post-call processor falls back to `_write_pg_dev_finalize`, forcibly writing the call log to a hardcoded `_DEV_CLIENT_ID`. The real client will not see the call, will not be billed, and campaign counters will stall.
- **Implementation Plan:** Instead of defaulting to the dev ID, query `SELECT client_id, campaign_id, lead_id FROM call_logs WHERE session_call_id = $1` to fully populate the context and run the production logic. Delete `_write_pg_dev_finalize` entirely.

### Resolution (2026-06-17)

Fixed by recovering campaign context from `call_logs` when Redis `pgctx` is missing, and removing the dev-client fallback:

1. **`call_transcript.py`**
   - Added `resolve_pg_context` (Redis first, `call_logs` fallback via `get_call_log_by_session`), `_pg_context_has_campaign_fields`, and shared `_run_campaign_post_call`.
   - Hangup clears `in_progress` whenever a PG pool and `session_call_id` exist (not only when Redis ctx hits).
   - GROQ and no-GROQ paths route campaign calls through `process_post_call`; n8n webhook only for non-campaign (`POST /start`) calls.
   - Removed `_write_pg_dev_finalize` and `_DEV_CLIENT_ID`.

2. **`db/postgres.py`**
   - Removed unused `finalize_call_log_dev`.

3. **`tests/test_pg_context_recovery.py`**
   - Regression tests for Redis preference, DB recovery from `call_logs`, null-campaign rejection, and dev-finalize removal.

---

## 5. API Validation Fragility & Naming Tech Debt [MEDIUM] — SOLVED

- **Location:** `ROADMAP.md`, `test_call.py`, `bot_configs` table, `api/routes/internal_script_configs.py`
- **Issue:** The database expects routes to be `sts` or `cascaded`, but old env vars and logs use `cascade`. Also, JSON payloads need strict validation to prevent DB corruption.
- **Implementation Plan:** Perform a codebase-wide find-and-replace for `"cascade"` -> `"cascaded"`. Validate `internal_script_configs.py` specifically checks that JSON payloads (`extraction_schema`) are properly formed dicts and not double-stringified `jsonb`.

### Resolution (2026-06-17)

Fixed by canonicalizing route naming and hardening script-config JSON validation:

1. **`api/script_config_validation.py`**
   - Added `normalize_route` (`cascade` → `cascaded` alias).
   - Added `normalize_script_config_payload` with `_ensure_json_dict` / `_ensure_json_list` to reject double-stringified JSON and coerce single-encoded JSON strings before validation.
   - `validate_script_config_payload` now normalizes in place before schema/outcome checks.

2. **`server.py`**, **`bot_cascade.py`**, **`justfile`**, **`.env`**
   - `BOT_ROUTE` and call-log route values use `cascaded` (legacy `cascade` still accepted via `normalize_route`).

3. **`api/routes/internal_script_configs.py`**, **`api/routes/internal.py`**, **`test_call.py`**
   - Create/patch paths normalize route aliases and JSON fields before DB writes.
   - Bot-config admin API accepts legacy `cascade` and stores `cascaded`.

4. **`tests/test_script_config_validation.py`**
   - Regression tests for route alias mapping, JSON string coercion, and double-stringify rejection.

---

# Production Blockers & Codebase Discrepancies

This document tracks all critical architectural bottlenecks, race conditions, and technical debt items that will cause the system to fail in a scaled production environment (e.g., behind a load balancer, multiple uvicorn workers, or high concurrency). The fixes are ordered by severity.

---

## 1. Severe Billing Overdrafts (CostGuard Race Condition) [CRITICAL]

- **Location:** `dialer/concurrent_dialer.py` and `db/postgres.py`
- **Issue:** The dialer checks if the campaign has at least 2 credits remaining (`check_campaign_budget`). If true, it immediately claims a batch of leads (e.g., `slots = 10`) and fires concurrent calls. Credits are only deducted *after* each call hangs up. A campaign with 2 credits left could easily fire 10 concurrent calls, overdrawing the client's balance heavily.
- **Implementation Plan:** When claiming `N` leads (`slots`), immediately "reserve" a worst-case budget (e.g., 2 credits per lead) by incrementing `campaigns.budget_used_credits` atomically inside the `claim_leads_for_dialer` transaction. When the call ends, the `post_call_processor.py` will refund the 2 reserved credits and add back the *actual* `credits_charged` based on the call duration.

---

## 2. Multi-Worker Routing Collapse (Redis Integration) [CRITICAL]

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

---

## 3. Unsafe Background Task Spawning (Data Loss on Restart) [HIGH]

- **Location:** `call_transcript.py`
- **Issue:** Post-call extraction and webhooks are fired using `asyncio.create_task()` without keeping a strong reference. If the server restarts, these pending background tasks will be killed mid-flight, losing the extraction payload.
- **Implementation Plan:** Add `app.state.background_tasks = set()` in `server.py`. Update `call_transcript.py` to inject tasks into this set with an `on_done` callback to automatically remove them. Update the FastAPI lifespan teardown block to `await asyncio.gather(*app.state.background_tasks)` before closing the DB pool.

---

## 4. Trashing Production Data to Dev Client (Fallback Data Loss) [HIGH]

- **Location:** `call_transcript.py`
- **Issue:** If `_PG_CONTEXT` is missing, the post-call processor falls back to `_write_pg_dev_finalize`, forcibly writing the call log to a hardcoded `_DEV_CLIENT_ID`. The real client will not see the call, will not be billed, and campaign counters will stall.
- **Implementation Plan:** Instead of defaulting to the dev ID, query `SELECT client_id, campaign_id, lead_id FROM call_logs WHERE session_call_id = $1` to fully populate the context and run the production logic. Delete `_write_pg_dev_finalize` entirely.

---

## 5. API Validation Fragility & Naming Tech Debt [MEDIUM]

- **Location:** `ROADMAP.md`, `test_call.py`, `bot_configs` table, `api/routes/internal_script_configs.py`
- **Issue:** The database expects routes to be `sts` or `cascaded`, but old env vars and logs use `cascade`. Also, JSON payloads need strict validation to prevent DB corruption.
- **Implementation Plan:** Perform a codebase-wide find-and-replace for `"cascade"` -> `"cascaded"`. Validate `internal_script_configs.py` specifically checks that JSON payloads (`extraction_schema`) are properly formed dicts and not double-stringified `jsonb`.

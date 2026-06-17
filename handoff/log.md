# Admin API Backend Changes — Log

> Date: 2026-06-10
> File modified: `api/routes/internal.py`
> Author: Antigravity CLI

---

## Summary

Added **8 new endpoints** and **expanded 2 existing endpoints** to the admin internal API. All changes are backward-compatible. No database schema changes required — every new route leverages existing DB functions from `db/postgres.py`.

---

## P0 — Critical (unblocked frontend pages)

### 1. `GET /internal/campaigns` — List all campaigns
- **Why**: No way existed to list campaigns from the admin panel. The frontend Campaigns page was completely blocked.
- **Params**: Optional `?client_id=<uuid>` to filter by client. Without it, returns all campaigns (limit 200).
- **DB function**: Calls `pg_db.list_campaigns(pool, client_id)` when filtered, or raw `SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 200` for global list.
- **Response**: `{ "campaigns": [...] }`

### 2. `GET /internal/campaigns/{campaign_id}/leads` — Admin-level lead listing
- **Why**: All lead endpoints (`/api/campaigns/:id/leads`) required client Bearer token. Admin couldn't view leads without pasting a client API key.
- **Params**: `?limit=50&offset=0&status=<optional>`
- **DB function**: Looks up campaign via `get_campaign_admin`, extracts `client_id`, then calls `pg_db.list_campaign_leads()`.
- **Response**: `{ "leads": [...], "total_count": N }`

### 3. `GET /internal/calls/{session_call_id}` — Admin single call detail
- **Why**: `GET /api/calls/:session_call_id` required client Bearer token. Admin couldn't view call transcripts or extraction results.
- **DB function**: `pg_db.get_call_log_by_session(pool, session_call_id)`
- **Response**: `{ "call": { ...full call_log row... } }` including transcript, extraction_json, usage stats, etc.

---

## P1 — High Value (removed friction)

### 4. `PATCH /internal/campaigns/{campaign_id}/start` — Admin can start campaigns
- **Why**: Starting a campaign previously required the client's Bearer token (`PATCH /api/campaigns/:id/start`). Admin had no way to start campaigns.
- **Logic**: Mirrors the client-side `start_campaign` exactly:
  1. Validates status is `draft`, `paused`, or `pausing`
  2. Checks remaining budget ≥ 2 credits
  3. Releases stuck calling leads
  4. Bumps pending retry times to now
  5. Reconciles campaign counters
  6. Sets status to `running`
  7. Starts the dialer via `start_dialer()`
- **Response**: `{ "status": "running", "campaign_id": "...", "released_calling_leads": N, "bumped_pending_retry": N, "counters": {...} }`

### 5. `POST /internal/campaigns/{campaign_id}/reconcile` — One-click counter fix
- **Why**: Counter drift required running raw SQL (`SELECT * FROM leads WHERE campaign_id = '...' GROUP BY status`). Now it's a single button click.
- **DB function**: `pg_db.reconcile_campaign_counters(pool, campaign_id, client_id)`
- **Response**: `{ "campaign_id": "...", "counters": { "total_leads": N, "pending_leads": N, ... } }`

### 6. `POST /internal/campaigns/{campaign_id}/release-stuck` — One-click stuck lead release
- **Why**: Previously CLI-only (`just release-stuck-leads <campaign_id>`). Now the Diagnostics page can trigger it.
- **DB function**: `pg_db.release_stuck_calling_leads(pool, campaign_id, client_id)`
- **Response**: `{ "campaign_id": "...", "released": N }`

### 7. `PATCH /internal/bot-configs/{bot_config_id}` — Expanded patch fields
- **Previously**: Could only update `credits_per_minute` and `active`.
- **Now**: Can also update `name`, `route`, `script_id`, `telephony_number`.
- **Validation**: `route` must be `sts` or `cascaded`, `script_id` must match `/^[a-z][a-z0-9_]*$/`.
- **Also fixed**: Response now uses `pg_db.record_to_dict(row)` instead of raw `dict(row)` for proper UUID/Decimal/datetime serialization.

### 8. `PATCH /internal/clients/{client_id}` — Edit client details
- **Why**: No way to update a client's name, email, or industry after creation.
- **Body**: `{ "name?": str, "contact_email?": str, "industry?": str }` — all optional, only provided fields are updated.
- **Response**: `{ "client": { ...updated client... } }`

---

## Bonus: `GET /internal/bot-configs/{bot_config_id}` — Single bot config detail
- Added for completeness. Useful for campaign creation confirmation and detail views.
- **Response**: `{ "bot_config": { ...full row... } }`

---

## Other Improvements

- **Moved `from dialer.concurrent_dialer import start_dialer, stop_dialer`** to top-level imports instead of inline imports inside `cancel_campaign_admin`. Cleaner and avoids repeated import overhead.
- **Added `Query()` validation** to `limit` and `offset` params on `GET /internal/calls` (was plain `int`, now `Query(50, ge=1, le=200)` and `Query(0, ge=0)`).
- **Added `PatchClientBody`** Pydantic model for client editing.

---

## Route Summary (complete)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/internal/clients` | Create client |
| GET | `/internal/clients` | List all clients |
| GET | `/internal/clients/:id` | Get single client |
| **PATCH** | **`/internal/clients/:id`** | **Edit client details** ← NEW |
| PATCH | `/internal/clients/:id/status` | Suspend/reactivate |
| PATCH | `/internal/clients/:id/credits` | Add/deduct credits |
| GET | `/internal/clients/:id/credits` | Credit transaction history |
| GET | `/internal/clients/:id/webhooks` | List webhooks |
| POST | `/internal/bot-configs` | Create bot config |
| GET | `/internal/bot-configs` | List all bot configs |
| **GET** | **`/internal/bot-configs/:id`** | **Get single bot config** ← NEW |
| PATCH | `/internal/bot-configs/:id` | Update bot config **(expanded)** |
| POST | `/internal/campaigns` | Create campaign |
| **GET** | **`/internal/campaigns`** | **List campaigns** ← NEW |
| GET | `/internal/campaigns/:id` | Get single campaign |
| PATCH | `/internal/campaigns/:id` | Update campaign settings |
| PATCH | `/internal/campaigns/:id/stop` | Stop (pause) campaign |
| **PATCH** | **`/internal/campaigns/:id/start`** | **Start campaign** ← NEW |
| PATCH | `/internal/campaigns/:id/cancel` | Cancel campaign |
| **POST** | **`/internal/campaigns/:id/reconcile`** | **Reconcile counters** ← NEW |
| **POST** | **`/internal/campaigns/:id/release-stuck`** | **Release stuck leads** ← NEW |
| **GET** | **`/internal/campaigns/:id/leads`** | **List leads (admin)** ← NEW |
| POST | `/internal/webhook-configs` | Upsert webhook |
| GET | `/internal/calls` | List all calls |
| **GET** | **`/internal/calls/:session_call_id`** | **Get single call** ← NEW |
| GET | `/internal/scripts` | List available scripts |
| GET | `/internal/stats` | Dashboard stats |
| GET | `/internal/health` | Extended health check |

---

## Addendum: Search Parameters (2026-06-10 14:57)

Added `?search=<name>` query param to all three list endpoints so the frontend can power searchable autocomplete dropdowns. The admin types a partial name and results filter instantly — no more copy-pasting UUIDs.

| Endpoint | Search fields matched |
|----------|----------------------|
| `GET /internal/clients?search=tech` | `name`, `industry`, `contact_email` (case-insensitive) |
| `GET /internal/bot-configs?search=intake` | `name`, `script_id` (case-insensitive) |
| `GET /internal/campaigns?search=renewal` | `name` (case-insensitive) |

Also added `?client_id=` filter to `GET /internal/bot-configs` so the frontend can fetch only bot configs belonging to a specific client (used when creating campaigns — the bot config dropdown filters as you select a client).

## Addendum: Client-Side Search Parameters (2026-06-10 15:03)

Added `?search=<term>` query params to the client-facing APIs as well.
- `GET /api/campaigns?search=foo` - Matches `name` (case-insensitive)
- `GET /api/calls?search=bar` - Matches `session_call_id` or `outcome` (case-insensitive ILIKE in Postgres)

---

## Addendum: Major Frontend & Client-Side Updates (2026-06-10 17:10)

Implemented layout refinements, currency calculations, compliance guards, and dark-mode styling fixes.

### 1. Dark-Mode Enhancements & Style Fixes
- **Forms & Inputs:** Standardized inputs, dropdowns, and option lists for both the Admin **Create Campaign** modal and the Client **Add/Edit Lead** modals using the molten color scheme (`bg-[#1A1C24]`, `border-[#2A345E]`, and `text-molten-text`).
- **Drawers:** Refined contrast, labels, and borders on **Call Details** and **Campaign Details** sliding drawer views.
- **Scroll Alignment:** Fixed the footer in `AdminLayout.jsx` to prevent it from overlaying elements or forcing scrolling errors.

### 2. Client Security & Data Copying Tools
- **Authentication Loop Patch:** Modified the Axios interceptor in `client.js` to avoid overriding headers unless the request context is missing an `Authorization` token, resolving client loop login bugs after API-key regeneration.
- **Copiable Identifiers:** Added copy-to-clipboard elements for client IDs, API keys, and campaign UUIDs with immediate visual confirmation feedback.

### 3. Compliance and Confirmation Banners
- **IST Compliance Window Alert:** Added a live-updating banner comparing local UTC time offsets to standard IST (`+5:30`) to warn clients when dialing is outside the TRAI hours (9:00 AM – 9:00 PM IST).
- **Mandatory Resume Lock:** Intercepted campaign resume controls and added a detailed confirmation modal detailing rates, concurrency settings, and TRAI warnings before calls are dispatched.

### 4. Admin Layout Navigation & Cleanups
- **Sidebar Naming:** Changed **"Settings"** to **"Bot Configuration"** to align with backend functionality.
- **Footer Updates:** Changed copyright year string to **2026** and removed placeholder support sections.
- **Header Updates:** Cleared duplicate user settings and profile symbols from the nav block.

## Addendum: Dynamic Script & Post-Call Config Planning (2026-06-15)

Planned a comprehensive database-driven CMS for bot scripts and post-call processing to replace the hardcoded Python files (`sts_scripts/`, `cascade_scripts/`). The plan is stored in `guides/plan.md`.

**Key Architectural Decisions:**
- **Zero Latency Hot-Path:** `bot_sts.py` and `bot_cascade.py` will NOT query the DB. Instead, `concurrent_dialer.py` will prefetch the config, render the prompts using `string.Template.safe_substitute`, and store it in an in-memory dictionary `PREFETCHED_CONFIGS[call_id]`.
- **Snapshotting:** To guarantee consistency during mid-call edits, the post-call extraction rules are snapshotted into `call_logs.call_data` at call start.
- **Rollback:** `script_config_revisions` table will support append-only rollback for safety.
- **Phase 0 Hotfix (Completed):** Fixed a massive bug where `bot_sts.py` and `bot_cascade.py` ignored `_pg.script_id` entirely. They now explicitly read `pg.get("script_id")` before falling back to env vars, enabling multi-tenant script routing on a single server immediately.

## Addendum: Dialer Prefetch (Step 3 — 2026-06-15)

Implemented database-driven script prefetch in the dialer hot path per `guides/plan.md` build order step 3.

**Files added/changed:**
- `script_prefetch.py` — `PREFETCHED_CONFIGS` registry, `build_lead_dict`, `render_script_config`, `sweep_stale_prefetched_configs`
- `db/postgres.py` — `get_script_config(pool, script_config_id, client_id)`
- `dialer/concurrent_dialer.py` — prefetch register in `fire_call` when `bot_config.script_config_id` is set; `pop` on dial/insert failure
- `dialer/maintenance.py` — stale prefetch sweep piggybacks on `run_stale_call_log_sweep`
- `tests/test_script_prefetch.py` — unit tests for lead dict filtering, template render, sweep

**Runtime behavior:**
- `script_config_id` **null** (current dev seed): unchanged — no prefetch, bots still use `.py` modules via `_pg.script_id`
- `script_config_id` **set**: dialer fetches `script_configs`, renders `$lead_name` templates, stores in `PREFETCHED_CONFIGS[call_id]` before Plivo dial (Step 4 will consume via `pop()` in bots)

## Addendum: Bot Loaders (Step 4 — 2026-06-15)

Wired tier-1 prefetch consumption into both Pipecat bots. Full 3-tier resolution is now live end-to-end.

**Files added/changed:**
- `script_runtime.py` — `StsRuntime` / `CascadeRuntime`, `resolve_sts_runtime`, `resolve_cascade_runtime`, gemini/vad/tool helpers
- `bot_sts.py` — uses `resolve_sts_runtime()` instead of direct importlib
- `bot_cascade.py` — uses `resolve_cascade_runtime()`; removed dead `bot_config` reference in `bot()`
- `tests/test_script_runtime.py` — prefetch hit/miss, route guard, helper unit tests

**Resolution order at `/ws` connect:**
1. `pop_prefetched_config(_session_call_id)` when dialer registered a CMS config
2. `_pg.script_id` → `importlib` (campaign calls without `script_config_id`)
3. `STS_SCRIPT` / `CASCADE_SCRIPT` env fallback (Phase 0 `/start` dev path)

## Addendum: Post-Call Snapshot (Step 5 — 2026-06-15)

Persists a compact post-call config freeze in `call_logs.call_data.post_call_snapshot` at call start.

**Files changed:**
- `script_runtime.py` — `build_post_call_snapshot*`, `maybe_write_post_call_snapshot`, `schedule_post_call_snapshot_write`
- `db/postgres.py` — `insert_call_log_start(..., call_data=)`, `patch_call_log_post_call_snapshot`
- `dialer/concurrent_dialer.py` — CMS path writes snapshot at dial time
- `bot_sts.py` / `bot_cascade.py` — module path schedules async snapshot patch at WS connect
- `tests/test_script_runtime.py`, `tests/test_post_call_snapshot.py`

**Write paths:**
- **CMS (`script_config_id` set):** dialer passes snapshot into `insert_call_log_start`
- **Module path:** bot patches snapshot idempotently after `resolve_*_runtime` if missing

**Note:** Post-call extraction still reads live `extraction_schema` from runtime until Step 6.

## Addendum: Post-Call Engine (Step 6 — 2026-06-15)

At hangup, post-call processing now reads the frozen `call_logs.call_data.post_call_snapshot` when present.

**Files changed:**
- `script_runtime.py` — `parse_post_call_snapshot`, `PostCallSnapshot`, `get_default_post_call_snapshot`, `outcome_buckets`
- `post_call_extract.py` — `apply_normalization_rules`, `normalize_post_call_extraction(..., normalization_rules=)`
- `post_call_processor.py` — snapshot-driven outcome buckets; `process_post_call(..., post_call_snapshot=)`
- `n8n_webhook.py` — `outcome_to_event(outcome, event_map=None)`
- `call_transcript.py` — loads snapshot at hangup for extract + processor
- `scripts/cli.py` — `rerun-extraction` prefers snapshot schema
- `tests/test_post_call_engine.py`

**Fallback paths (unchanged behavior when snapshot absent):**
- Extraction uses bot closure `extraction_schema` and legacy Pyramid normalization patches
- Lead transitions and webhooks use hardcoded outcome sets / event map
- Applies to Phase 0 SQLite-only calls, module-path race before snapshot patch, and legacy rows

## Addendum: CLI test_call (Step 7 — 2026-06-15)

End-to-end CMS test dial without campaign dialer or admin UI.

**Files added/changed:**
- `test_call.py` — root CLI: resolve script_config, throwaway lead, `fire_call`, poll loop
- `db/seed/dev_tenant.sql` — sandbox bots (`...0004` STS, `...0005` cascaded) + campaign (`...0006`, 500 credits)
- `dialer/concurrent_dialer.py` — `fire_call(..., dial_phone=)` returns `session_call_id`
- `justfile` — `just cms-call <script-config-id> <phone> [route]`
- `tests/test_test_call.py`

**Sandbox UUIDs (dev seed):**
- STS bot: `00000000-0000-4000-8000-000000000004`
- Cascaded bot: `00000000-0000-4000-8000-000000000005`
- Campaign: `00000000-0000-4000-8000-000000000006`

**Usage:**
```bash
just dev          # server must be running (holds PREFETCHED_CONFIGS)
just cms-call <script-config-uuid> +919... sts
```

**vs `just call`:** Phase 0 `POST /start` uses env module scripts, no `lead_id` FK, no CMS prefetch/snapshot. `test_call.py` exercises the full production dial path.

**Prerequisites:** `DATABASE_URL`, Plivo creds, `NGROK_URL`, a `script_configs` row for the given UUID.

## Addendum: Admin API (Step 8 — 2026-06-15)

CRUD + validation + rollback for `script_configs` under `/internal/script-configs/*`.

**Files added/changed:**
- `api/script_config_validation.py` — schema/outcome validation, `default_template()`, `build_config_snapshot()`
- `api/routes/internal_script_configs.py` — all admin endpoints
- `db/postgres.py` — `create_script_config`, `update_script_config`, `list_script_config_revisions`, `rollback_script_config`, `list_script_configs`
- `server.py` — router registration
- `tests/test_script_config_validation.py`, `tests/test_script_config_api.py`

**Example:**
```bash
curl -sS -H "X-Admin-Key: $ADMIN_API_KEY" \
  "http://localhost:7860/internal/script-configs/template?route=sts" | jq .

curl -sS -X POST -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"client_id":"00000000-0000-4000-8000-000000000001", ...}' \
  http://localhost:7860/internal/script-configs
```

**Validation:** Non-summary configs require `intent_status` enum values to map bijectively to `outcome_terminal` / `outcome_retry` / `outcome_callback` with no overlap.

## Addendum: Data Migration (Step 9 — 2026-06-16)

Migrated module-based scripts (`sts_scripts/*`, `cascade_scripts/*`) to DB-backed `script_configs` via a new idempotent CLI.

**Files added/changed:**
- `script_module_export.py` — exports module scripts into `script_configs` payload shape
- `scripts/migrate_script_configs.py` — discovers active `bot_configs`, creates/updates `script_configs`, links `script_config_id`
- `tests/test_script_module_export.py`, `tests/test_migrate_script_configs.py`
- `justfile` — `just migrate-scripts`

**Migration command:**
```bash
uv run python scripts/migrate_script_configs.py
```

**Modes:**
- `--dry-run`: export + validate only
- `--verify-only`: validate all discovered module exports only
- `--force-update`: update existing `script_configs` rows from module export

**Scope and behavior:**
- Targets all active `bot_configs` rows (`DISTINCT client_id, route, script_id`)
- Creates missing `script_configs` rows and links `bot_configs.script_config_id`
- Re-runs are idempotent by default (skip existing rows, still ensure links)
- Keeps `.py` scripts as fallback path; no file deprecation in Step 9

**Verification path:**
1. `uv run python scripts/migrate_script_configs.py --dry-run`
2. `uv run python scripts/migrate_script_configs.py`
3. `just cms-call <script-config-uuid> +91... sts`

## Addendum: Frontend Script Configs CMS & Bot Config Changes (2026-06-16)

Implemented the full frontend for the Script Configs CMS and updated the Bot Configs UI to consume the new system.

**Admin Script Configs (`AdminScriptConfigs.jsx`):**
- Built a comprehensive CMS interface with Tabbed Navigation (Core, Prompts, Cascade, Post-Call, Advanced).
- Supported creating and editing `script_configs`.
- Implemented "Create Template" to dynamically pull reference defaults (`default_template` from `sts_scripts/pyramid_bilingual.py` and `sts_scripts/pyramid_extraction.py`).
- Added a full Revision History sliding drawer with the ability to view JSON diffs and instantly "Rollback" to any prior version.
- Added a "Deploy Bot" workflow directly from the Script Templates list, which creates a `bot_configs` entry natively linked to the script template.
- Fixed React uncontrolled input warnings by strictly binding text/number inputs and textareas.
- Fixed an `Objects are not valid as a React child` crash by correctly unpacking FastAPI 422 validation arrays into string messages using an `extractError` utility.

**Admin Bot Configs (`AdminBotConfigs.jsx`):**
- Removed all legacy manual override inputs (Model, Voice, Temperature, VAD settings, Webhook Overrides, Scripts).
- Admin is now *forced* to select an existing Script Template from a dropdown. All configuration flows through the `script_config_id`.
- Bot Configuration UI now correctly sends only `client_id`, `name`, `route`, `script_id`, `script_config_id`, `telephony_number`, and `credits_per_minute` to the backend.

**Backend adjustments (`db/postgres.py`, `api/routes/internal_script_configs.py`):**
- Made `client_id` optional on `GET /internal/script-configs` for global admin views.
- Modified the dynamic `default_template` endpoint to natively extract boilerplate text from Python scripts (`pyramid_bilingual.py`) using `LeadContext` injection to preserve accurate parameterization.
- Added pruning logic to limit script config revisions to 5 per script template, preventing runaway database bloat from excessive edits.

## Addendum: E2E React UI, Test Cleanup & Auth Patches (2026-06-17)

Implemented crucial frontend UX refinements, database test isolation patterns, and expanded admin client dashboard controls.

### 1. Admin Authentication UX Patch
- **Form State Normalization:** Fixed a UI refresh bug on [AdminLogin.jsx](file:///home/satyam/aakashvani/frontend/src/pages/admin/AdminLogin.jsx) where clicking "Retry Authentication" after a wrong password cleared the typed password.
- **Typing Auto-Clear:** Typing a new character in the password field while in an `'error'` state now automatically resets the status to `'idle'`, clearing error states and restoring the "Authenticate" submit button.
- **Enter Key Submission:** The form submission is now allowed in the `'error'` state, permitting immediate retry by pressing Enter.
- **Improved Retry Button:** Clicking the "Retry Authentication" button now focuses and selects the existing typed key, allowing the operator to correct typos without starting from scratch.

### 2. Automated Test Database Cleanup
- **Post-run Cleanup Fixture:** Added an asynchronous PostgreSQL transaction cleanup block inside the session-scoped `setup_globals` fixture in [conftest.py](file:///home/satyam/aakashvani/tests/conftest.py).
- **Exact Data Pruning:** At the end of every `pytest` run, the cleanup hook automatically prunes all test-generated clients, bot configurations, campaigns, leads, call logs, webhook configs, credit transactions, and script configs while preserving the default seeded test data (dev client `...0001`, sandbox campaigns, and bots).
- **Constraint Order Enforcement:** Structured the cleanup sequence (`call_logs` -> `leads` -> `campaigns` -> `bot_configs` -> client child records -> `clients`) to completely prevent PostgreSQL foreign key constraint violations.

### 3. Integrated Client-Level Campaigns & Creation Panel
- **Client Ledger Campaigns Tab:** Added a dedicated **Campaigns** tab to the Admin Client Detail panel in [AdminClientDetail.jsx](file:///home/satyam/aakashvani/frontend/src/pages/admin/AdminClientDetail.jsx).
- **Context-Aware Creation Modal:** Admins can now create campaigns directly inside a client's page. The modal automatically prefills and disables the client selection to prevent mistakes, showing only bot configs belonging to that specific client.
- **Rich Analytics & Settings Drawer:** Built a sliding drawer panel to inspect campaign leads pipeline statistics and settings details directly.
- **In-flight Action Handles:** Supported pausing (`stop`) and `cancel` actions on client-level campaigns, automatically refreshing the client's credit balances (deducting budgets or processing refunds) upon execution.
- **Visual Grid Alignment:** Positioned the new tab content cleanly inside the React `<div className="relative min-h-[400px]">` Tabs Container, resolving a visual layout vertical gap.

---

## Addendum: Backend Hardening, Redis Integration & Multi-Worker State Sync (2026-06-17)

Implemented robust state management, billing guarantees, validation sanitization, and background task safety to support high-concurrency production deployments across multiple workers.

### 1. Atomic Budget Reservation (CostGuard Race Condition Fix)
- **Problem:** Campaign budget validation was prone to race conditions. The dialer checked for $\ge 2.0$ credits before claiming $N$ leads, but since credits were only charged *after* calls hung up, a campaign with 2 credits could launch 10 parallel calls, resulting in massive overdrafts.
- **Solution:** 
  - Claiming leads now locks the campaign row via `FOR UPDATE`, checks the balance, and reserves a worst-case budget (2 credits per lead) by incrementing `campaigns.budget_used_credits` atomically inside the transaction.
  - Dialer functions record the reservation in `call_logs.call_data`.
  - On hangup, `post_call_processor.py` computes the final cost and executes `settle_call_budget` to refund the reservation and deduct the actual usage.
  - Pre-dial failures immediately release the reservation.

### 2. Redis Central State Store for Multi-Worker Support
- **Problem:** Critical state like script prefetch maps, Plivo query-contexts, and startup warmup indicators were stored in local memory dictionaries. Under a multi-worker server setup (e.g. 4 uvicorn workers behind a load balancer), subsequent requests routed to a different worker would fail.
- **Solution:** Added Redis image to `docker-compose.yml` and required `REDIS_URL` in `.env`.
  - **Script Prefetch:** Moved to `prefetch:{session_call_id}` keys in Redis with a 5-minute TTL.
  - **Plivo Context (`_PG_CONTEXT`):** Moved to `pgctx:{session_call_id}` keys in Redis.
  - **Warmup Status:** `/answer` endpoint polls `redis.get("warmup_state")` up to 3 seconds, removing the in-memory asyncio Event.
  - **Distributed Dialer Locking:** Implemented a Redis-based distributed lock (`dialer_lock:{campaign_id}`) with a token-based refresh mechanism so only one worker can process a campaign's dialer loop at a time.
  - **Global Rate Limiting:** Configured `slowapi` to utilize `limits.aio.storage.RedisStorage`.

### 3. Lifespan Teardown & Strong References for Background Tasks
- **Problem:** Post-call extraction and webhooks were spawned via bare `asyncio.create_task()`. On server restart, these tasks would be killed mid-flight, losing customer data.
- **Solution:**
  - Created `background_tasks.py` to maintain strong references in a global set.
  - Registered callbacks automatically remove tasks from the set upon completion.
  - Wired `await drain_background_tasks()` in FastAPI's lifespan teardown to guarantee all active webhook and extraction tasks complete before database and redis connections close.

### 4. PG Context Recovery Fallback
- **Problem:** If Redis context was lost/expired, calls fell back to writing to a hardcoded developer client ID, losing the tenant context.
- **Solution:** Deleted the developer client ID fallback. Replaced with database lookup `resolve_pg_context` querying `call_logs` directly to restore context dynamically.

### 5. API Route Normalization and JSON Hardening
- **Route Naming:** Standardized all route references from legacy `cascade` to `cascaded` across server configurations, CLI scripts, and tests (with backward-compatible mapping).
- **JSON Sanitization:** Hardened `api/script_config_validation.py` to reject double-stringified JSON and automatically parse JSON string formats to prevent database serialization errors.

### 6. Script Template Searching & Filtering
- **Admin Search Bar:** Added template search functionality inside `AdminScriptConfigs.jsx` to filter template rows by script identifier or client name, ensuring fast navigation as the template library grows.


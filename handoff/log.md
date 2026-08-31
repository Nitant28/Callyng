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
- `scripts/test_call.py` — root CLI: resolve script_config, throwaway lead, `fire_call`, poll loop
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

**vs `just call`:** Phase 0 `POST /start` uses env module scripts, no `lead_id` FK, no CMS prefetch/snapshot. `scripts/test_call.py` exercises the full production dial path.

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

---

## Addendum: `guides/optimization.md` — Spec & Implementation Audit Trail (2026-06-27)

`guides/optimization.md` is the single source of truth for the call-outcome / lead-state optimization work (Workstreams A–H). Header status: **All workstreams (A–H) complete.** The doc defines the canonical five-status model (§1), per-workstream specs (§2–§14), sequencing (§10), verification checklist (§11), and an implementation audit log (§15). Below mirrors what §15 records as shipped.

### Document structure (key sections)

| Section | Purpose |
|---|---|
| §1 | Canonical lead statuses, outcome vocabulary, status × outcome matrix |
| §2–§8 | Workstreams A–G specs (state machine, Plivo mapping, DNC removal, extractor de-hardcoding, indexes, frontend cards, repo cleanup) |
| §14 | Workstream H — admin script/post-call UI guidance copy |
| §15 | Implementation log — what was actually shipped (audit trail) |

### §15.1 — Workstream A: Post-call state machine unification ✅

Funnelled all five divergent lead-status mutation paths through `resolve_post_call_transition` (answered) and `resolve_lead_retry_or_failed` (non-answers/abandoned).

| Path | After |
|---|---|
| Unanswered Plivo hangup | campaign `retry_delay_minutes` + `outcome_from_plivo_status`; normalized outcome on `call_logs` + `leads` |
| Orphaned dials | `retry_delay_minutes=0`, `base_outcome="Carrier_Failed"` |
| Stuck/exhausted housekeeping | `resolve_lead_retry_or_failed` with campaign delay / `Max_Attempts_Reached` |

**Files:** `db/postgres.py`, `plivo_hangup.py`, `post_call_processor.py` (`_SHORT_CALL_SECONDS = 90`, `_SHORT_CALL_RETRY_CAP_MIN = 1`), `dialer/concurrent_dialer.py`. **Review fix:** `settle_unanswered_call` sync order — resolve outcome before writing to both `call_logs` and `leads`.

### §15.2 — Workstream B: Outcome normalization (Plivo path) ✅

- **New:** `call_outcomes.py` — `TERMINAL`, `RETRY`, `FAILURE`, `outcome_from_plivo_status()`.
- Plivo mapping: `busy→Busy`, `no-answer/cancel→No_Answer`, `reject→Rejected`, `failed→Carrier_Failed`, else `Unknown`.
- **Review fix:** `reject` corrected from `Call_Rejected` to `Rejected`.

### §15.3 — Post-call extraction reconcile fix ✅

- **`post_call_extract.py`:** removed early return on `_CALLBACK_CONFIRM_RE` that blocked property-interest branch; priority: property confirmed + no time → `Interested`, explicit time → `Callback_Requested`.
- Fixed `tests/test_post_call_engine.py` Hindi STT conflict transcript failure.

### §15.4 — Tests added/updated (A/B)

- `tests/test_call_outcomes.py` (new), `tests/test_post_call_engine.py` updated for 3-tuple `resolve_lead_retry_or_failed`.

### §15.5 — Verification (2026-06-27)

- `rg "'Unanswered'" db/postgres.py` → zero matches ✅
- Campaign retry delay flows via `plivo_hangup.py` ✅
- **151 passed** with Postgres up.

### §15.6 — Workstream C: DNC removal ✅

- Migration `007_remove_dnc.py`; `dnc_leads` column dropped; `dnc` leads → `completed` / `Not_Interested`.
- Backend: removed DNC from `post_call_processor.py`, `db/postgres.py` counter deltas, `api/routes/leads.py` transitions, `scripts/cli.py`.
- Frontend: removed DNC badge/counters from `CampaignDetail.jsx`, `AdminClientDetail.jsx`, `AdminCampaigns.jsx`.
- `fix_leads.py` deleted; `env.example` scrubbed; docs sanitized.

### §15.7 — Sequencing status table

All workstreams A–H marked ✅ Complete in the doc's status table.

### §15.8 — Workstream F: Frontend status cards & outcome labels ✅

- `CampaignDetail.jsx` — five-card grid (Pending, Calling, Callback Scheduled, Completed, Failed) with `OUTCOME_LABELS` / `friendlyOutcome()` for all §1.2 outcomes; no `Unanswered` / DNC references.

### §15.9 — Workstream H: Admin outcome drag-and-drop editor ✅

- `AdminScriptConfigs.jsx` — `OutcomeDragDropEditor` (move-not-copy drag, unmapped/stale warnings, summary-mode hide, raw JSON escape hatch, save blocked when mapping incomplete).

### §15.10 — Workstream D: Extractor de-hardcoding ✅

- `PYRAMID_NORMALIZATION_RULES` in `sts_scripts/pyramid_extraction.py`; migration `008_pyramid_normalization_rules`; stripped domain heuristics from `post_call_extract.py`.
- **Behavior change:** when `normalization_rules` is non-empty, generic `site_visit_agreed` / `callback_time` fallback no longer runs (explicit config wins).

### §15.11 — Workstream E: Performance / indexes ✅

- Migration `009_calllog_indexes.py` — `idx_call_logs_lead_live`, `idx_call_logs_lead_ended`.
- Base schema `001_initial.sql` parity; dialer 30s cooldown gate; `guides/admin_script_guide.md` created.

### §15.12 — Workstream G: Repo cleanup ✅

- 14 root ad-hoc scripts deleted; `test_call.py` → `scripts/test_call.py`; `pyproject.toml` `testpaths = ["tests"]`.
- `tests/test_settle_unanswered_call.py` added; **153 passed**.

### §14 — Workstream H guidance copy (spec, in-doc)

Defines inline help for Extraction Schema, Outcome buckets, Normalization Rules, Outcome Event Map, plus worked healthcare example (§14.6). Acceptance: six post-call fields editable, drag-and-drop partition UI, validation errors inline near bucket editors.

---

## Addendum: Workstreams E / G / H — Dialer Hot-Path, Repo Cleanup & Frontend Polish (2026-06-28)

Completed the dialer hot-path index optimization (Workstream E), repo/seed cleanup (Workstream G), and the Admin Script Configs frontend UX gaps (Workstream H), plus scripting-guide documentation. Status tracked in `guides/optimization.md` §15.7 / §15.11.

### 1. Database Indexes (Workstream E — hot-path optimization)
- Added two partial indexes targeting the dialer's most expensive `NOT EXISTS` subqueries in `claim_leads_for_dialer`, eliminating sequential scans:
  - `idx_call_logs_lead_live` — leads with active calls (`WHERE in_progress = TRUE`).
  - `idx_call_logs_lead_ended` — leads with recently completed calls (wrap-up grace query).
- Added in both a new migration `alembic/versions/009_calllog_indexes.py` (`down_revision = 008_pyramid_normalization_rules`, `IF NOT EXISTS`, `downgrade()` drops them) and the base schema `db/schema/001_initial.sql` for fresh installs.

### 2. Dialer Cooldown Gate (Workstream E)
- **`dialer/concurrent_dialer.py`:** the claim-failure branch previously called `release_stuck_calling_leads` on every ~5s tick, generating heavy multi-CTE transactions. Added a module-level 30s per-campaign cooldown (`_RELEASE_STUCK_COOLDOWN_S = 30.0`) throttling ongoing polling. The cold-start path stays unconditional; the per-campaign key is cleaned up in `stop_dialer` (no leak).

### 3. Admin Script Configuration Guide
- Added `guides/admin_script_guide.md` covering all 8 internal script-config API endpoints, field references for all 30+ config attributes, deep dives into `extraction_schema` / `normalization_rules` / outcome mapping / `cascade_live_tools`, and how Workstream D made explicit config win over normalization fallbacks.

### 4. Status Tracking
- **`guides/optimization.md`:** marked Workstream E complete and appended the implementation audit log to §15.11 (§15.7 reflects E & G complete).

### 5. Workstream H — Frontend Polish (`AdminScriptConfigs.jsx`)
- **Inline error feedback:** moved validation errors from the truncated modal footer to a full-width inline message below the outcome mapping editor (removed the duplicate footer display).
- **Auto-tab switching:** `saveConfig` now switches the user to the Post-Call tab and shows inline validation when the backend reports unmapped `intent_status` fields.
- **Defaults helper copy:** added text clarifying how untouched JSON fields behave as null vs an explicitly saved empty structure (`[]`).

### 6. Seed Data & UI Filtering (Workstream G)
- **`db/seed/dev_tenant.sql`:** repointed dev sandbox bots to live scripts — `…0004 → pyramid_hi`, `…0005 → prowave` (was `cli_sandbox_sts` / `cli_sandbox_cascade`).
- **`api/routes/internal_script_configs.py`:** dropped the `cli_sandbox*` hiding filter now that the seeded script references are valid active scripts.
- **Repo cleanup:** removed orphaned root-level ad-hoc scripts; moved `test_call.py` → `scripts/test_call.py` (kept `just cms-call` + `tests/test_test_call.py` working).

### 7. Scripting Guide Enhancements (`ScriptingGuideModal.jsx`)
- Added a 5-step post-call lifecycle section (Transcript → Extraction → Normalization → Routing → Update) into the UI guide.
- Fixed stale `pyramid_hindi` references → `pyramid_hi`.

### 8. Tests & verification
- **Added `tests/test_settle_unanswered_call.py`** (exhaustion/retry mapping coverage).
- Full suite: **153 passed**; `npm run build` clean; `EXPLAIN ANALYZE` confirmed `idx_call_logs_lead_live` is used for the dialer concurrency check; `db-seed` works with the repointed `dev_tenant.sql`.

---

## Addendum: Post-Attempt Callback Visibility (Early Disconnect) (2026-06-28)

Reworked the post-call lead state machine so that **every inconclusive dial attempt routes to `callback_scheduled` (purple card), never back to `pending` (yellow)**. Pending now strictly means "awaiting first dial." Added a new `Early_Disconnect` outcome for short callee hangups and made the manual "reset to pending" override behave like a fresh lead. Full plan in `/home/satyam/.cursor/plans/early_disconnect_callback_3434bd48.plan.md`.

### Core UX contract change
- **Pending (yellow):** never tried — `attempts = 0` fresh upload, or a lead manually reset while paused.
- **Callback Scheduled (purple):** tried + inconclusive — shows outcome badge + when we redial.
- Dialer claim SQL, wrap-up grace, budget reservation, and lock semantics are **untouched** — `claim_leads_for_dialer` already claims both `pending` and `callback_scheduled`, and the `calling → callback_scheduled` counter delta already existed.

### 1. Step 0 — `normalization_rules` load bug fix
- **`call_transcript.py`:** post-call extraction loaded `norm_rules = rules` where `rules = norm_rules` (self-reference, always `None`). Now correctly reads `rules = snapshot.get("normalization_rules")`, so per-bot normalization rules are actually applied at hangup.

### 2. Step 1 — Retry outcomes → `callback_scheduled`
- **`db/postgres.py` `resolve_lead_retry_or_failed`:** returns `callback_scheduled` (was `pending`) for under-max-attempts retries; still returns `failed` + `Max_Attempts_Reached` at the cap.
- **`db/postgres.py` `settle_unanswered_call`:** unanswered Plivo calls (Busy/No_Answer/Rejected/Carrier_Failed) now set `scheduled_callback_at` and increment the `calling → callback_scheduled` counter.
- **`db/postgres.py` `release_stuck_calling_leads`:** stuck-lead release now routes to `callback_scheduled` (renamed internal `pending_ids` → `callback_ids`, sets `scheduled_callback_at`).
- **`post_call_processor.py` `_lead_transition`:** retry branch and the fallback branch return `callback_scheduled` with `scheduled_callback_at = next_attempt_at`.
- **`post_call_processor.py` `resolve_post_call_transition`:** the callee-hangup override returns `callback_scheduled` (was `pending`).

### 3. Step 2 — `apply_early_disconnect_policy`
- **`post_call_processor.py`:** new pure function + `EARLY_DISCONNECT_MAX_SECONDS = 30`. Fires when the callee hung up, duration < 30s, and intent is weak (`""` or `Unknown`), returning `Early_Disconnect`.

### 4. Step 3 — `Early_Disconnect` vocabulary + webhook
- **`call_outcomes.py`:** `Early_Disconnect` added to the `CALLBACK` frozenset.
- **`script_runtime.py`:** added to `DEFAULT_OUTCOME_CALLBACK`.
- **`api/script_config_validation.py`:** added to `_DEFAULT_OUTCOME_CALLBACK`.
- **`n8n_webhook.py`:** `outcome_to_event` maps `early_disconnect → lead_callback`.

### 5. Step 4 / 4b — Wiring + scheduling + short-call cap
- **`post_call_processor.py` `process_post_call`:** applies the early-disconnect policy (reordered so `attempts`/`max_attempts`/`retry_delay`/`call_log`/`callee_hangup` are computed first), rewriting `outcome` and `extraction_json["intent_status"]` before transition resolution. Policy is wired here only (recovery delegates to `process_post_call`).
- **`_lead_transition` callback bucket:** `Callback_Requested` with a parsed time → that time; `Early_Disconnect` → `now + retry_delay_minutes`; organic `Callback_Requested` without a time → `+4h`.
- **Short-call cap:** condition changed from `new_status == "pending"` to `new_status == "callback_scheduled"` AND (retry-bucket outcome OR `Early_Disconnect`); now caps `next_at` and keeps `sched_cb` in sync (1-minute cap when duration < 90s).

### 6. Step 5 — Migration + extraction enum
- **`alembic/versions/010_early_disconnect_outcome.py`:** appends `Early_Disconnect` to `outcome_callback` for existing pyramid script_configs (`pyramid_bilingual`, `pyramid_hi`, `pyramid_mr`, `prowave`); idempotent, no-op downgrade.
- **`sts_scripts/pyramid_extraction.py`:** added `Early_Disconnect` to the `intent_status` enum values and description.

### 7. Step 6 — API enrichment
- **`db/postgres.py` `list_campaign_leads`:** added a `LEFT JOIN LATERAL` on the most recent ended `call_log` exposing `last_call_duration_seconds`, `last_call_outcome`, `last_call_ended_at`, and `last_hangup_source` (from `plivo_hangup_json`). Qualified existing `status`/`name`/`phone`/`created_at` filters with the `l.` alias.

### 8. Step 7 — Frontend transparency
- **`frontend/src/pages/client/CampaignDetail.jsx`:** added `Early_Disconnect` → "Hung up early" to `OUTCOME_LABELS`; new `formatCallbackTiming` + `buildCallbackBadgeLabel` helpers render "Callback in Xm / Xh / at …". Callback card now shows the outcome + timing badge (e.g. `Hung up early (8s) · Callback in 10 min`). Pending card shows **"Awaiting first call"** when `attempts === 0`, else `Pending · n/max`. Release-stuck toast wording updated to "callback scheduled".
- **`frontend/src/components/shared/CallTranscriptDrawer.jsx`:** added a post-call summary strip (duration, hangup source via `hangupSourceLabel`, outcome via `outcomeLabel`) shown for completed calls.
- **`frontend/src/components/shared/ScriptingGuideModal.jsx`:** updated outcome-routing copy — retry-bucket outcomes and `Early_Disconnect` map to `callback_scheduled`, not `pending`.

### 9. Step 8b — Manual status override (pause + edit lead) = fresh reset
- **`db/postgres.py` `update_lead_status_manual`:** new `reset_to_fresh` flag; when resetting to pending it sets `attempts = 0`, `outcome = NULL`, `extraction = '{}'::jsonb`.
- **`api/routes/leads.py` `change_lead_status`:** passes `reset_to_fresh=(target == "pending")`. A tried lead manually moved to pending becomes a clean "Awaiting first call" lead. (Manual edits remain blocked while a campaign is `running`.)
- **`api/routes/leads.py` `change_lead_status` (follow-up guard):** rejects manual `→ callback_scheduled` when `attempts >= max_attempts` with HTTP 409 and message to move to Pending first. Prevents a lead landing on the purple Callback card with a scheduled time but never dialable (`claim_leads_for_dialer` requires `attempts < max_attempts`). Recovery path: `pending` reset clears attempts → `callback_scheduled` allowed again.
- **Test:** `tests/test_client_api_edge.py::test_manual_callback_blocked_at_max_attempts` (409 at cap; recovery via `failed → pending` reset → `callback_scheduled`).

### 10. Tests + docs
- **Added:** `tests/test_call_transcript_norm_rules.py`, `tests/test_early_disconnect_policy.py`, `tests/test_early_disconnect_post_call.py`.
- **Updated:** `tests/test_post_call_engine.py` and `tests/test_phase2.py` (retry → `callback_scheduled`, callee-hangup → `callback_scheduled`, `Early_Disconnect` webhook mapping); `tests/test_settle_unanswered_call.py` (asserts `callback_scheduled` + `scheduled_callback_at`); `tests/test_client_api_edge.py` (`test_manual_pending_resets_attempts`).
- **Docs:** `guides/admin_script_guide.md` (outcome bucket descriptions).

### 11. `guides/optimization.md` — canonical model & target-design updates

Spec sections updated to reflect Post-Attempt Callback Visibility (§15 implementation log not yet extended with §15.13):

**§1.1 Lead statuses — pending / callback semantics rewritten:**
| Status | Doc meaning (after update) |
|---|---|
| `pending` | Awaiting **first dial only** (`attempts = 0`, or manually reset while paused) |
| `callback_scheduled` | **Tried, inconclusive** — shows outcome + when we call back |

**§1.2 Outcome vocabulary — routing model changed:**
- Added `Early_Disconnect` under **Callback → `callback_scheduled`** (short callee hangup, no intent).
- Retry-bucket outcomes (`Busy`, `No_Answer`, `Rejected`, `Carrier_Failed`, `Wrong_Requirement`, `Unknown`) now documented as mapping to **`callback_scheduled` status** (outcome label preserved on card; **not** `pending`).
- Clarifies outcome buckets in `script_configs` do not need to move — runtime maps retry-bucket outcomes to `callback_scheduled` card visibility.

**§1.3 Status × outcome matrix — UI contract:**
| Status | Allowed outcomes (after update) |
|---|---|
| `pending` | `NULL` only (never called, or manual reset with `attempts = 0`) |
| `callback_scheduled` | `Callback_Requested`, `Early_Disconnect`, `Busy`, `No_Answer`, `Rejected`, `Carrier_Failed`, `Wrong_Requirement`, `Unknown` |
- Added note: **Manual → `pending` while paused** resets `attempts = 0`, clears `outcome` and `extraction`.

**§2.2 Target design — `resolve_lead_retry_or_failed` example updated:**
```python
return "callback_scheduled", ts + timedelta(minutes=retry_delay_minutes), base_outcome
```
(was `pending` in the original spec text)

**§11.3 manual smoke (still references pre-callback-card model):** smoke checklist in §11.3 still says `pending(Busy/No_Answer)` — **stale**; actual behavior is `callback_scheduled` per §1.1–1.3. Update when next editing the doc.

**§14.4 outcome-bucket guidance copy (still stale):** §14.4 still says `outcome_retry` → Pending card; implementation and §1.2 now route retry-bucket outcomes to Callback Scheduled. Update when next editing the doc.

### Migration & verification
- Run `alembic upgrade head` (applies `010_early_disconnect_outcome`) before deploying.
- Verified: **165 tests passed**; `npm run build` succeeded.

---

## 2026-07-28 — Production STS Voice Cut Remediation & Performance Tuning

> Date: 2026-07-28  
> Scope: Audio pipeline hot path, database connection pool, API load isolation, slowapi rate limiting, loguru logging sink, dialer loop performance  
> Author: Antigravity CLI  
> Branch: `feature/export-and-outcome-dropdown`  

### Summary

A comprehensive code audit and production server log analysis identified event-loop stalls, database connection pool exhaustion, duplicate writes, rate limit drops, and un-isolated dashboard API polling as the root causes of production voice cuts. All 16 fixes across 4 phases were implemented and verified with zero regression.

### Root Causes & Fixes Delivered

#### Phase 0 — Telephony & Server Foundation (Emergency Fixes)
1. **Telephony Webhook Rate Limit Exemptions (`server.py`)**: Added `@limiter.exempt` to `/start`, `/answer`, `/plivo-hangup`, `/plivo-recording`, and `/health`. Prevents default 100/min SlowAPI rate limiter from returning 429 to Plivo webhooks (which dropped call streams).
2. **Non-blocking Loguru Logging (`logging_setup.py`, `server.py`)**: Removed loguru default sink; added non-blocking background thread sink with `enqueue=True`, `backtrace=False`, `diagnose=False`. Stops 30KB prompt dumps from stalling the event loop when logging to Docker pipes. Added `--no-access-log` to Uvicorn startup.
3. **Gemini Pre-warm Session Reduction (`server.py`)**: Gated Gemini pre-warming behind `GEMINI_PREWARM` flag (defaults to `0`/disabled). Halves concurrent Gemini Live sessions and requests-per-minute quota usage while keeping Redis warmup signaling intact.

#### Phase 1 — Audio Pipeline & Transcript Optimization
4. **Removed `STSTranscriptionCatcher` (`bot_sts.py`)**: Deleted `STSTranscriptionCatcher` from the pipeline. Stopped duplicate user turn DB writes and lazy python import overhead between `user_aggregator` and `llm`.
5. **Non-blocking Turn Events (`call_transcript.py`)**: `TranscriptBuffer.register()` appends turns to in-memory `self.turns` synchronously on turn events.
6. **Debounced Snapshot Replace (`call_transcript.py`, `db/postgres.py`)**: Replaced per-turn `transcript || $1::jsonb` concatenation with `replace_transcript(pool, session_call_id, transcript)` debounced to 2.0s background flushes (`_PG_WRITE_LIVE_TIMEOUT_S = 2.0`). Eliminates write amplification and row-lock contention.

#### Phase 2 — Dashboard API Load Relief & Pagination
7. **Slim `list_call_logs` Projection (`db/postgres.py`, `api/routes/calls.py`)**: Modified `list_call_logs` to select explicit scalar columns, excluding multi-megabyte `transcript`, `call_data`, `extraction_json`, and `plivo_hangup_json` blobs. Reduced default GET `/api/calls` limit from 2000 to 100.
8. **Denormalized Counters & TTL Cache (`db/postgres.py`)**: `get_campaign_outcome_stats` reads denormalized status counters from `campaigns` table and caches outcome aggregations for 10 seconds (`_STATS_CACHE_TTL_S = 10.0`).
9. **Frontend Polling Optimization (`useDashboardData.js`)**: Updated frontend polling interval from 2s/5s to 5s (running) / 15s (idle); capped list requests to `limit: 100`; removed per-campaign call list fan-out.

#### Phase 2.5 — Dialer Loop & Database Pool Timeouts
10. **Dialer Loop Query Optimization (`dialer/concurrent_dialer.py`)**: Uses denormalized `calling_leads` counter instead of per-iteration `COUNT(*)`; throttles `terminalize_exhausted_leads` to every 30s; increases idle sleep intervals (5s / 10s).
11. **PostgreSQL Statement Timeouts (`db/postgres.py`)**: Added `SET statement_timeout = '15s'` and `SET idle_in_transaction_session_timeout = '15s'` to asyncpg `_init_connection`. Prevents pathological dashboard queries from holding pool connections indefinitely.

#### Phase 3 — Logging, Warmup & SQLite Optimization
12. **Truncated Prompt Logging (`script_runtime.py`)**: Replaced 30KB prompt text dumps at `INFO` level with length + MD5 hash, keeping full instruction at `DEBUG`.
13. **Warmup State Race Condition Fix (`db/warmup_state.py`)**: `wait_for_warmup()` only deletes Redis key when status is `"ready"`, allowing late pre-warms to complete safely.
14. **Gemini Error Handlers & CWC Target (`bot_sts.py`)**: Registered `on_error` and `on_completion_timeout` handlers; raised default `GEMINI_CWC_TRIGGER_TOKENS` from 20,000 to 32,000.
15. **Memory Optimization (`server.py`)**: Skipped pre-loading `LocalSmartTurnV3Analyzer` and `SileroVADAnalyzer` when `BOT_ROUTE == "sts"`. Saves resident memory on VPS.
16. **SQLite Optimization (`call_log_db.py`)**: Removed `init_db()` from `insert_call_log` hot path; configured `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`.

### Files Modified

- `server.py`
- `logging_setup.py` (new)
- `bot_sts.py`
- `call_transcript.py`
- `db/postgres.py`
- `db/warmup_state.py`
- `call_log_db.py`
- `script_runtime.py`
- `dialer/concurrent_dialer.py`
- `api/routes/calls.py`
- `frontend/src/client/hooks/useDashboardData.js`
- `tests/test_call_transcript_finalize.py`

### Test Suite Verification

- **Full Pytest Suite**: **191 passed, 6 skipped** in 23.40s.


---

## Addendum: Multi-Protocol Post-Call Extraction (2026-07-19)

> Date: 2026-07-19
> Scope: post-call LLM transport only (cascade live LLM in `bot_cascade.py` unchanged)
> Author: Cursor agent

### Summary

Post-call extraction no longer hardcodes Groq. `POST_CALL_PROVIDER` selects one of three HTTP protocols — OpenAI-compatible chat completions (default), Anthropic Messages, or Gemini `generateContent` — while prompt build, JSON parse, and normalization stay shared. Existing Groq deployments keep working with no `.env` change.

### Config

| Variable | Role |
|---|---|
| `POST_CALL_PROVIDER` | `openai` (default) \| `anthropic` \| `gemini` |
| `POST_CALL_MODEL` | model id (default still `llama-3.3-70b-versatile`) |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | openai provider; base defaults to `https://api.groq.com/openai/v1` |
| `GROQ_API_KEY` | openai key fallback; still required for cascaded live LLM |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` | anthropic provider |
| `GOOGLE_API_KEY` | gemini provider (reuse STS key) |

**Key resolution (openai):** explicit `api_key` arg → `OPENAI_API_KEY` → `GROQ_API_KEY`.

### 1. `post_call_extract.py` — provider dispatch

- Removed sole hard-coded `GROQ_CHAT_COMPLETIONS_URL` path.
- Added helpers: `post_call_provider()`, `post_call_llm_configured()`, `post_call_missing_key_message()`, `_resolve_openai_key` / `_resolve_provider_key`.
- Transport split (all via existing `aiohttp`, no new deps):
  - `_chat_openai_compat` — `POST {base}/chat/completions`, Bearer auth
  - `_chat_anthropic` — `POST {base}/v1/messages`, `x-api-key` + `anthropic-version: 2023-06-01`
  - `_chat_gemini` — Google `generateContent` with `systemInstruction` + query `key=`
- Shared `_post_json` + per-provider response content extractors; log strings provider-neutral (`LLM HTTP …`).
- `extract_post_call` signature unchanged; missing key still returns `(None, None, model)` (skip).

### 2. Call-site gates (no longer Groq-only)

- **`call_transcript.py`:** runs extraction when `post_call_llm_configured()`; skip log uses `post_call_missing_key_message()`.
- **`api/routes/internal_script_configs.py`:** 503 uses the same helper (names the active provider’s key).
- **`scripts/cli.py` (`rerun-extraction`):** same gate before calling `extract_post_call`.

### 3. Env + docs

- **`env.example`:** `POST_CALL_PROVIDER`, commented `OPENAI_BASE_URL` / `ANTHROPIC_*`, usage notes for OpenRouter / Anthropic / Gemini.
- **`docs/system/15_ENVIRONMENT_SETUP.md`:** table rows for the new vars; cascade still documented as `GROQ_API_KEY`-dependent.

### 4. Tests (CI-hardened)

- **Added** `tests/test_post_call_providers.py`:
  - Patches `_post_json` (not `ClientSession`) so tests are stable under CI’s session-scoped asyncio loop.
  - Autouse fixture clears provider-related env keys so local `.env` cannot leak.
  - Covers openai (custom base + Groq fallback + key preference), anthropic body/headers, gemini URL/body, unsupported provider, missing-key skip, HTTP error propagation, `post_call_llm_configured` per provider.
- **Updated** `tests/test_script_config_api.py` extraction test env patch to set `POST_CALL_PROVIDER=openai` alongside `GROQ_API_KEY`.

### Example `.env` snippets

```bash
# OpenRouter (or any OpenAI-compatible endpoint)
POST_CALL_PROVIDER=openai
OPENAI_API_KEY=sk-or-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
POST_CALL_MODEL=meta-llama/llama-3.3-70b-instruct

# Anthropic
POST_CALL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
POST_CALL_MODEL=claude-sonnet-4-20250514

# Gemini
POST_CALL_PROVIDER=gemini
GOOGLE_API_KEY=...
POST_CALL_MODEL=gemini-2.0-flash

# Unchanged Groq default
# POST_CALL_PROVIDER unset → openai + Groq base URL
GROQ_API_KEY=gsk_...
```

### Verification

- `tests/test_post_call_providers.py`: **9 passed** (including under `asyncio_default_test_loop_scope=session`).
- Ruff clean on touched modules/tests.
- Full suite still requires Postgres/Redis via session `setup_globals` (same as existing CI).

---

## 2026-07-21 — Deep Audit Remediation (calling pipeline)

> Date: 2026-07-21
> Scope: bot STS/cascade, call finalize, server lifespan, script_runtime, call_limits
> Author: Cursor agent
> Plan: `.cursor/plans/deep_audit_fix_plan_07c2afc5.plan.md` (not edited)

### Summary

Line-by-line audit of the calling pipeline found 20 issues (1 false positive skipped). All confirmed bugs and cleanups were implemented with production/CI constraints: no new deps, no migrations, no new env vars. Local gate: `uvx ruff check .` clean; `uv run pytest -x --tb=short` → **184 passed, 6 skipped**.

### Architecture context (Bug #1)

`TranscriptBuffer()` was constructed without `session_call_id`, so `_maybe_pg_append` always early-returned. Live per-turn Postgres transcript writes were dead; only finalize-time SQLite/PG paths ran. Crash mid-call lost incremental turns. Docs (`guides/aakash_arch.md`) assume turn-by-turn PG growth for live polling.

---

### P0 — Real bugs

#### 1. Pass `session_call_id` to `TranscriptBuffer`
- **Files:** `bot_sts.py`, `bot_cascade.py`
- Hoist `session_call_id = body.get("_session_call_id")` at start of `run_bot()`.
- `TranscriptBuffer(session_call_id=session_call_id)`.
- Removed duplicate `pg = body.get("_pg") or {}` (audit #13).
- **STSTranscriptionCatcher:** replace orphan `asyncio.create_task(_pg_write(...))` with `spawn_background_task(..., "sts_transcription_pg")`.

#### 2. Protect webhook on non-post-call-LLM path
- **File:** `call_transcript.py`
- Added `_schedule_call_completed_webhook(payload)` — wraps `send_call_completed_webhook` in try/except + `spawn_background_task(..., "call_completed_webhook")`.
- Bare `await send_call_completed_webhook` on the skip-LLM branch can no longer abort `_on_pipeline_finished`.

#### 3. Gemini prewarm strong reference
- **File:** `server.py`
- Extended import: `from background_tasks import bind_background_tasks, drain_background_tasks, spawn_background_task`.
- `/start`: `spawn_background_task(_prewarm_gemini(call_id), f"prewarm_gemini:{call_id}")` instead of discarding `asyncio.create_task`.

#### 4. Non-blocking SQLite insert
- **File:** `call_transcript.py`
- `row_id = await asyncio.to_thread(insert_call_log, ...)` inside `_on_pipeline_finished` so sync sqlite3 does not block the event loop.

---

### P1 — Medium

#### 5. `row_id = -1` silent extraction loss
- **Files:** `call_log_db.py`, `call_transcript.py`
- Added `get_row_id_by_session(session_call_id)` (calls `init_db` first).
- `_resolve_sqlite_row_id(row_id, session_call_id)` recovers via lookup when insert fails.
- `update_call_log_extraction`: early-return + warning when `row_id <= 0`.

#### 6. Remove debug Plivo phone log
- **File:** `server.py` — deleted `logger.info(f"DEBUG PLIVO_PHONE_NUMBER=...")` on every `/start`.

#### 7. Safe WebSocket close
- **File:** `server.py` `/ws` bot error handler — nested try/except around `await websocket.close()` so already-closed WS does not mask the original error.

#### 8. Redis init fail-fast logging
- **File:** `server.py` lifespan — wrap `init_redis()` in try/except, log that `REDIS_URL` is required for rate limiting + call state, then re-raise (still required; not optional like PG).

#### 9. Cancel dialers on shutdown
- **Files:** `dialer/concurrent_dialer.py`, `server.py`
- Added `shutdown_all_dialers(app)` — cancel all `app.state.dialer_tasks`, gather with `return_exceptions=True`, clear `_active_tasks`.
- Called in lifespan teardown before `drain_background_tasks()`.

#### 10. Dangling coroutine on RuntimeError
- **File:** `script_runtime.py` `schedule_post_call_snapshot_write`
- Capture `coro = _run()`; on `RuntimeError` from `spawn_background_task`, call `coro.close()` (not `_run.close()` — `_run` is the function).

#### 11. Cascade ImportError logging
- **File:** `script_runtime.py` `_load_cascade_script` — mirror STS loader: log + re-raise on `ImportError`.

#### 12. Safe numeric coercion
- **File:** `script_runtime.py`
- Added `_safe_int` / `_safe_float` (warn + default on bad input).
- Used in `build_gemini_vad` and `_sts_from_prefetch` (`gemini_temperature`).

---

### P2 — Code quality

| # | Change |
|---|--------|
| 13 | Duplicate `pg` reads removed (with #1) |
| 14 | Redundant `import json` inside `_coerce_extraction_override` removed |
| 15 | Redundant `from db import postgres as pg_db` inside `call_transcript` functions removed; use module-level import |
| 16 | `assert resolved_ctx is not None` → explicit None check + log + return |
| 17 | `_pg_context_from_call_log`: parse `call_data` string via `json.loads` instead of substring match for `is_test_call` |
| 18 | **Skipped** — `time` import is used (`time.perf_counter` in finalize) |
| 19 | Removed no-op `except asyncio.CancelledError: raise` in `call_limits.py` (×3) |
| 20 | Removed unused `ScheduledCall = ScheduledCallLimits` alias |

---

### Tests added / extended

| File | Coverage |
|------|----------|
| `tests/test_transcript_buffer.py` (new) | PG append skipped without sid; append with sid (user + assistant) |
| `tests/test_call_transcript_finalize.py` (new) | Webhook spawn swallows failures; row_id recovery; invalid row_id guard; `get_row_id_by_session` |
| `tests/test_background_tasks.py` | Strong-reference / registry retain regression |
| `tests/test_script_runtime.py` | Invalid VAD/float fallbacks; cascade ImportError |
| `tests/test_concurrent_dialer_unit.py` | `shutdown_all_dialers` |

### Files touched (implementation)

- `bot_sts.py`, `bot_cascade.py`
- `call_transcript.py`, `call_log_db.py`
- `server.py`, `script_runtime.py`, `call_limits.py`
- `dialer/concurrent_dialer.py`
- tests listed above

### Not touched (by design)

- `pyproject.toml` / `uv.lock` — no new dependencies
- Alembic migrations — none
- `tests/conftest.py` session fixture — left alone
- Unrelated local `justfile` diff (`migrate-scripts` after `db-seed`) left as-is

### Deploy / rollback notes

- Merge to `main` triggers CI then VPS restart; dialers cancelled cleanly via #9.
- Bug #1 starts writing live PG transcript turns on new processes.
- Rollback: `git revert` + redeploy; no migration rollback.

---

## 2026-07-21 — Dial-test 404 after `just db-reset` (ops note)

### Symptom

```
POST /internal/script-configs/895f47c4-088b-4399-bd90-b51dbdeafc30/dial-test?client_id=00000000-0000-4000-8000-000000000001
→ 404 Not Found
```

### Root cause (not a missing route)

- Route exists: `api/routes/internal_script_configs.py` → `POST /script-configs/{id}/dial-test`, mounted via `server.py` `include_router(internal_script_configs.router)`.
- Handler raises `HTTPException(404, "script_config not found or inactive")` when `pg_db.get_script_config(..., active=TRUE)` returns None.
- `just db-reset` does `docker compose down -v` then migrate + seed + `migrate-scripts` — **new UUIDs** every time.
- ID `895f47c4-...` was a **stale pre-reset** id still held in Admin UI `editingConfig` state / open tab.

### DB state after reset (seed client)

| id | script_id | route |
|----|-----------|-------|
| `d1ccfc04-8b37-4166-943e-f0456ea47789` | prowave | cascaded |
| `eea5f09c-ed97-42ec-a2b9-ce020d7f2512` | pyramid_hi | sts |

Query confirmed `895f47c4-...` → 0 rows.

### Fix for operators

1. Hard-refresh admin Script Configs (or reopen page).
2. Select a listed config (`pyramid_hi` / `prowave`) so dial-test uses a current id.
3. Optional curl smoke against `eea5f09c-...` with `X-Admin-Key`; 404 should stop (503 only if Plivo env missing).

### Takeaway

404 on dial-test after reset almost always means **stale script_config UUID in the UI**, not a broken route or failed seed. Always re-list configs after `db-reset`.

---

## Addendum: Silence / Inactivity Watchdog (`45s` default) (2026-07-28)

Implemented an automated 45-second silence / dead-air watchdog across both STS (Gemini Live) and Cascade (Silero VAD) calling routes.

### Architectural Summary & Routing:
- **`CallEndCoordinator` ([`call_limits.py`](file:///home/satyam/aakashvani/call_limits.py)):**
  - Managed by `SILENCE_TIMEOUT_SECONDS` environment variable (default: `45.0` seconds; set to `0` to disable).
  - Watchdog arms (`_silence_armed = True`) only after the bot speaks its initial opening line (`note_bot_speaking(True)`), preventing pre-greeting silence (WebSocket / prewarm setup delays) from prematurely canceling calls.
- **`SilenceActivityTap` ([`call_limits.py`](file:///home/satyam/aakashvani/call_limits.py)):**
  - Placed between `user_aggregator` and `llm` in `bot_sts.py` and `bot_cascade.py`.
  - Intercepts upstream `TranscriptionFrame`s emitted by Gemini Live (`llm → user_aggregator → input`) and invokes `coordinator.note_activity()` to reset the 45s silence timer without disarming pending goodbye/end_call hangups.
  - Exclusively handles upstream `TranscriptionFrame`s; VAD speech start/stop boundaries remain strictly owned downstream by `BotSpeechEndGate` (placed after `transport.output()`).
- **Configuration & Documentation:**
  - `SILENCE_TIMEOUT_SECONDS=45` added to `env.example`.
  - Unit tests added in `tests/test_voice_cut_fixes.py` (pre-greeting grace period, dead-air hangup, upstream transcript activity reset, downstream transcript isolation, default `45s`).

---

## Addendum: Nitant Update — Lead Schema, Custom Export & Admin Improvements (2026-08-08)

Implemented schema-driven Excel/CSV lead management, custom metadata export, unified turn tracking, admin client filtering, and diagnostic automation.

### 1. Lead Schema & Dynamic Excel/CSV Import & Export
- **Visual Lead Schema Builder**: Added `LeadSchemaBuilder.jsx` component to `frontend/src/admin/components/` allowing admins to visually construct lead schemas (field keys, display labels, types, required flags, and CSV column aliases).
- **Schema-Driven Lead Validation**: Updated `lead_upload/validator.py` and `lead_upload/parser.py` to validate uploaded lead files (Excel `.xlsx`, `.xls`, and `.csv`) dynamically against configured script lead schemas.
- **Enhanced Lead Export (`/api/campaigns/{campaign_id}/leads/export`)**: Updated `api/routes/leads.py` to export both standard columns (`Name`, `Phone`), custom lead schema metadata fields, and system columns (`Status`, `Outcome`, `Attempts`, `Turns`, `Interested`, `Last Call Duration`, `Last Call`, `Created Time`, `Updated Time`). Enforced text formatting (`@`) on phone columns in exported Excel workbooks.

### 2. Unified Turn Count Tracking
- **PostgreSQL LATERAL Query**: Updated `db/postgres.py` (`list_campaign_leads`) to compute transcript turns (`CASE WHEN jsonb_typeof(transcript) = 'array' THEN jsonb_array_length(transcript) ELSE 0 END`) and expose both `turns` and `transcript_turns` aliases.
- **Frontend Turn Utilities**: Enhanced `frontend/src/client/utils/computeTurns.js` with robust multi-fallback resolution (`turn_count`, `turns`, `last_call_turns`, `transcript_turns`, and direct transcript array turn parsing).
- **UI Integration**: Updated `CallTranscriptDrawer` and `CampaignDetail` lead views to render real-time turn count badges.

### 3. Dashboard Metrics & Caching
- **Dashboard Refactoring**: Updated `api/routes/dashboard.py` for conversion rate and outcome metric calculations.
- **In-Memory Stat Caching**: Added short TTL caching (`_STATS_CACHE_TTL_S = 10.0`) in `db/postgres.py` to reduce database query load during high-frequency poll traffic.

### 4. Admin Portal Filtering & UI Polish
- **Admin Customer Filter**: Added `AdminCustomerFilter.jsx` component (`frontend/src/admin/components/AdminCustomerFilter.jsx`) to filter campaigns, calls, and script configs by customer/client across the admin portal.
- **Admin Styling**: Redesigned `AdminOverview` styling and aligned top toolbar layouts across `AdminBotConfigs`, `AdminCampaigns`, and `AdminScriptConfigs`.

### 5. Automated Diagnostic Scripts
- Added diagnostic and automated testing scripts in `scripts/`:
  - `_concurrent_live_campaign.py`
  - `_diag_post_call.py`
  - `_e2e_agent_call.py`
  - `_e2e_preflight.py`
  - `_e2e_prowave_campaign.py`
  - `_plivo_numbers.py`
  - `_redial_e2e.py`
  - `_set_plivo_from.py`

---

## Addendum: Started-Minute Setup Billing + Admin Telephony/Bot Split (2026-08-15)

Replaced flat per-dial setup with **Plivo-style setup per started minute**, and surfaced a **Total = Telephony + Bot** breakdown in admin.

### Formula (locked)

```
started_minutes = max(1, ceil(seconds / 60))   # unanswered 0s → 1
telephony       = started_minutes × fixed_start_credits
bot             = (seconds / 60) × credits_per_minute
total           = telephony + bot
```

Duration stays pro-rata (no `math.ceil` on talk time). Each component quantized HALF_UP to 4 dp from the unrounded product; campaign/wallet still 2 dp.

Worked checks at ₹3.50/min + ₹0.60 setup:

| Duration | Started mins | Telephony | Bot | Total |
| --- | --- | --- | --- | --- |
| 0s (busy / unanswered) | 1 | 0.6000 | 0 | **0.6000** |
| 15s | 1 | 0.6000 | 0.8750 | **1.4750** |
| 59s | 1 | 0.6000 | 3.4417 | **4.0417** |
| 65s (1m5s) | 2 | 1.2000 | 3.7917 | **4.9917** |
| 125s (2m5s) | 3 | 1.8000 | 7.2917 | **9.0917** |

Reservation at claim: `R = (setup + rate) × BILLING_RESERVE_MINUTES` → ₹8.20 at ₹3.50/min (was ₹7.60 flat-setup model).

Unchanged rules: never-Plivo / orphans / test calls = ₹0; rates snapshotted onto `call_data` at dial; mid-flight rate changes do not rewrite in-flight charges.

### 1. Billing math — `billing.py`

- `compute_call_charge` now returns `started_minutes`, `setup_charge` (telephony), `duration_charge` (bot), plus `billed_minutes` / `credits_charged` / `budget_amount`.
- `reservation_credits(setup, rate)` = `2 × (setup + rate)` quantized to 0.01.

### 2. Persist telephony/bot split — no new migration

- `finalize_call_log` (`db/postgres.py`) merges `setup_charge` + `duration_charge` into `call_logs.call_data` JSONB.
- `settle_unanswered_call` writes the same (`duration_charge = 0`).
- `list_call_logs` selects `(call_data->>'setup_charge')::numeric` and `duration_charge` as top-level fields.
- `record_to_dict` backfills those keys from `call_data` when present on detail fetches.
- `post_call_processor` threads the split through `_finalize_call_log_and_settle_budget`.

Old rows without the keys: UI shows Total from `credits_charged`; Telephony/Bot show **—**.

### 3. Admin stats — `GET /internal/stats` + Overview KPIs

- API adds `telephony_credits_today` and `bot_credits_today` (SUM of the JSONB keys for today).
- `AdminOverview.jsx`: keeps **Credits Burned** as total; adds **Telephony** and **Bot** KPI cards.
- KPI grid CSS uses `auto-fit` so five cards wrap cleanly.

### 4. Admin call drawer — `AdminCalls.jsx`

Drawer metadata tiles: **Duration**, **Total**, **Telephony**, **Bot** (list Cost column still the total).

### 5. Labels & preview

- `AdminBotConfigs.jsx` / `AdminScriptConfigs.jsx`: setup labeled **₹ / started min**; preview uses `max(1, ceil(s/60)) × setup + (s/60) × rate` (2 min @ ₹4 + ₹0.60 = ₹9.20, not ₹8.60).
- `CampaignDetail.jsx`: “₹x.xx / started min” instead of “to connect”.
- Helper copy: setup charged each started minute (0s and 60s = 1; 61s = 2).

### 6. Tests & docs

- `tests/test_billing.py` rewritten for 15s / 59s / 65s / 125s / 90s custom setup / busy / reservation (12 passed).
- `tests/test_cost_guard_budget.py`: `_R` comment and remaining-budget fixture updated for ₹6.20 reservation at ₹2.50/min + ₹0.60.
- `guides/credit.md` intro: “setup fee per started minute” (spec §2–3 already matched).

### Files touched

| Area | Path |
| --- | --- |
| Formula | `billing.py` |
| Settle / list | `db/postgres.py`, `post_call_processor.py` |
| Admin API | `api/routes/internal.py` |
| Admin UI | `AdminOverview.jsx`, `AdminOverview.css`, `AdminCalls.jsx`, `AdminBotConfigs.jsx`, `AdminScriptConfigs.jsx` |
| Client copy | `CampaignDetail.jsx` |
| Tests / docs | `tests/test_billing.py`, `tests/test_cost_guard_budget.py`, `guides/credit.md` |

### Operator note

If `PATCH /internal/bot-configs/...` previously 500’d with `column "fixed_start_credits" does not exist`, run `alembic upgrade head` (migration `011_bot_fixed_start_credits`). That column is required for rates and the new charge path.

---

## Addendum: Unanswered dials are free (2026-08-15)

**Policy change:** Busy / No_Answer / Rejected / Cancel / Failed (never picked up) charge **₹0**. Full claim reservation is refunded. Setup + talk rate apply only after the callee answers (post-call processor).

### Code
- `plivo_hangup.py`: `settle_unanswered_call(..., charge_setup=False)`.
- `db/postgres.py` `settle_unanswered_call`: always writes `credits_charged = 0`, `setup_charge = 0`, `duration_charge = 0`; `charge_setup` ignored.
- `tests/test_settle_unanswered_call.py`: asserts ₹0 + reservation refund to budget_used = 0.
- Spec updates: `guides/credit.md`, `docs/system/09_CALL_LIFECYCLE.md`.




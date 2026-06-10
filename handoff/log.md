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

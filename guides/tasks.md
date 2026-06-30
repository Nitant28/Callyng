# Admin Dashboard — Tasks & Frontend Expectations

> Source of truth for every remaining frontend task. References `db/postgres.py` and `api/routes/internal.py` directly.
> Last updated: 2026-06-10
>
> **Backend status**: All P0+P1 admin endpoints are implemented. See `handoff/log.md` for details.

---

## Part 1: Admin Flow — How the Operator Uses This Panel

### Authentication
1. Operator navigates to `/admin/login`.
2. Types the `ADMIN_SECRET` (env var on the server). The key is stored **only** in React state (`AdminAuthContext`). Never localStorage, never sessionStorage.
3. The frontend calls `GET /internal/health` to validate the key. If 200 → redirect to `/admin`. If 403 → show "Invalid key".
4. On any subsequent 403 or 503 from any `/internal/*` call → clear the key from state, redirect to `/admin/login`.

### The Data Model (How Entities Relate)
```
Client (1) ──→ (N) Bot Configs
Client (1) ──→ (N) Campaigns
Client (1) ──→ (N) Webhook Configs

Bot Config (1) ──→ (N) Campaigns (a campaign uses exactly one bot config)

Campaign (1) ──→ (N) Leads
Campaign (1) ──→ (N) Call Logs

Lead (1) ──→ (N) Call Logs (one lead can be called multiple times)
```

### Typical Operator Workflow
1. **Create a client** → receives a one-time API key → gives it to the customer.
2. **Add credits** to the client's balance.
3. **Create a bot config** for the client → picks a script_id (from available scripts on disk), a route (`sts` or `cascaded`), a telephony number, and a credits_per_minute rate.
4. **Create a campaign** → picks the client, their bot config, sets budget, concurrency limits, and retry settings. Budget is deducted from the client's balance atomically.
5. The customer (via the client API) uploads leads as CSV, then starts the campaign.
6. **The admin monitors**: watches the global calls feed, checks for stuck calls, reviews extraction results, and can force-stop or cancel campaigns.
7. **Configure webhooks** so the customer's n8n/backend receives events like `lead_qualified`, `campaign_completed`.

### Edge Cases the Admin Must Handle
- **Insufficient balance**: Creating a campaign with `budget_credits > 0` fails if `client.balance_credits < budget_credits`. The error message from the backend is: `"Insufficient balance: have X, need Y"`.
- **Duplicate phone in campaign**: Adding a lead with a phone that already exists in the campaign returns nothing (ON CONFLICT DO NOTHING). The frontend should detect this and warn the user.
- **Campaign already terminal**: Attempting to stop/cancel a campaign in `completed` or `cancelled` status returns 409. The UI should disable stop/cancel buttons for terminal campaigns.
- **Bot config client mismatch**: Creating a campaign with a `bot_config_id` that doesn't belong to the selected `client_id` returns 400: `"Invalid bot_config_id for this client"`.
- **Script ID validation**: `script_id` must match `/^[a-z][a-z0-9_]*$/`. Backend returns 422 if invalid.
- **Route must be exactly `sts` or `cascaded`**: Backend returns 422 otherwise. Never `cascade`.
- **Stuck calls**: Calls with `in_progress = true` and `started_at` older than `MAX_CALL_MINUTES + 2` (default 12 minutes) are stale orphans. The operator needs to see these to run `just release-stuck-leads`.
- **Failed extractions**: Calls where `extraction_error IS NOT NULL` or `outcome IS NULL` after call completion indicate the AI extraction pipeline failed. The operator reruns these with `just rerun-extraction`.
- **Budget settlement on cancel**: Cancelling refunds unused budget (`budget_credits - budget_used_credits`) back to the client, but only after all `calling_leads` finish (in-flight calls complete first).

---

## Part 2: Backend Endpoint Map (Complete)

### `/internal/*` routes (X-Admin-Key auth)

| Endpoint | Method | Request Body | Response Shape | Notes |
|----------|--------|-------------|----------------|-------|
| `/internal/health` | GET | — | `{ status, active_calls, pool: { size, idle }, plivo_balance, dialer_tasks }` | `plivo_balance` can be `null` if Plivo fetch fails |
| `/internal/stats` | GET | — | `{ total_calls_today, active_campaigns, total_credits_used_today }` | All integers/floats |
| `/internal/clients` | GET | — | `{ clients: [{ id, name, contact_email, industry, balance_credits, active, created_at, active_campaigns, total_campaigns }] }` | Only active=TRUE clients |
| `/internal/clients` | POST | `{ name, contact_email?, industry? }` | `{ id, name, api_key, message }` | **api_key shown once only** |
| `/internal/clients/:id` | GET | — | `{ client: { ...all fields } }` | Includes inactive clients |
| `/internal/clients/:id/status` | PATCH | `{ active: bool }` | `{ client: { ...updated } }` | Suspend/reactivate |
| `/internal/clients/:id/credits` | PATCH | `{ amount: float, note?: string }` | `{ balance_credits: float }` | Amount can be negative for deductions |
| `/internal/clients/:id/credits` | GET | — | `{ transactions: [{ id, client_id, amount, note, created_at }] }` | Ordered by created_at DESC |
| `/internal/clients/:id/webhooks` | GET | — | `{ webhooks: [{ id, client_id, event, url, secret, active }] }` | Raw DB rows |
| `/internal/bot-configs` | GET | — | `{ bot_configs: [{ id, client_id, name, route, script_id, telephony_number, credits_per_minute, active, created_at }] }` | Only active=TRUE |
| `/internal/bot-configs` | POST | `{ client_id, name, route, script_id, telephony_number, credits_per_minute }` | `{ id }` | Validates script_id and route |
| `/internal/bot-configs/:id` | PATCH | `{ credits_per_minute?, active? }` | `{ bot_config: { ...updated } }` | — |
| `/internal/campaigns` | POST | `{ client_id, bot_config_id, name, budget_credits, max_concurrent_calls?, calls_per_minute?, max_attempts?, retry_delay_minutes?, max_call_minutes? }` | `{ id, campaign: { ...full }, balance_credits }` | `budget_credits >= 0` enforced |
| `/internal/campaigns/:id` | GET | — | `{ campaign: { ...all fields including denorm counters } }` | Admin-level (no client_id needed) |
| `/internal/campaigns/:id` | PATCH | `{ name?, max_concurrent_calls?, calls_per_minute?, max_attempts?, retry_delay_minutes?, max_call_minutes? }` | `{ campaign: { ...updated } }` | — |
| `/internal/campaigns/:id/stop` | PATCH | — | `{ status: "paused", released_calling_leads }` | Stops dialer, releases stuck leads |
| `/internal/campaigns/:id/cancel` | PATCH | — | `{ campaign_id, status, leads_terminalized, credits_returned, calling_leads_remaining, budget_settled }` | Returns unused budget. Fails 409 if already terminal |
| `/internal/webhook-configs` | POST | `{ client_id, event, url, secret }` | `{ id }` | Upserts on (client_id, event) |
| `/internal/calls` | GET | `?limit=50&offset=0` | `{ calls: [...], total_count }` | All call_logs, ordered by created_at DESC |
| `/internal/scripts` | GET | — | `{ scripts: [{ route, script_id }] }` | Scans `sts_scripts/` and `cascade_scripts/` dirs |

### `/api/*` routes (Bearer token auth — client API key)

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/campaigns/:id/leads` | GET/POST/PATCH/DELETE | Requires client Bearer token. Admin doesn't have this. |
| `/api/campaigns/:id/leads/:id/status` | PATCH | Manual status transitions. Requires Bearer. |
| `/api/calls/:session_call_id` | GET | Returns single call log. Requires Bearer. |
| `/api/campaigns/:id/start` | PATCH | Starts dialer. Requires Bearer. |
| `/api/campaigns/:id/stop` | PATCH | Stops dialer. Requires Bearer. |

---

## Part 3: Remaining Tasks

### Task 0: Fix Existing Pages (Remove Mock Data)

#### 0.1 — AdminCalls.jsx: Replace mock fallback with real API
- **Current bug**: Line 16 uses `.catch(() => ({ data: { calls: [...8 hardcoded rows...] } }))`. On any API error, the user sees fake data instead of an error.
- **Fix**: Remove the `.catch()` fallback. Call `GET /internal/calls?limit=50&offset=0` directly. On error, show an inline error banner with a Retry button.
- **Field mapping** from `call_log` DB row to table columns:
  - `session_call_id` → Call ID (first 8 chars, monospace, full UUID on hover)
  - `client_id` → Client (resolve to name from clients lookup map)
  - `campaign_id` → Campaign (resolve to name from campaign lookup)
  - `route` → Route (badge: `sts` = blue, `cascaded` = purple)
  - `in_progress` → Status (`in_progress=true` → pulsing "Live" badge; else show `outcome`)
  - `duration_seconds` → Duration (format as `Xm Ys`)
  - `billed_minutes` → Billed
  - `credits_charged` → Credits (2 decimal places)
  - `started_at` → relative time ("3 hours ago")
- **Add pagination**: `limit` selector (25/50/100), offset-based prev/next buttons.
- **Add call detail panel**: Clicking a row opens a slide-in panel with:
  - All call_log fields rendered
  - Transcript as chat bubbles (assistant left, user right)
  - Usage stats: prompt_tokens, completion_tokens, total_tokens, tts_characters
  - `extraction_json` rendered as key-value pairs (not raw JSON)
  - `extraction_error` shown as red inline error if present
  - Recording URL link if not null, else "No recording (Phase 4)"
  - If `in_progress=true`: pulsing "Live" badge. **Note**: Live polling requires Bearer auth (`GET /api/calls/:session_call_id`), which admin doesn't have. Show a note: "Live transcript polling requires client API key."

#### 0.2 — AdminOverview.jsx: Remove silent mock fallbacks
- **Current bug**: Lines 60-61 have `.catch()` blocks that return fake stats on API failure.
- **Fix**: Remove `.catch()` fallbacks. On error, show "Failed to load stats" error inline. Add a Retry button.
- **Add**: Display `plivo_balance` from `/internal/health` (can be null — show "N/A" if null).
- **Add**: Display `dialer_tasks` count and `pool` stats (size/idle) from health endpoint.

#### 0.3 — AdminClientDetail.jsx: Audit and fix
- Verify it calls `/internal/clients/:id` and `/internal/clients/:id/credits` correctly.
- Verify the "Add Credits" form sends `PATCH /internal/clients/:id/credits` with `{ amount, note }`.
- Ensure no mock data remains. Remove any `.catch(() => mockData)` patterns.
- Add client suspend/reactivate toggle using `PATCH /internal/clients/:id/status` with `{ active: bool }`.

### Task 1: Build Campaigns Page (`/admin/campaigns`)

#### 1.1 — Campaign List (client-scoped)
- **No `GET /internal/campaigns` (all)** endpoint exists. Campaigns must be fetched by selecting a client first.
- **Workaround**: There IS `GET /internal/campaigns/:id` (admin-level, no client_id needed). But we don't have campaign IDs unless we fetch them.
- **Best approach**: Add a `GET /internal/campaigns` endpoint that lists all campaigns across all clients. It doesn't exist yet — **ask the user** if this should be added to the backend.
- **Alternative**: Use the client's `active_campaigns` and `total_campaigns` counts from `/internal/clients`, and when a client is clicked, show their campaigns. But we still need a `list_campaigns` admin endpoint. The DB function `get_campaign_admin` exists but only takes a single `campaign_id`.
- **Recommended backend addition**: Add a `GET /internal/campaigns?client_id=<uuid>` route that calls `list_campaigns(pool, client_id)` — this DB function already exists at line 532 of `postgres.py`.
- **Table columns**: Name, Status (badge: draft=gray, running=green, paused=amber, completed=blue, cancelled=red), Budget allocated, Budget used, Remaining, Lead counters (total/pending/calling/callback/completed/failed), Created at
- **Status values**: Exactly `draft`, `running`, `paused`, `pausing`, `completed`, `cancelled`. The `pausing` status is a transitional state while in-flight calls complete.

#### 1.2 — Campaign Detail (expand on row click)
- Fetch `GET /internal/campaigns/:id` for full detail.
- Show all denormalized counters: `total_leads`, `pending_leads`, `calling_leads`, `callback_leads`, `completed_leads`, `failed_leads`, ``.
- Show budget: `budget_credits` / `budget_used_credits` / remaining (all 2 decimal places).
- Show settings: `max_concurrent_calls`, `calls_per_minute`, `max_attempts`, `retry_delay_minutes`, `max_call_minutes`.
- Resolve `bot_config_id` to bot name from lookup map.
- **Action buttons**:
  - **Stop** → `PATCH /internal/campaigns/:id/stop`. Confirm dialog: "This will pause the campaign and release stuck leads."
  - **Cancel** → `PATCH /internal/campaigns/:id/cancel`. Confirm dialog: "This will cancel the campaign, fail all pending leads, and refund unused budget. In-flight calls will complete." Show returned credits in success toast.
  - Disable Stop if status is not `running`/`pausing`.
  - Disable Cancel if status is `completed` or `cancelled`.
  - **Note**: Campaign `start` requires client Bearer token (`PATCH /api/campaigns/:id/start`). Show disabled button with tooltip: "Start requires client API key."

#### 1.3 — Create Campaign
- Form fields: client (select), bot config (select, **filtered to selected client**), name, budget_credits (≥ 0), max_concurrent_calls (default 5), calls_per_minute (default 10), max_attempts (default 3), retry_delay_minutes (default 120), max_call_minutes (optional).
- Bot config dropdown must update when client changes. Fetch `GET /internal/bot-configs` and filter by `client_id`.
- On success, display returned campaign and updated `balance_credits`.

#### 1.4 — Edit Campaign
- Inline form in expanded detail.
- Editable fields: `name`, `max_concurrent_calls`, `calls_per_minute`, `max_attempts`, `retry_delay_minutes`, `max_call_minutes`.
- `PATCH /internal/campaigns/:id` with only changed fields.

### Task 2: Build Diagnostics Page (`/admin/diagnostics`)

Three stacked panels:

#### 2.1 — Plivo Balance
- Display `plivo_balance` from `GET /internal/health`.
- If null, show: "Plivo balance unavailable. Check via `just plivo-balance` in the terminal."

#### 2.2 — Stuck Calls
- Fetch `GET /internal/calls?limit=100` and filter client-side for rows where:
  - `in_progress = true`
  - `started_at` is older than 12 minutes (default `MAX_CALL_MINUTES=10` + 2 grace)
- Display table: session_call_id, campaign_id, lead_id, started_at, time stuck (relative).
- Show note: "Use `just release-stuck-leads <campaign_id>` to release these."

#### 2.3 — Failed Extractions
- Fetch `GET /internal/calls?limit=100` and filter for rows where:
  - `outcome` is null AND `in_progress = false` (call ended but no outcome)
  - OR `extraction_error IS NOT NULL`
- Display: session_call_id, route, started_at, extraction_error.
- Show note: "Use `just rerun-extraction <session_id>` to retry."

#### 2.4 — Campaign Counter Reconcile
- Text input for campaign UUID.
- Show the SQL query the operator should run: `SELECT status, COUNT(*) FROM leads WHERE campaign_id = '<id>' GROUP BY status;`
- No API call. This is a manual diagnostic.

### Task 3: Add Missing Nav Links to AdminLayout

Add these to the sidebar navigation in `AdminLayout.jsx`:
- **Campaigns** → `/admin/campaigns` (icon: `campaign`)
- **Diagnostics** → `/admin/diagnostics` (icon: `monitor_heart`)

### Task 4: Add Routes to App.jsx

Add these routes:
- `/admin/campaigns` → `<AdminCampaigns />` wrapped in AdminLayout + AdminGuard
- `/admin/diagnostics` → `<AdminDiagnostics />` wrapped in AdminLayout + AdminGuard

### Task 5: Wire Admin Calls Properly

The current `AdminCalls.jsx` hits `/admin/calls` which the interceptor maps to `/internal/calls`. This is correct, but the response mapping is wrong.

**The `GET /internal/calls` response shape** (from `list_call_logs` at line 2046):
```json
{
  "calls": [
    {
      "id": "uuid",
      "session_call_id": "string",
      "client_id": "uuid",
      "campaign_id": "uuid (nullable)",
      "lead_id": "uuid (nullable)",
      "bot_config_id": "uuid (nullable)",
      "route": "sts|cascaded",
      "call_sid": "string (Plivo UUID, nullable)",
      "started_at": "iso datetime",
      "ended_at": "iso datetime (nullable)",
      "duration_seconds": "int (nullable)",
      "billed_minutes": "int (nullable)",
      "credits_charged": "float (nullable)",
      "in_progress": "bool",
      "outcome": "string (nullable)",
      "qualified": "bool (nullable)",
      "transcript": "[{role, content, ts}]",
      "extraction_json": "{}",
      "extraction_model": "string (nullable)",
      "extraction_error": "string (nullable)",
      "usage_prompt_tokens": "int",
      "usage_completion_tokens": "int",
      "usage_total_tokens": "int",
      "usage_tts_characters": "int",
      "created_at": "iso datetime"
    }
  ],
  "total_count": 42
}
```

### Task 6: Data Resolution Maps

Load on app mount (after login):
- **Clients map**: `{ [client_id]: { name, industry } }` from `GET /internal/clients`
- **Bot configs map**: `{ [bot_config_id]: { name, client_id, route, script_id } }` from `GET /internal/bot-configs`

Use these maps everywhere UUIDs appear. Refresh after any create/edit mutation.

Store in a shared context or pass down from a top-level admin data provider.

### Task 7: Backend Changes Needed (Ask User First)

| Change | Why |
|--------|-----|
| Add `GET /internal/campaigns?client_id=<uuid>` | No way to list campaigns for a client from admin panel. DB function `list_campaigns` already exists. |
| Optionally: Add `GET /internal/campaigns` (all campaigns) | Useful for a global campaigns view without pre-selecting a client. |

---

## Part 4: Formatting & Display Conventions

| Data Type | Format |
|-----------|--------|
| UUID | First 8 chars displayed, full UUID in title attribute. One-click copy button. |
| Timestamps | Relative time ("3 hours ago") with ISO string in title attribute. |
| Credits/Money | Always `toFixed(2)`, never raw floats. |
| Duration | `Math.floor(s/60)m Math.floor(s%60)s` |
| JSON fields | Render as `<dl>` key-value pairs. Nested objects collapsible. Never raw `<pre>`. |
| Transcript | Chat bubbles. Assistant = left, muted bg. User = right, primary bg. Timestamp below each. |
| Status badges | Pill-shaped, semantic colors from design system. |
| Empty states | Meaningful message + action hint. Never blank. |
| Loading states | Skeleton or spinner. Never blank. |
| Error states | Inline banner with HTTP status, detail message, and Retry button. |

## Part 5: Lead Status State Machine (for reference)

```
                ┌─────────────┐
     Upload ──→ │   pending   │ ──→ calling ──→ completed
                └─────────────┘         │
                      ↑                 ├──→ failed
                      │                 ├──→ 
                      │                 └──→ callback_scheduled ──→ calling (retry)
                      │                           │
                      └───────────────────────────┘ (manual: back to pending)
```

Manual transitions allowed (from `_MANUAL_TRANSITIONS` in `leads.py`):
- `pending` → `failed`, ``, `callback_scheduled`
- `callback_scheduled` → `pending`, `failed`, ``
- `failed` → `pending`
- `` → `pending`
- `completed` → `pending`

## Part 6: Campaign Status State Machine

```
  draft ──→ running ──→ pausing ──→ paused
                │                      │
                ├──→ completed         │
                │                      ├──→ running (restart)
                └──→ cancelled ←───────┘
```

- `draft`: Created but not started. Leads can be uploaded.
- `running`: Dialer is actively making calls.
- `pausing`: Stop requested; waiting for in-flight calls to finish.
- `paused`: All in-flight calls done. Can be restarted.
- `completed`: All leads processed. Budget settled.
- `cancelled`: Operator cancelled. Unused budget refunded.

# 06 — Frontend Integration Guide (MOST IMPORTANT)

This document is written for a frontend engineer building a **new** client (and
optionally admin) UI against the existing FastAPI backend. Every claim is tied to
verified source. API shapes are in `05_API_REFERENCE.md`; statistics rules in
`11_STATISTICS_ENGINE.md`.

---

## Global integration facts

| Topic | Verified behavior |
|-------|-------------------|
| Base URL | `VITE_API_BASE_URL` (empty in dev → Vite proxy to `:7860`) |
| Client auth | `Authorization: Bearer <key>` from `localStorage['client_api_key']` |
| Admin auth | `X-Admin-Key` from `localStorage['aakashvani_admin_key']` |
| Error shape | `{ detail: string \| object }` — read `error.response.data.detail` |
| 401/403 client | clear key → redirect `/login` (`api/client.js`) |
| 403/503 admin | logout callback → redirect `/admin/login` (`api/admin.js`) |
| CORS origins | localhost:3000/5173/5174 + production admin/app domains (`server.py`) |
| Rate limit | 100 req/min/IP → 429 |

**No WebSocket/SSE for dashboard updates today.** All realtime is **polling**.

---

## Client pages

### `/login` — `Login.jsx`

| | |
|---|---|
| **Purpose** | Validate client API key and persist it |
| **APIs** | `GET /api/credits` with explicit `Authorization: Bearer ${key}` (bypasses interceptor for validation) |
| **State** | `apiKey`, `loading`, `isSuccess`, `isError`, `isShaking`, `isRedirecting` |
| **Components** | `CanvasBackground`, `ThemeToggle`, `Button` |
| **Success response** | HTTP 200 on `/api/credits` → store `localStorage.client_api_key` → navigate `/app` |
| **Loading** | Button shows "Validating..."; input disabled |
| **Error** | 401/403 → shake animation + "Invalid Client Key" (no server message surfaced) |
| **Empty** | n/a |
| **Refresh** | none |
| **Polling** | none |
| **Must NOT compute** | n/a |
| **Must come from backend** | Key validity only (via credits endpoint) |

---

### `/app` — `Dashboard.jsx`

| | |
|---|---|
| **Purpose** | Credit balance + campaign grid; start/stop campaigns |
| **APIs** | `GET /api/credits`, `GET /api/campaigns`, `PATCH /api/campaigns/{id}/start`, `PATCH /api/campaigns/{id}/stop` |
| **State** | `balance`, `displayBalance` (animation), `campaigns[]`, `loading`, `confirmStartCampaign`, `istStatus` (client-computed TRAI window display) |
| **Components** | `LoaderOverlay`, `Badge`, campaign cards |
| **Expected campaign fields** | Full `campaigns` row: `id`, `name`, `status`, `budget_credits`, `budget_used_credits`, all `*_leads` counters, `calling_leads`, `max_concurrent_calls`, etc. |
| **Loading** | `LoaderOverlay` on initial load |
| **Error** | `console.warn` only — **no user-visible error state** for failed fetches |
| **Empty** | Empty campaign grid when `campaigns.length===0` |
| **Refresh** | Initial `loadDashboardData()` on mount |
| **Polling** | **5s** when any campaign is `running`, `pausing`, or `paused` with `calling_leads>0`. Silent refresh (`showSpinner=false`) |
| **Realtime** | Counter changes on campaign cards via poll |
| **Must NOT compute** | Lead counts, progress % from lead list |
| **Must come from backend** | `balance_credits`, all campaign counters, `status`, budget fields |
| **Safe to derive** | `remaining = budget_credits - budget_used_credits`; IST compliance badge (display-only, mirrors `compliance.py` 9–21 IST) |

**Start flow:** opens confirm modal → `PATCH .../start` → toast on success → reload.

---

### `/app/campaigns/:id` — `CampaignDetail.jsx`

| | |
|---|---|
| **Purpose** | Single-campaign command center: stats, leads CRUD, CSV upload, start/stop/cancel, release-stuck |
| **APIs** | `GET /api/campaigns/{id}/stats`, `GET /api/campaigns/{id}/leads`, `POST .../leads/upload`, `GET .../leads/template`, `POST/PATCH/DELETE .../leads`, `PATCH .../leads/{id}/status`, `PATCH .../start\|stop\|cancel`, `POST .../release-stuck-calling` |
| **State** | `campaign` (stats object), `leads[]`, `totalLeadsCount`, pagination (`leadsLimit=10`, `leadsOffset`, `leadsSearch`, `leadsStatusFilter`), modals (add/edit/start/release), `liveCallingCount` (animated from `calling_leads`), `istStatus`, transcript drawer state |
| **Components** | `LoaderOverlay`, `CallTranscriptDrawer`, tabs (overview/leads/settings) |
| **Stats response** | `{ stats: { ...campaignRow, bot_config: { ..., lead_schema } } }` |
| **Leads response** | `{ leads, total_count, limit, offset, status, search }` — each lead may include `last_call_duration_seconds`, `last_call_outcome`, `last_call_ended_at`, `last_hangup_source` |
| **Loading** | Full-page `LoaderOverlay` until first stats load; separate `leadsLoading` for table |
| **Error** | Toasts via `showToast` on mutations; fetch failures mostly `console.warn` |
| **Empty** | Empty leads table; upload result panel |
| **Refresh** | Reload stats + leads on mount and after mutations |
| **Polling** | Stats: **2s** while `status==='pausing'`, else **5s** when `running`/`pausing`/`paused&&calling_leads>0`. Leads: **5s** under same conditions |
| **Realtime** | Metric cards, `liveCallingCount`, lead statuses |
| **Must NOT compute** | `pending_leads`, `calling_leads`, etc. from `leads.length`; total leads from page size |
| **Must come from backend** | All campaign counters; `total_count` for pagination; `total_leads`; budget; `lead_schema` for dynamic form fields |
| **Safe to derive** | `OUTCOME_LABELS` mapping (display); `formatCallbackTiming` from `next_attempt_at`; `buildCallbackBadgeLabel`; progress bar from counters |

**Upload:** `multipart/form-data` field `file`. On 400 with `detail.errors`, show validation errors.

**Transcript:** opens `CallTranscriptDrawer` with lead's latest call — drawer fetches by `session_call_id` (Not verified: exact resolution path from lead row in CampaignDetail — inspect component for `session_call_id` source).

---

### `/app/calls` — `CallLogs.jsx`

| | |
|---|---|
| **Purpose** | Paginated call history + transcript drawer |
| **APIs** | `GET /api/calls?limit&offset`, `GET /api/calls/{session_call_id}`, `GET /api/calls/{id}/recording/play` (blob) |
| **State** | `calls[]`, `totalCount`, `limit=10`, `offset`, `loading`, drawer state, `callData`, `recordingUrl`, recording loading/error |
| **Components** | `CallTranscriptDrawer` |
| **List response** | `{ calls: CallLog[], total_count }` — rows include joined `name`, `phone` |
| **Detail response** | Full call_log dict; `in_progress: bool` drives polling |
| **Loading** | List spinner; drawer `callLoading`; recording `recordingLoading` |
| **Error** | `console.warn` on list; recording shows `recordingError` |
| **Empty** | Empty table state |
| **Polling** | Drawer polls detail **2s** while `in_progress===true` (`CallTranscriptDrawer`) |
| **Must come from backend** | `total_count`, `duration_seconds`, `outcome`, `credits_charged`, `transcript`, `extraction_json`, `in_progress` |

---

### `/app/settings` — `Settings.jsx`

| | |
|---|---|
| **Purpose** | Theme toggle only |
| **APIs** | **none** |
| **State** | none (uses `useTheme` hook / localStorage) |

---

## Shared components

### `CallTranscriptDrawer.jsx`
- Fetches `GET /api/calls/{sessionCallId}` on open.
- Parses `transcript` / `extraction_json` if returned as strings (defensive).
- Polls **2s** while `call.in_progress`.
- Recording: `GET .../recording/play` as blob → object URL.
- **Must display** backend `outcome`, `duration_seconds`, `extraction_json` verbatim.

### `Guards.jsx`
- `ClientGuard`: `localStorage.client_api_key` present → else `/login`.
- `AdminGuard`: `useAdminAuth().adminKey` → else `/admin/login`.
- No server round-trip on navigation.

---

## Admin pages (summary — see `13_ADMIN_GUIDE.md`)

All use `adminApi` with `/internal/*` paths. `AdminDataContext` preloads
`clients` + `bot_configs` on auth.

| Route | Primary APIs |
|-------|-------------|
| `/admin/login` | `GET /internal/health` (key validation) |
| `/admin` | `GET /internal/stats`, `GET /internal/health` |
| `/admin/clients` | `GET/POST /internal/clients`, regenerate-key |
| `/admin/clients/:id` | client, credits ledger, webhooks, campaigns, start/stop |
| `/admin/bot-configs` | `GET/POST/PATCH /internal/bot-configs` |
| `/admin/script-configs` | full script-config CMS |
| `/admin/campaigns` | `GET/POST /internal/campaigns`, start/stop |
| `/admin/calls` | `GET /internal/calls`, detail, recording |
| `/admin/diagnostics` | health, calls, reconcile, release-stuck |
| `/admin/webhooks` | clients list, upsert webhook-configs |

---

## Caching strategy (current vs recommended)

**Current:** no cache library. Polling refetches full resources. Admin clients/bots
cached in `AdminDataContext` until logout.

**Recommended for rebuild:** React Query / TanStack Query with:
- `staleTime: 0` for polled resources (campaign stats while running).
- `refetchInterval` tied to campaign status (5s/2s as above).
- No client-side aggregation of stats.

---

## Authentication flow (rebuild)

```
Client: paste key → GET /api/credits → store localStorage → ClientGuard on /app/*
Admin:  paste key → GET /internal/health → store localStorage → setGlobalAdminKey → AdminGuard
```

No refresh tokens. Key rotation = admin regenerates → client must re-login.

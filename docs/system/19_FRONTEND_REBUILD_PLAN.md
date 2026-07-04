# 19 — Frontend Rebuild Plan

Actionable plan for building a **new** frontend against the existing backend.
All API existence claims verified from `api/routes/*` and `server.py`.

---

## APIs that already exist (use these)

### Client (build the new UI on these)
| Capability | Endpoint |
|------------|----------|
| Auth validate | `GET /api/credits` |
| Credit balance | `GET /api/credits` |
| List campaigns | `GET /api/campaigns` |
| Campaign stats + bot schema | `GET /api/campaigns/{id}/stats` |
| Create campaign | `POST /api/campaigns` |
| Patch campaign settings | `PATCH /api/campaigns/{id}` |
| Start/stop/cancel | `PATCH .../start\|stop\|cancel` |
| Release stuck | `POST .../release-stuck-calling` |
| List/upload/template leads | `GET/POST .../leads`, upload, template |
| Lead CRUD + status | leads routes |
| Call logs + detail + recording | `/api/calls*` |

### Admin (if rebuilding admin too)
Full `/internal/*` surface documented in `05_API_REFERENCE.md`.

### Do NOT use from frontend
| Endpoint | Why |
|----------|-----|
| `POST /start` | Manual/test dial only; no client auth |
| `/answer`, `/ws`, `/plivo-*` | Plivo integration |
| `GET /health` (unauthenticated) | Use `/internal/health` for admin only |

---

## APIs that are missing (gaps for a polished frontend)

| Gap | Impact | Workaround today |
|-----|--------|------------------|
| No `GET /api/me` or profile endpoint | Can't show client email/industry | Only `client_name` from `/api/credits` |
| No client campaign create in old UI? | API exists (`POST /api/campaigns`) but **not verified in current client pages** | Wire create-campaign flow |
| No `GET /api/bot-configs` for client | Client can't pick bot when creating campaign | Admin creates campaigns OR add backend route |
| No WebSocket push for stats/calls | Must poll | Poll as documented |
| No bulk export (leads/calls CSV) | — | Add backend route or client-side page iteration (expensive) |
| No client webhook visibility | — | Admin only |
| Upload errors return `detail.errors` array | Need structured parser | Handle object detail |
| No OpenAPI-generated client SDK | Manual typing | Generate from `/docs` or maintain types in `07` |

---

## APIs that should be improved

1. **`GET /api/campaigns/{id}/stats`** — rename or alias to `GET /api/campaigns/{id}`
   (stats is the full campaign; confusing name).
2. **Normalize error responses** — always `{ code, message, details? }` instead of
   mixed string/object `detail`.
3. **`GET /api/calls`** — include `lead_name/phone` consistently (already joined);
   add `campaign_name` for list context.
4. **Admin `GET /internal/campaigns`** — hard LIMIT 200; needs cursor pagination.
5. **`GET /internal/stats`** — accept `?timezone=Asia/Kolkata` or compute in IST explicitly.
6. **Client bot-config list** — `GET /api/bot-configs` (read-only, client's bots only)
   for self-serve campaign creation.

---

## Endpoints that need pagination (already paginated vs not)

| Endpoint | Paginated? | Default limit |
|----------|------------|---------------|
| `GET /api/calls` | yes | 50 |
| `GET /api/campaigns/{id}/leads` | yes | 50 |
| `GET /api/campaigns` | **no** (full list) | — |
| `GET /internal/calls` | yes | 50 |
| `GET /internal/campaigns` | **no** (LIMIT 200) | 200 |
| `GET /internal/clients` | **no** | all |

Rebuild: paginate campaign list client-side only if tenant has few campaigns;
add virtual scroll if list grows.

---

## Expensive endpoints

| Endpoint | Cost | Mitigation |
|----------|------|------------|
| `GET /api/campaigns/{id}/stats` + leads poll | moderate (2 queries / 5s) | React Query `refetchInterval`; stop when inactive |
| `GET /api/calls/{id}` poll 2s | moderate for long calls | stop when `!in_progress` |
| `POST .../leads/upload` large CSV | heavy (pandas + bulk insert) | progress UI; async job **not implemented** |
| `GET /internal/calls?limit=200` | heavy | keep admin pagination low |
| `reconcile_campaign_counters` | COUNT(*) on all leads | admin-only; never call from client |

---

## Optimistic updates (recommended)

| Action | Optimistic? | Reason |
|--------|-------------|--------|
| Start/stop campaign | **No** — wait for server | status + counters must be authoritative |
| Upload leads | **No** | server returns inserted count |
| Edit lead fields | **Yes** possible | revert on 409 |
| Manual status change | **No** | server returns updated counters |
| Delete lead | **Yes** with rollback | then reconcile counters from response |

---

## Polling strategy (preserve verified intervals)

| Page | Interval | Condition |
|------|----------|-----------|
| Dashboard | 5s | any campaign running/pausing/paused+calling |
| CampaignDetail stats | 2s | status===pausing |
| CampaignDetail stats | 5s | running/pausing/paused+calling |
| CampaignDetail leads | 5s | same |
| CallTranscriptDrawer | 2s | `in_progress===true` |

---

## WebSocket later (not in backend today)

Candidates for future **server-push** (would need new backend work):
- Live `calling_leads` / campaign counters
- In-call transcript stream (today: poll `GET /api/calls/{id}`)
- Dialer progress events

Do not implement WS client until backend exposes a documented protocol.

---

## Recommended React architecture

```
src/
  app/           # routes, providers
  api/           # typed clients (client.ts, admin.ts)
  hooks/         # useCampaignStats(id), useLeadsQuery(...), useAuth
  features/
    campaigns/
    leads/
    calls/
    auth/
  components/ui/ # design system
  lib/           # formatters (duration, outcome labels), istCompliance
  types/         # Campaign, Lead, CallLog from 07
```

- **React 18 + TypeScript + Vite**
- **TanStack Query** for server state, polling, cache invalidation
- **React Router v6**
- No Redux — server state in Query; UI state local

---

## Recommended Context architecture

| Context | Scope |
|---------|-------|
| `AuthContext` | client key + login/logout (unify client; keep admin separate or split) |
| `ToastContext` | global notifications |
| Optional `ThemeContext` | dark/light |

Avoid caching campaigns globally — use Query per route.

---

## Recommended API layer

```typescript
// api/client.ts
const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL });
// interceptors: Bearer, 401 redirect, detail extraction

export const campaignsApi = {
  list: () => client.get<{ campaigns: Campaign[] }>('/api/campaigns'),
  stats: (id: string) => client.get<{ stats: Campaign & { bot_config } }>(`/api/campaigns/${id}/stats`),
  // ...
};
```

Generate types from OpenAPI (`/openapi.json`) if maintained — **verify FastAPI
exposes it at `/openapi.json`**.

---

## Recommended hooks

| Hook | Responsibility |
|------|----------------|
| `useClientAuth()` | key in localStorage, validate, logout |
| `useCampaign(id)` | stats query + poll policy from status |
| `useCampaignLeads(id, query)` | paginated leads + poll |
| `useCalls(query)` | paginated call list |
| `useCallDetail(sessionCallId)` | detail + poll if in_progress |
| `useIstCompliance()` | display-only TRAI window (mirror `compliance.py`) |

---

## Caching strategy

- `staleTime: 30_000` for static-ish data (credits) when not polling.
- `refetchInterval` dynamic based on `campaign.status` and `calling_leads`.
- Invalidate `['campaign', id]` and `['campaigns']` after start/stop/upload.
- Never cache mutated counters without refetch — trust POST/PATCH response
  `counters` field when present (start, release-stuck, status change).

---

## Error handling

- Map `error.response.data.detail` (string or `{errors:[]}` for upload).
- Show **visible** fetch errors (current UI often only `console.warn`).
- 409 → explain campaign/lead state (backend message is descriptive).
- 503 → "Service unavailable — database connection" (Postgres down).
- 429 → backoff + user message.

---

## Loading strategy

- Route-level skeleton for Dashboard/CampaignDetail/CallLogs.
- Table row skeleton for leads/calls pagination.
- Disable action buttons while mutation pending (`isPending` from Query).
- Separate `isRefreshing` from `isLoading` for poll (no full-page flash).

---

## Authentication flow

```
Client:
  Login → GET /api/credits → setItem('client_api_key') → /app
  Route guard: key present (optional: re-validate credits on app boot)
  401 anywhere → clear key → /login

Admin (if built):
  Login → GET /internal/health + X-Admin-Key → setItem → /admin
  403/503 → clear → /admin/login
```

---

## Reusable components to build

| Component | Data source |
|-----------|-------------|
| `CampaignStatusBadge` | `campaign.status` |
| `CampaignMetricsGrid` | backend counters only |
| `BudgetBar` | `budget_used_credits / budget_credits` |
| `LeadsTable` | paginated leads API |
| `CallTranscriptPanel` | call detail + poll |
| `AudioPlayer` | recording/play blob |
| `CsvUploadDropzone` | multipart upload |
| `LeadForm` | dynamic fields from `lead_schema` |
| `ConfirmDialog` | start/cancel/release-stuck |
| `IstComplianceBanner` | client-derived IST clock |
| `OutcomeBadge` | maps `outcome` → label (display only) |
| `Pagination` | uses `total_count` from API |

---

## Migration checklist

1. Stand up types + API client against running backend (`15_ENVIRONMENT_SETUP.md`).
2. Implement auth + route guards.
3. Dashboard + campaign list (counters from API only — read `11_STATISTICS_ENGINE.md`).
4. Campaign detail (stats poll + leads CRUD + upload).
5. Call logs + transcript drawer + recording.
6. Settings (theme).
7. (Optional) Admin console or defer to existing SPA.
8. E2E tests against seed tenant (`RUN_LOCAL.md` credentials).

---

## Success criteria

- Zero client-side recomputation of `*_leads` counters or `total_count`.
- Polling stops when campaigns inactive (save API load).
- All 409/400 paths show backend `detail` message.
- New engineer can implement UI without reading `db/postgres.py` — only this
  `/docs/system` folder + OpenAPI.

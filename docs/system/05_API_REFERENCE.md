# 05 — API Reference

Base URL: `VITE_API_BASE_URL` (frontend) → FastAPI host (dev `:7860`).
Global rate limit: **100 req/min per IP** (429 on exceed). CORS allow-list in
`server.py` (see `03_BACKEND_ARCHITECTURE.md`).

Auth schemes:
- **Client:** `Authorization: Bearer <client_api_key>` → resolves to a client row.
  Errors: **401** invalid key, **503** Postgres unavailable.
- **Admin:** `X-Admin-Key: <ADMIN_API_KEY>`. Error: **403**.
- **Telephony:** none.

> The admin frontend (`api/admin.js`) calls paths under `/admin/*` and **rewrites
> them to `/internal/*`** before sending. The real server paths are `/internal/*`.
> This doc uses the real server paths.

Conventions:
- All bodies are JSON unless noted. Lead upload is `multipart/form-data`.
- UUIDs in paths are validated by FastAPI (422 on malformed).
- Many mutating endpoints validate campaign state and return **409** when the
  action isn't allowed in the current state.

---

# CLIENT API (`/api/*`)

## `GET /api/credits`
- **Auth:** client. **Used by:** Login (validation), Dashboard.
- **Response:** `{ balance_credits: float, max_concurrent_calls: int, client_name: str }`
- **Internal:** reads the `client` dict from `get_client_from_token` (no extra query).
- **Tables:** `clients` (read, via auth).
- **Example response:** `{"balance_credits": 1450.0, "max_concurrent_calls": 5, "client_name": "Pyramid"}`

## `GET /api/campaigns`
- **Auth:** client. **Query:** `search?` (client-side name filter applied in route).
- **Response:** `{ campaigns: Campaign[] }` — full campaign rows incl. all counters
  + budget. Ordered `created_at DESC`.
- **Internal:** `pg_db.list_campaigns(pool, client_id)`. **Tables:** `campaigns`.
- **Frontend:** Dashboard (cards). Polled every 5s while any campaign active.

## `POST /api/campaigns`
- **Auth:** client. **Body:** `ClientCreateCampaignBody`
  `{ name, bot_config_id (UUID), budget_credits (≥0), max_concurrent_calls=5,
  calls_per_minute=10, max_attempts=3, retry_delay_minutes=120, max_call_minutes? }`
- **Behavior:** creates `draft` campaign; if `budget_credits>0`, **immediately
  deducts** from `clients.balance_credits` (`allocate_campaign_budget`, FOR UPDATE).
- **Response:** `{ id: str }`. **Errors:** 400 (invalid bot_config / insufficient
  balance).
- **Tables:** `campaigns` (insert), `clients` (balance −).

## `GET /api/campaigns/{campaign_id}/stats`
- **Auth:** client. **Response:** `{ stats: Campaign & { bot_config: BotConfig & { lead_schema } } }`.
  The campaign row (all counters) plus its bot config and resolved lead schema.
- **Internal:** `get_campaign` + `get_bot_config` + `_get_lead_schema`.
- **Errors:** 404. **Frontend:** CampaignDetail metric cards. Polled 2–5s while active.

## `PATCH /api/campaigns/{campaign_id}`
- **Auth:** client. **Body:** `ClientPatchCampaignBody` (any of name/throttle/retry/max_call_minutes).
- **Guard:** `require_campaign_modifiable(allow_paused=True)` → **409** unless
  draft/paused. **Response:** `{ success: true }`.

## `POST /api/campaigns/{campaign_id}/leads/upload`
- **Auth:** client. **Body:** `multipart/form-data` with `file` (CSV/XLSX).
- **Guard:** campaign must be draft/paused (409 otherwise).
- **Behavior:** parse (`parse_upload`) → validate against lead schema
  (`validate_dataframe`; **400 `{errors:[...]}` on schema errors**) → normalize
  phones → build metadata from schema fields → `bulk_insert_leads`
  (`ON CONFLICT (campaign_id, phone) DO NOTHING`). If outside TRAI window, fresh
  leads get `next_attempt_at = next_compliant_time()`.
- **Response:** `{ leads_uploaded: int, invalid_phones: int, duplicates_skipped: int }`.
- **Tables:** `leads` (insert), `campaigns` (counters via insert path).

## `GET /api/campaigns/{campaign_id}/leads/template`
- **Auth:** client. **Response:** `text/csv` attachment with header row
  (`phone`, `name`, + schema csv columns). **Frontend:** CampaignDetail "download template".

## `PATCH /api/campaigns/{campaign_id}/start`
- **Auth:** client. **Behavior:** allowed from draft/paused/pausing (else 409);
  requires remaining budget `≥ 2` (else 400). Releases stuck `calling` leads,
  bumps due retries, reconciles counters, sets status `running`, **starts dialer**.
- **Response:** `{ status:"running", campaign_id, released_calling_leads, bumped_pending_retry, counters }`.

## `PATCH /api/campaigns/{campaign_id}/stop`
- **Auth:** client. **Behavior:** stops dialer, releases stuck calling leads,
  sets status `pausing` if `calling_leads>0` else `paused`.
- **Response:** `{ status, campaign_id, released_calling_leads }`.

## `PATCH /api/campaigns/{campaign_id}/cancel`
- **Auth:** client. **Behavior:** stops dialer; `cancel_campaign` terminalizes
  non-terminal leads → `failed`, returns unused budget (idempotent), sets
  `cancelled` (deferred while in-flight calls remain). **409** if already
  completed/cancelled.
- **Response:** `{ campaign_id, ...settlement result }`.

## `POST /api/campaigns/{campaign_id}/release-stuck-calling`
- **Auth:** client. **Behavior:** force-release stuck `calling` leads
  (`ignore_wrap_grace=True`) + reconcile counters. **409** unless running/pausing/paused.
- **Response:** `{ campaign_id, released, counters }`.

### Leads CRUD (`/api/campaigns/{campaign_id}/leads`)

## `GET /api/campaigns/{campaign_id}/leads`
- **Auth:** client. **Query:** `limit=50, offset=0, status?, search?`.
- **Response:** `{ leads: Lead[], limit, offset, status, search, total_count }`.
  Each lead includes LATERAL-joined `last_call_duration_seconds`,
  `last_call_outcome`, `last_call_ended_at`, `last_hangup_source`.
- **Frontend:** CampaignDetail lead table. Polled 5s while active.

## `GET /api/campaigns/{campaign_id}/leads/{lead_id}`
- **Auth:** client. **Response:** `{ lead: Lead }`. 404 if not found / wrong campaign.

## `POST /api/campaigns/{campaign_id}/leads`
- **Auth:** client. **Body:** `AddLeadBody { phone, name?, lead_type='cold', metadata? }`.
- **Guard:** campaign draft/paused. Validates phone (422), lead_type (422),
  duplicate → **409**. **Response:** `{ lead }`.

## `PATCH /api/campaigns/{campaign_id}/leads/{lead_id}`
- **Auth:** client. **Body:** `EditLeadBody { name?, lead_type?, metadata? }`.
- **Guard:** campaign modifiable + lead not `calling` (409). 400 if no fields.
  **Response:** `{ lead }`.

## `PATCH /api/campaigns/{campaign_id}/leads/{lead_id}/status`
- **Auth:** client. **Body:** `ChangeStatusBody { status, scheduled_at? }`.
- **Behavior:** enforces `_MANUAL_TRANSITIONS`; never allows → `calling` (409);
  blocks `callback_scheduled` if attempts exhausted (409); reconciles counters.
- **Response:** `{ lead, transition: "x → y", counters }`.

## `DELETE /api/campaigns/{campaign_id}/leads/{lead_id}`
- **Auth:** client. **Guard:** campaign draft/paused + lead not calling.
  **Behavior:** hard-delete lead (call_logs preserved) + reconcile counters.
- **Response:** `{ deleted: true, lead_id, counters }`.

### Calls (`/api/calls`)

## `GET /api/calls`
- **Auth:** client. **Query:** `limit=50 (1–200), offset=0, search?`.
- **Response:** `{ calls: CallLog[], total_count }`. Each row is `call_logs.*`
  joined with `leads.name, leads.phone`. Excludes test calls. Ordered `created_at DESC`.
- **Frontend:** CallLogs list (pagination).

## `GET /api/calls/{session_call_id}`
- **Auth:** client. **Behavior:** look up by `session_call_id`; if not found and
  the id parses as UUID, fall back to latest call_log for that **lead_id**.
- **Response:** the call_log dict (incl. `transcript`, `extraction_json`,
  `in_progress`, `plivo_hangup_json`, timing, billing). 404 if none.
- **Frontend:** CallTranscriptDrawer. Polled 2s while `in_progress`.

## `GET /api/calls/{session_call_id}/recording`
- **Auth:** client. **Response:** `local:` → `audio/mpeg` file; else
  `{ url, expires_in: 3600 }` (resolved Plivo/R2 URL). 404 if no recording.

## `GET /api/calls/{session_call_id}/recording/play`
- **Auth:** client. **Response:** streams audio (`audio/mpeg`). For `plivo:` keys
  it **proxies** the Plivo recording with Plivo BasicAuth (server-side); `local:`
  returns the file; R2 keys redirect to a signed URL. **Frontend:** drawer audio
  player (consumed as blob).

---

# ADMIN API (`/internal/*`) — requires `X-Admin-Key`

### Clients
| Method | Path | Body / Query | Response | Notes |
|--------|------|--------------|----------|-------|
| POST | `/internal/clients` | `{name, contact_email?, industry?}` | `{id, name, api_key, message}` | api_key shown **once** |
| GET | `/internal/clients` | `search?` | `{clients:[...]}` | |
| GET | `/internal/clients/{id}` | | `{client}` | 404 |
| POST | `/internal/clients/{id}/regenerate-key` | | `{api_key, message}` | invalidates old key |
| PATCH | `/internal/clients/{id}` | `{name?, contact_email?, industry?}` | `{client}` | raw SQL update |
| PATCH | `/internal/clients/{id}/status` | `{active: bool}` | `{client}` | |
| PATCH | `/internal/clients/{id}/credits` | `{amount, note?}` | `{balance_credits}` | writes `credit_transactions`; 404 if client missing |
| GET | `/internal/clients/{id}/credits` | | `{transactions:[...]}` | ledger |
| GET | `/internal/clients/{id}/webhooks` | | `{webhooks:[...]}` | |

### Bot configs
| Method | Path | Body / Query | Response |
|--------|------|--------------|----------|
| POST | `/internal/bot-configs` | `{client_id, name, route, script_id, script_config_id?, telephony_number, credits_per_minute}` | `{id}` (422 bad script_id/route) |
| GET | `/internal/bot-configs` | `client_id?, search?` | `{bot_configs:[...]}` (hides "CLI Sandbox") |
| GET | `/internal/bot-configs/{id}` | | `{bot_config}` |
| PATCH | `/internal/bot-configs/{id}` | partial fields incl. `active` | `{bot_config}` |

### Campaigns (admin)
| Method | Path | Body / Query | Response | Notes |
|--------|------|--------------|----------|-------|
| POST | `/internal/campaigns` | `CreateCampaignBody` (+`client_id`) | `{id, campaign, balance_credits}` | allocates budget |
| GET | `/internal/campaigns` | `client_id?, search?` | `{campaigns}` | all campaigns (LIMIT 200) if no client_id; hides "CLI Test Sandbox" |
| GET | `/internal/campaigns/{id}` | | `{campaign}` | `get_campaign_admin` (no client filter) |
| PATCH | `/internal/campaigns/{id}` | `PatchCampaignBody` | `{campaign}` | |
| PATCH | `/internal/campaigns/{id}/start` | | `{status, counters, ...}` | budget ≥2 (400); 409 bad state |
| PATCH | `/internal/campaigns/{id}/stop` | | `{status:"paused", released_calling_leads}` | admin stop forces `paused` |
| PATCH | `/internal/campaigns/{id}/cancel` | | `{campaign_id, ...}` | |
| POST | `/internal/campaigns/{id}/reconcile` | | `{campaign_id, counters}` | recompute counters |
| POST | `/internal/campaigns/{id}/release-stuck` | | `{campaign_id, released}` | |
| GET | `/internal/campaigns/{id}/leads` | `limit, offset, status?` | `{leads, total_count}` | |

### Calls (admin)
| Method | Path | Query | Response |
|--------|------|-------|----------|
| GET | `/internal/calls` | `limit, offset, search?` | `{calls, total_count}` (incl. test calls) |
| GET | `/internal/calls/{session_call_id}` | | `{call}` (404) |
| GET | `/internal/calls/{session_call_id}/recording` | | file or `{url, expires_in}` |

### Webhooks / scripts / stats / health
| Method | Path | Body / Query | Response |
|--------|------|--------------|----------|
| POST | `/internal/webhook-configs` | `{client_id, event, url, secret}` | `{id}` (upsert by client+event) |
| GET | `/internal/scripts` | | `{scripts:[{route, script_id}]}` (filesystem scan) |
| GET | `/internal/stats` | | `{total_calls_today, active_campaigns, total_credits_used_today}` |
| GET | `/internal/health` | | `{status, active_calls, pool:{size,idle}, plivo_balance, dialer_tasks}` |

### Script configs (`/internal/script-configs`) — `internal_script_configs.py`
Verified endpoints (from frontend usage + route file): create, list
(`?active_only=`), get, patch, revisions, rollback, template (`?route=`),
dial-test, and an extraction test. See file for exact bodies.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/internal/script-configs` | list (supports `?active_only=false`) |
| GET | `/internal/script-configs/template?route=sts\|cascaded` | starter template |
| POST | `/internal/script-configs` | create |
| GET | `/internal/script-configs/{id}` | get one |
| PATCH | `/internal/script-configs/{id}` | update (header used for version note) |
| GET | `/internal/script-configs/{id}/revisions` | history |
| POST | `/internal/script-configs/{id}/rollback` | `{version}` rollback |
| POST | `/internal/script-configs/{id}/dial-test` | place a test call with this config |
| POST | (extraction test endpoint) | run extraction against a transcript |

> The exact request schemas for script-config create/patch/dial-test/extraction-
> test are defined in `api/routes/internal_script_configs.py` and validated by
> `api/script_config_validation.py`. **Not transcribed field-by-field here** —
> consult those files for authoritative shapes before building the admin UI.

---

# TELEPHONY / SYSTEM endpoints (no auth)

| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| POST | `/start` | place an outbound call (manual/test) | `{phone_number, body?}` → `{call_uuid, call_id, status, route}` |
| GET/POST | `/answer` | Plivo answer webhook → returns `<Stream>` XML | waits ≤3s for prewarm; links call_sid; starts recording |
| WS | `/ws` | Pipecat audio WebSocket | `?call_id=&body=<base64>` |
| GET/POST | `/plivo-hangup` | Plivo hangup webhook | records hangup, settles unanswered |
| GET/POST | `/plivo-recording` | Plivo recording webhook | stores `recording_url` |
| GET | `/health` | liveness | `{status:"ok", route}` |

**These are NOT for the new frontend.** They are Plivo↔backend integration
points. A frontend never calls them.

---

## HTTP error semantics (verified)

| Code | When |
|------|------|
| 400 | bad body / insufficient budget / malformed upload |
| 401 | bad/missing client Bearer token |
| 403 | bad/missing `X-Admin-Key` |
| 404 | resource not found / wrong owner |
| 409 | action not allowed in current campaign/lead state |
| 422 | FastAPI validation (bad UUID, bad enum, invalid script_id) |
| 429 | rate limit (100/min/IP) |
| 503 | Postgres not configured/unavailable |

Error body shape: FastAPI default `{ "detail": <str | obj> }`. The frontend
axios interceptors read `error.response.data.detail` (string) for toasts; upload
returns `detail: {errors: [...]}` (object).

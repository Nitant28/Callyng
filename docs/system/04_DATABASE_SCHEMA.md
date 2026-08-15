# 04 — Database Schema

System of record: **PostgreSQL 16** (asyncpg). Schema defined in
`db/schema/001_initial.sql` … `006_script_configs.sql` and refined by
`alembic/versions/007…010`. Secondary stores: **Redis** (ephemeral) and
**SQLite** (`call_log_db.py`, parallel transcript log).

Conventions verified across `db/postgres.py`:
- Every business table has `client_id UUID` and **every query filters by it**
  (multi-tenant isolation). Admin reads use `get_campaign_admin` /
  `list_call_logs(client_id=None)` which bypass the client filter.
- Denormalized counters on `campaigns` are the canonical stats — see
  `11_STATISTICS_ENGINE.md`.
- 1 credit = ₹1 at launch (per schema comments).

---

## Entity-relationship overview

```
clients 1───∞ bot_configs            bot_configs ∞───1 script_configs (script_config_id, ON DELETE SET NULL)
clients 1───∞ campaigns              campaigns   ∞───1 bot_configs
clients 1───∞ leads                  leads       ∞───1 campaigns
clients 1───∞ call_logs              call_logs   ∞───1 leads, ∞───1 campaigns, ∞───1 bot_configs
clients 1───∞ webhook_configs
clients 1───∞ credit_transactions
clients 1───∞ script_configs         script_configs 1───∞ script_config_revisions
```

All FKs to `clients(id)` are `ON DELETE CASCADE` (deleting a client wipes its
data). `campaigns.bot_config_id → bot_configs(id)` has no cascade.
`call_logs.campaign_id/lead_id/bot_config_id` are nullable references (no cascade
on lead, so call_logs survive lead deletion — verified in `delete_lead` docstring
"call_logs are preserved").

---

## Table: `clients`

**Purpose:** one row per paying client (company/tenant). Holds the master credit
pool, concurrency ceiling, and the hashed API key.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `name` | VARCHAR(255) NOT NULL | client/company name |
| `contact_email` | VARCHAR(255) | |
| `industry` | VARCHAR(100) | real_estate/insurance/edtech/lending/healthcare/other |
| `api_key_hash` | VARCHAR(64) NOT NULL UNIQUE | **SHA-256 hex** of raw key. Raw key shown once. |
| `balance_credits` | NUMERIC(12,2) DEFAULT 0 | master pool. Pre-deducted at campaign budget allocation. |
| `max_concurrent_calls` | INTEGER DEFAULT 5 | hard ceiling across all this client's campaigns |
| `active` | BOOLEAN DEFAULT TRUE | inactive clients can't authenticate / allocate budget |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |

**Auth:** incoming Bearer key is SHA-256 hashed (`hash_api_key`) and compared to
`api_key_hash` (`get_client_by_token`). Raw keys are never stored or logged.

**Written by:** `POST /internal/clients` (create), `POST /internal/clients/{id}/regenerate-key`,
`PATCH /internal/clients/{id}` (name/email/industry), `PATCH /internal/clients/{id}/status`,
`PATCH /internal/clients/{id}/credits` (via `add_credits`), and budget
allocation/return (`allocate_campaign_budget`, `return_unused_budget`).
**Read by:** `get_client_from_token` (every client request), `GET /api/credits`,
`GET /internal/clients`, `GET /internal/clients/{id}`.
**Frontend screens:** Admin Clients/ClientDetail; Client Dashboard (balance via
`/api/credits`), Login (validation).

---

## Table: `bot_configs`

**Purpose:** registry binding a client to a runnable bot: route + script_id +
DID + per-minute price + optional dynamic `script_config_id`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients ON DELETE CASCADE | |
| `name` | VARCHAR(255) NOT NULL | internal label |
| `route` | VARCHAR(20) NOT NULL CHECK in (`sts`,`cascaded`) | |
| `script_id` | VARCHAR(100) NOT NULL | resolves `sts_scripts/<id>.py` or `cascade_scripts/<id>.py`; validated `^[a-z][a-z0-9_]*$` |
| `telephony_number` | VARCHAR(20) | Plivo DID (E.164) |
| `credits_per_minute` | NUMERIC(6,2) NOT NULL | ₹ per connected minute (pro-rata per second) |
| `fixed_start_credits` | NUMERIC(10,4) NOT NULL DEFAULT 0.6000 | setup fee when Plivo accepts the dial |
| `active` | BOOLEAN DEFAULT TRUE | |
| `script_config_id` | UUID → script_configs ON DELETE SET NULL | added in 006; non-null = use DB script config |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |

**Written by:** `POST /internal/bot-configs`, `PATCH /internal/bot-configs/{id}`.
**Read by:** campaign creation (validates ownership), post-call billing
(`credits_per_minute`), lead-schema resolution, `GET /internal/bot-configs`,
`AdminDataContext` (frontend cache).
**Indexes:** `idx_bot_configs_script_config_id`.
**Frontend screens:** Admin BotConfigs, AdminScriptConfigs (binding), used
indirectly by campaign stats (`bot_config` embedded in client stats response).

---

## Table: `campaigns`

**Purpose:** one campaign = one bot_config + one lead set + one run. Holds budget,
dialer throttle, retry policy, and the **denormalized lead counters** (the
canonical statistics).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `bot_config_id` | UUID NOT NULL → bot_configs | |
| `name` | VARCHAR(255) NOT NULL | |
| `status` | VARCHAR(50) DEFAULT 'draft' CHECK in (`draft`,`running`,`pausing`,`paused`,`completed`,`cancelled`) | |
| `budget_credits` | NUMERIC(12,2) DEFAULT 0 | pre-allocated from `clients.balance_credits` |
| `budget_used_credits` | NUMERIC(12,2) DEFAULT 0 | reservation + actual billing accumulator |
| `max_concurrent_calls` | INTEGER DEFAULT 5 | ≤ client ceiling |
| `calls_per_minute` | INTEGER DEFAULT 10 | dialer launch rate |
| `max_attempts` | INTEGER DEFAULT 3 | copied to `leads.max_attempts` at upload (frozen) |
| `retry_delay_minutes` | INTEGER DEFAULT 120 | |
| `scheduled_start_at` | TIMESTAMPTZ | nullable; not heavily used (Not verified active in dialer this pass) |
| `completed_at` | TIMESTAMPTZ | |
| `budget_returned_at` | TIMESTAMPTZ | idempotency guard for budget settlement (003) |
| `max_call_minutes` | INTEGER DEFAULT NULL | per-call duration cap (004) |
| `total_leads` | INTEGER DEFAULT 0 | **counter** |
| `pending_leads` | INTEGER DEFAULT 0 | **counter** |
| `calling_leads` | INTEGER DEFAULT 0 | **counter** |
| `callback_leads` | INTEGER DEFAULT 0 | **counter** |
| `completed_leads` | INTEGER DEFAULT 0 | **counter** (terminal: Interested/Not_Interested) |
| `failed_leads` | INTEGER DEFAULT 0 | **counter** |
| `extraction_schema_override` | JSONB DEFAULT NULL | per-campaign extraction override |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |

> **`dnc_leads` was removed** in migration `007_remove_dnc`. The `leads.status`
> CHECK no longer includes `dnc`.

**Counters are maintained incrementally** in the same transaction as each lead
status change (`increment_campaign_counters`), and recomputed authoritatively by
`reconcile_campaign_counters` (full `COUNT(*) FILTER`). See `11_STATISTICS_ENGINE.md`.

**Written by:** `create_campaign` (POST `/internal/campaigns`, `/api/campaigns`),
`update_campaign_status`, `update_campaign_settings`, budget functions, counter
functions, settlement. **Read by:** `GET /api/campaigns`, `/api/campaigns/{id}/stats`,
`/internal/campaigns`, dialer loop, post-call.
**Frontend screens:** Client Dashboard (campaign cards), CampaignDetail (all
metric cards), Admin Campaigns/ClientDetail.

---

## Table: `leads`

**Purpose:** one row per person to call within a campaign. Drives the dialer state
machine; carries the latest promoted outcome + extraction.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `campaign_id` | UUID NOT NULL → campaigns CASCADE | |
| `phone` | VARCHAR(20) NOT NULL | E.164, normalized on upload |
| `name` | VARCHAR(255) | injected as `{lead_name}` |
| `lead_type` | VARCHAR(20) DEFAULT 'cold' CHECK (cold/warm/hot) | |
| `status` | VARCHAR(50) DEFAULT 'pending' CHECK (pending/calling/completed/failed/callback_scheduled) | |
| `attempts` | INTEGER DEFAULT 0 | incremented at dial claim |
| `max_attempts` | INTEGER DEFAULT 3 | frozen from campaign at upload |
| `last_attempted_at` | TIMESTAMPTZ | |
| `next_attempt_at` | TIMESTAMPTZ DEFAULT NOW() | dialer eligibility gate; powers `idx_leads_dialer` |
| `scheduled_callback_at` | TIMESTAMPTZ | set on callback outcome |
| `metadata` | JSONB DEFAULT '{}' | domain CSV fields; injected via `string.Template` (safe) |
| `outcome` | VARCHAR(50) | latest promoted intent_status |
| `extraction` | JSONB DEFAULT '{}' | latest promoted extraction |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |
| | | **UNIQUE (campaign_id, phone)** — duplicate phone silently skipped on upload |

**State machine** (verified `post_call_processor._lead_transition` +
`leads.py _MANUAL_TRANSITIONS`):
```
pending ──claim──> calling ──post-call──> completed | failed | callback_scheduled
callback_scheduled ──next_attempt_at<=NOW()──> calling
(manual transitions allowed: pending↔failed↔completed↔callback_scheduled per table; never manual→calling)
```

**Written by:** upload (`bulk_insert_leads`), `insert_single_lead`,
`update_lead_fields`, `update_lead_status_manual`, `delete_lead`, dialer claim
(`claim_leads_for_dialer`), `update_lead_post_call`, `release_stuck_calling_leads`,
`terminalize_campaign_leads`, `bump_pending_retry_to_now`.
**Read by:** `GET /api/campaigns/{id}/leads` (with LATERAL join to latest
call_log), dialer, post-call.
**Indexes:** `idx_leads_dialer` (partial: campaign_id, next_attempt_at WHERE
status in pending/callback_scheduled — **the hottest index**), `idx_leads_campaign_status`,
`idx_leads_client`.
**Frontend screens:** CampaignDetail lead table; Admin campaign leads.

---

## Table: `call_logs`

**Purpose:** one row per **call attempt** (a lead with 3 attempts → 3 rows). Full
audit trail + live transcript polling source + billing record + per-attempt
extraction.

Key columns (see `001_initial.sql` lines 321–435 + `002_compat.sql`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `campaign_id` / `lead_id` / `bot_config_id` | UUID (nullable FKs) | |
| `session_call_id` | VARCHAR(255) | our UUID from `/start`; **frontend polls by this** |
| `call_sid` | VARCHAR(255) | Plivo CallUUID (linked at `/answer`) |
| `started_at` | TIMESTAMPTZ | set at insert (call start) |
| `ended_at` | TIMESTAMPTZ | set by finalize |
| `duration_seconds` | INTEGER | connected duration |
| `billed_minutes` | NUMERIC(10,4) | `duration_seconds / 60` (15s → 0.2500) |
| `credits_charged` | NUMERIC(10,4) | setup + billed_minutes × rate (4 dp) |
| `route` | VARCHAR(20) CHECK (sts/cascaded) | |
| `outcome` | VARCHAR(50) | this attempt's outcome |
| `qualified` | BOOLEAN DEFAULT FALSE | `outcome == 'Interested'` |
| `in_progress` | BOOLEAN DEFAULT TRUE | **TRUE while live → frontend polls** |
| `transcript` | JSONB DEFAULT '[]' | array of `{role, content, ts,...}` turns |
| `usage_prompt_tokens` / `usage_completion_tokens` / `usage_total_tokens` / `usage_tts_characters` | INTEGER | from `call_metrics` |
| `cost_usd` | NUMERIC(10,6) | internal margin (never shown to client) |
| `extraction_json` | JSONB DEFAULT '{}' | raw per-attempt extraction |
| `extraction_model` | VARCHAR(100) | e.g. `groq/llama-3.3-70b-versatile` |
| `extraction_error` | TEXT | |
| `quality_score` / `flagged_for_review` | INTEGER / BOOLEAN | Phase 3 placeholders |
| `recording_url` | TEXT | `local:<file>` \| `plivo:<url>` \| R2 key |
| `call_data` | JSONB DEFAULT '{}' | overflow: `budget_reserved_credits`, `is_test_call`, post-call snapshot, prewarm timings |
| `plivo_hangup_json` | JSONB DEFAULT '{}' | hangup payload incl. `hangup_source` (002) |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |

**Lifecycle:** inserted `in_progress=TRUE` at dial (`insert_call_log_start`),
transcript appended per turn, finalized (`finalize_call_log`: in_progress=FALSE,
duration, billing, outcome, extraction, usage), or settled at 0 credits for
unanswered (`settle_unanswered_call`).

**Written by:** dialer (`insert_call_log_start`), `link_call_log_plivo_sid`,
`append_transcript_turn`, `finalize_call_log`, `mark_call_log_not_in_progress`,
`record_plivo_hangup`, `settle_unanswered_call`, `update_call_log_recording_url`,
`patch_call_log_post_call_snapshot`.
**Read by:** `GET /api/calls`, `/api/calls/{session_call_id}`, recording routes,
`/internal/calls*`, `/internal/stats`, `/internal/health`, stale sweep.
**Indexes:** `idx_call_logs_lead`, `idx_call_logs_campaign`,
`idx_call_logs_client_date`, `idx_call_logs_live` (partial WHERE in_progress),
`idx_call_logs_lead_live`, `idx_call_logs_lead_ended`, `idx_call_logs_call_sid`,
plus 009 added indexes.
**Frontend screens:** CallLogs list + CallTranscriptDrawer; Admin Calls/Diagnostics.

> **Test calls** are tagged `call_data->>'is_test_call' = 'true'` and are
> **excluded** from client-facing `get_call_log` / `get_latest_call_log_for_lead`
> / `list_call_logs` (but NOT from admin `list_call_logs(client_id=None)`).

---

## Table: `webhook_configs`

**Purpose:** per-client, per-event n8n webhook URL + HMAC secret.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `event` | VARCHAR(50) NOT NULL | `lead_qualified`/`lead_not_interested`/`lead_callback`/`lead_failed`/`campaign_completed` |
| `url` | TEXT NOT NULL | n8n endpoint |
| `secret` | VARCHAR(255) | HMAC-SHA256 signing secret |
| `active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |
| | | **UNIQUE (client_id, event)** |

**Written by:** `POST /internal/webhook-configs` (`upsert_webhook_config`).
**Read by:** `get_webhook_config_for_event` (post-call), `GET /internal/clients/{id}/webhooks`.
**Frontend screens:** Admin Webhooks, AdminClientDetail (webhooks list).

---

## Table: `credit_transactions` (migration 005)

**Purpose:** append-only ledger of manual credit movements.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `amount` | NUMERIC(12,2) NOT NULL | positive = top-up |
| `note` | TEXT | |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | |

**Written by:** `add_credits` (`PATCH /internal/clients/{id}/credits`).
**Read by:** `GET /internal/clients/{id}/credits` (`list_credit_transactions`).
**Frontend screens:** AdminClientDetail (ledger).
> Note: this ledger records **manual top-ups** only. Budget allocation/return
> mutate `clients.balance_credits` directly and are **not** recorded here (Not
> verified that allocation writes ledger rows — code shows it does not).

---

## Table: `script_configs` (migration 006) — dynamic AI CMS

**Purpose:** database-driven bot persona + Gemini/cascade settings + post-call
extraction/normalization/outcome mapping. Lets admins change prompts without code
deploys.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID NOT NULL → clients CASCADE | |
| `script_id` | TEXT NOT NULL | |
| `route` | TEXT NOT NULL CHECK (sts/cascaded) | |
| `gemini_model` | TEXT DEFAULT 'models/gemini-3.1-flash-live-preview' | |
| `gemini_voice` | TEXT DEFAULT 'Aoede' | |
| `gemini_language` | TEXT DEFAULT 'hi-IN' | |
| `gemini_temperature` | NUMERIC(3,2) DEFAULT 0.50 | |
| `vad_start_sensitivity` / `vad_end_sensitivity` | TEXT (HIGH/LOW) | |
| `vad_silence_duration_ms` / `vad_prefix_padding_ms` | INT (800 / 300) | |
| `system_instruction_template` | TEXT NOT NULL | `string.Template` with lead vars |
| `bootstrap_messages_json` | JSONB DEFAULT '[]' | |
| `goodbye_markers` | JSONB DEFAULT '[]' | phrases that trigger hangup |
| `cascade_stt_provider/model`, `cascade_llm_provider/model`, `cascade_tts_provider/voice` | TEXT | defaults sarvam/groq/cartesia |
| `cascade_live_tools` | JSONB DEFAULT '[]' | function tools for cascade |
| `extraction_schema` | JSONB NOT NULL | post-call schema |
| `lead_schema` | JSONB DEFAULT '{"fields": []}' | CSV validation schema |
| `normalization_rules` | JSONB DEFAULT '[]' | declarative outcome normalization |
| `outcome_event_map` | JSONB DEFAULT '{}' | outcome → webhook event |
| `outcome_terminal` | JSONB DEFAULT '["Interested","Not_Interested"]' | |
| `outcome_retry` | JSONB DEFAULT '["Busy","Unknown","Wrong_Requirement"]' | |
| `outcome_callback` | JSONB DEFAULT '["Callback_Requested"]' | (010 appends `Early_Disconnect` for pyramid) |
| `active` | BOOLEAN DEFAULT true | |
| `version` | INT DEFAULT 1 | |
| `created_at` / `updated_at` | TIMESTAMPTZ | |
| | | **UNIQUE (client_id, script_id)** |

**Written by:** `/internal/script-configs` create/patch/rollback.
**Read by:** dialer prefetch (`script_prefetch`), `script_runtime`, lead-schema
resolution, `/internal/script-configs` list/get.
**Indexes:** `idx_script_configs_client_id`.
**Frontend screens:** AdminScriptConfigs.

---

## Table: `script_config_revisions` (migration 006)

**Purpose:** immutable version history for `script_configs` (rollback support).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `script_config_id` | UUID NOT NULL → script_configs CASCADE | |
| `version` | INT NOT NULL | |
| `config_snapshot` | JSONB NOT NULL | full snapshot at that version |
| `created_at` | TIMESTAMPTZ | |
| | | **UNIQUE (script_config_id, version)** |

**Written by:** `_insert_script_config_revision` (on create/update/rollback).
**Read by:** `GET /internal/script-configs/{id}/revisions`, rollback.
**Frontend screens:** AdminScriptConfigs (history modal).

---

## Redis keys (ephemeral; `db/redis_client.py` + callers)

| Key prefix | Set by | Consumed by | Purpose |
|------------|--------|-------------|---------|
| `warmup:<call_id>` | `set_warmup_pending/ready` (`/start`, prewarm) | `wait_for_warmup` (`/answer`) | Gemini prewarm signal |
| `dialer_lock:<campaign_id>` | `dialer/dialer_lock.py` | dialer loop | single-worker campaign lock |
| `prefetch:<call_id>` (`script_prefetch._PREFETCH_KEY_PREFIX`) | dialer | `/ws` (`pop_prefetched_config`) | rendered script config per call |
| `pgctx:<call_id>` (`call_transcript._PGCTX_KEY_PREFIX`) | `/ws` (`register_pg_context`) | post-call | campaign/lead/bot context |
| slowapi storage | rate limiter | rate limiter | request counts |

Exact key formats: **Not fully verified** here for the lock/prefetch/pgctx string
templates — see the respective modules for exact prefixes.

---

## SQLite (`call_log_db.py`, `data/call_logs.db`)

Single-tenant, Phase-0. Table `call_logs(id, session_call_id, plivo_call_id,
route, started_at, ended_at, duration_ms, transcript_json, usage_*, extraction_*,
cost_inr, recording_path)`. Written by `call_transcript` on every call regardless
of Postgres. **Not used by any `/api/*` or `/internal/*` endpoint** — irrelevant
to the new frontend, but do not assume it's dead (the bots still write it).

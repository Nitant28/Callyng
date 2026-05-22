# Aakashvani — Complete Architecture & Design Reference
> Phase 2 design document. Final version incorporating all decisions from design session.
> This is the source of truth for database schema, system behaviour, and implementation contracts.
> Last updated: May 2026
>
> **Related documents:** [README.md](README.md) (dev setup) · [ROADMAP.md](ROADMAP.md) (phases & vision).
> ROADMAP §6 defers Postgres schema detail to this file. If README or ROADMAP conflict with this doc, **this doc wins**.

---

## Table of contents

1. [System model](#1-system-model)
2. [Database schema — complete](#2-database-schema--complete)
3. [Schema design decisions — rationale](#3-schema-design-decisions--rationale)
4. [Credit and billing system](#4-credit-and-billing-system)
5. [Bot configuration model](#5-bot-configuration-model)
6. [Lead lifecycle and state machine](#6-lead-lifecycle-and-state-machine)
7. [Concurrent dialer](#7-concurrent-dialer)
8. [Post-call extraction](#8-post-call-extraction)
9. [Webhook system](#9-webhook-system)
10. [Security contracts](#10-security-contracts)
11. [Live call visibility](#11-live-call-visibility)
12. [CSV/Excel upload pipeline](#12-csvexcel-upload-pipeline)
13. [Admin-first build order](#13-admin-first-build-order)
14. [File layout](#14-file-layout)
15. [Environment variables](#15-environment-variables)
16. [Open questions](#16-open-questions)

---

## 1. System model

Aakashvani is a **managed voice automation service**. Clients buy outcomes, not tools.

### What we own and operate
- Bot scripts, prompts, voice config, VAD settings — all in script files we control
- n8n workflow design and CRM integration — built by us during onboarding
- Plivo number assignment
- Server and infrastructure
- Extraction schema design per campaign
- Credit allocation to campaigns

### What clients can touch
- Add credits to their account (manual bank transfer → we top up, Razorpay later)
- Upload a CSV of leads to a campaign we already configured
- Start / pause / stop a campaign
- Watch live call progress and transcripts
- View call logs, extraction results, audio (Phase 4)
- View credit balance

### Multi-tenancy model
One codebase, one database, one server. Isolation is application-layer via `client_id`. Every query on every table includes `WHERE client_id = $n`. There are no per-client deployments.

### Two voice routes
- `sts` — Gemini Live speech-to-speech. ~0.5–1s latency. Script in `sts_scripts/<script_id>.py`.
- `cascaded` — Sarvam STT → Groq LLM → Cartesia TTS. ~1.5–2.5s latency. Script in `cascade_scripts/<script_id>.py`.

Route is set per bot_config. The DB stores the route and script_id. The script file contains everything operational (prompts, VAD, models, extraction schema, lead schema).

### Credit model (key concept)
Clients buy **credits**. At launch, 1 credit = ₹1. Later, packs can give better rates (e.g. 1000 credits for ₹800). The credit amount in the account is always credits — only the purchase conversion rate changes per pack. Billed in **ceiling minutes**: 61 seconds = 2 billed minutes. Each bot has a `credits_per_minute` cost set by us.

---

## 2. Database schema — complete

```sql
-- ============================================================
-- AAKASHVANI — PostgreSQL 16 complete schema
-- Multi-tenant: client_id on every table, every query
-- Credits model: ceiling billing, 1 credit = ₹1 at launch
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- CLIENTS
-- One row per paying client (company).
-- api_key_hash: SHA-256 of actual key. Key shown once on creation.
-- balance_credits: master credit pool. Pre-deducted at campaign
-- budget allocation. Unused credits returned on campaign completion.
-- max_concurrent_calls: hard ceiling across ALL campaigns for
-- this client simultaneously.
-- ============================================================
CREATE TABLE clients (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 VARCHAR(255) NOT NULL,
    contact_email        VARCHAR(255),
    industry             VARCHAR(100),
    -- 'real_estate' | 'insurance' | 'edtech' | 'lending' | 'healthcare' | 'other'

    api_key_hash         VARCHAR(64) NOT NULL UNIQUE,
    -- SHA-256 hex of the actual key. Key shown to client ONCE on creation.
    -- Auth: hash incoming bearer token, compare to this column.
    -- Never store raw key. Never log raw key.

    balance_credits      NUMERIC(12,2) DEFAULT 0,
    -- Master credit pool. 1 credit = ₹1 at launch.
    -- Deducted at campaign budget allocation (not per call).
    -- Unused campaign credits returned here on campaign completion.
    -- Topped up manually by admin (Razorpay automation in Phase 3).

    max_concurrent_calls INTEGER DEFAULT 5,
    -- Hard ceiling. Sum of calling_leads across all active campaigns
    -- for this client cannot exceed this number.

    active               BOOLEAN DEFAULT TRUE,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- BOT CONFIGS
-- Registry entry only. All operational config lives in the
-- script file: sts_scripts/<script_id>.py or
-- cascade_scripts/<script_id>.py
--
-- DB stores: who owns it, which file runs it, what it costs.
-- Script file stores: prompts, VAD, models, LEAD_SCHEMA,
-- EXTRACTION_SCHEMA, function config, call limits, everything else.
--
-- script_id validated on insert: re.fullmatch(r'[a-z][a-z0-9_]*')
-- Prevents path traversal. '../secrets' fails the regex.
--
-- credits_per_minute: set by us based on route + providers used.
-- Billed in ceiling minutes: ceil(duration_seconds / 60).
-- Clients never see this number — they see credits consumed.
-- ============================================================
CREATE TABLE bot_configs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    name                 VARCHAR(255) NOT NULL,
    -- Internal label e.g. "Diya - Pyramid Parkland - Marathi"

    route                VARCHAR(20) NOT NULL
                             CHECK (route IN ('sts', 'cascaded')),
    -- 'sts'      → sts_scripts/<script_id>.py  (Gemini Live)
    -- 'cascaded' → cascade_scripts/<script_id>.py (Sarvam+Groq+Cartesia)

    script_id            VARCHAR(100) NOT NULL,
    -- e.g. 'pyramid_mr', 'pyramid_hi', 'prowave_hi'
    -- Combined with route to resolve: sts_scripts/pyramid_mr.py
    -- Validated: re.fullmatch(r'[a-z][a-z0-9_]*', script_id)

    telephony_number     VARCHAR(20),
    -- Plivo DID assigned to this bot. E.164: '+912240000000'

    credits_per_minute   NUMERIC(6,2) NOT NULL,
    -- Credits charged per billed minute for calls using this bot.
    -- Billed minute = ceil(duration_seconds / 60).
    -- 61 seconds → 2 billed minutes → 2 * credits_per_minute deducted.
    -- Example: 1.49 for cascaded Sarvam+Groq+Cartesia.
    -- Set by us. Reflects our provider costs + margin.

    active               BOOLEAN DEFAULT TRUE,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- CAMPAIGNS
-- One campaign = one bot_config + one CSV upload + one run.
-- Single bot per campaign. Managed service: we configure the
-- bot and campaign; client uploads leads and starts/stops.
--
-- CREDITS (pre-allocation model, eliminates race conditions):
--   At campaign start:
--     clients.balance_credits  -= budget_credits   (one-time deduction)
--   Per call end:
--     budget_used_credits      += billed_minutes * credits_per_minute
--   At campaign completion:
--     clients.balance_credits  += (budget_credits - budget_used_credits)
--
-- COUNTERS: denorm. Updated in same DB transaction as every lead
-- status change. Never computed with COUNT(*).
-- At 50k leads, COUNT(*) on dashboard refresh = unacceptable.
--
-- EXTRACTION OVERRIDE: campaign-specific extraction config.
-- NULL = use script module's EXTRACTION_SCHEMA.
-- Non-null = use this instead (same JSON structure as EXTRACTION_SCHEMA).
-- Useful when running the same bot across campaigns with different
-- reporting needs (one wants fields, another wants summary only).
-- ============================================================
CREATE TABLE campaigns (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    bot_config_id        UUID NOT NULL REFERENCES bot_configs(id),

    name                 VARCHAR(255) NOT NULL,
    -- e.g. "Pune Dec Batch", "Mumbai Jan Warm Leads"

    status               VARCHAR(50) DEFAULT 'draft'
                             CHECK (status IN ('draft', 'running', 'paused',
                                               'completed', 'cancelled')),
    -- draft      → campaign configured, no leads uploaded or dialer not started
    -- running    → dialer actively placing calls
    -- paused     → dialer stopped, leads preserved, can resume
    -- completed  → all leads in terminal state, unused credits returned
    -- cancelled  → manually cancelled, unused credits returned

    -- ── CREDITS ──────────────────────────────────────────────
    budget_credits       NUMERIC(12,2) DEFAULT 0,
    -- Pre-allocated from clients.balance_credits at campaign start.
    -- Deducted from master balance once. Not touched per call.

    budget_used_credits  NUMERIC(12,2) DEFAULT 0,
    -- Running total of credits consumed. Incremented per call:
    -- += ceil(duration_seconds / 60) * bot_config.credits_per_minute
    -- Atomic SQL increment — no race condition possible.

    -- ── DIALER THROTTLE ───────────────────────────────────────
    max_concurrent_calls INTEGER DEFAULT 5,
    -- Maximum simultaneous live calls for this campaign.
    -- Cannot exceed clients.max_concurrent_calls.
    -- Dialer checks: slots = max_concurrent_calls - calling_leads

    calls_per_minute     INTEGER DEFAULT 10,
    -- Rate limit on how fast the dialer launches new calls.
    -- Prevents Plivo rate limit bursts when calls are short.
    -- Dialer sleeps 60/calls_per_minute seconds between launch batches.
    -- Example: calls_per_minute=10 → sleep 6s between batches.

    -- ── RETRY POLICY ─────────────────────────────────────────
    max_attempts         INTEGER DEFAULT 3,
    -- How many total call attempts per lead before marking failed.
    -- Copied to leads.max_attempts on upload (frozen per lead).
    -- Changing this mid-campaign does NOT affect already-uploaded leads.

    retry_delay_minutes  INTEGER DEFAULT 120,
    -- Minutes to wait before retrying a Busy or Unknown lead.
    -- Sets leads.next_attempt_at = NOW() + retry_delay_minutes.

    -- ── SCHEDULING ────────────────────────────────────────────
    scheduled_start_at   TIMESTAMPTZ,
    -- NULL = start immediately when status set to 'running'.
    -- Non-null = dialer waits until this timestamp.

    completed_at         TIMESTAMPTZ,
    -- Stamped when dialer marks all leads terminal and returns unused credits.

    -- ── DENORM COUNTERS ───────────────────────────────────────
    -- Updated in same transaction as lead status change. Never COUNT(*).
    total_leads          INTEGER DEFAULT 0,
    pending_leads        INTEGER DEFAULT 0,
    -- Waiting to be called (next_attempt_at <= NOW() or in future)
    calling_leads        INTEGER DEFAULT 0,
    -- Currently in a live call (status = 'calling')
    callback_leads       INTEGER DEFAULT 0,
    -- Scheduled for callback (status = 'callback_scheduled')
    completed_leads      INTEGER DEFAULT 0,
    -- Terminal: Interested or Not_Interested
    failed_leads         INTEGER DEFAULT 0,
    -- Attempts exhausted, no qualified outcome
    dnc_leads            INTEGER DEFAULT 0,
    -- Do Not Call: opted out during call or flagged on upload

    -- ── EXTRACTION OVERRIDE ───────────────────────────────────
    extraction_schema_override JSONB DEFAULT NULL,
    -- NULL → use script module's EXTRACTION_SCHEMA (default)
    -- Non-null → use this JSON for this campaign only.
    -- Same structure as EXTRACTION_SCHEMA in the script file.
    -- Example (summary-only override):
    -- {
    --   "mode": "summary",
    --   "summary_prompt": "One sentence: interested or not, and why."
    -- }

    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- LEADS
-- One row per person to be called in a campaign.
--
-- STATUS MACHINE:
--   pending
--     → calling              (dialer claims with FOR UPDATE SKIP LOCKED)
--     → completed            (terminal outcome received)
--     → failed               (attempts >= max_attempts, no terminal outcome)
--     → dnc                  (opted out during call, or TRAI/internal DND)
--     → callback_scheduled   (lead asked to be called back at specific time)
--   callback_scheduled
--     → calling              (when next_attempt_at <= NOW())
--
-- METADATA: all domain-specific CSV columns beyond phone/name.
-- Validated against script.LEAD_SCHEMA on upload.
-- Keys injected into system_prompt via safe string.Template substitution.
-- NEVER use .format(**metadata) — prompt injection risk.
--
-- EXTRACTION: latest Groq/Gemini output promoted from call_logs
-- after each call attempt. This is what n8n reads and the
-- dashboard shows. call_logs.extraction_json has per-attempt raw output.
--
-- UNIQUE (campaign_id, phone): duplicate phone in same campaign
-- → silently skipped on upload. Not an error.
-- ============================================================
CREATE TABLE leads (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id               UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    campaign_id             UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,

    -- ── CORE IDENTITY ─────────────────────────────────────────
    phone                   VARCHAR(20) NOT NULL,
    -- Always E.164: +919876543210. Normalised on upload via phonenumbers lib.
    -- Indian formats handled: 10-digit → +91 prefix, 0-prefix, +91 already.

    name                    VARCHAR(255),
    -- Lead's name. Injected into prompt as {lead_name}.

    lead_type               VARCHAR(20) DEFAULT 'cold'
                                CHECK (lead_type IN ('cold', 'warm', 'hot')),
    -- cold: no prior engagement
    -- warm: showed interest before
    -- hot:  ready to buy / high intent signal

    -- ── DIALER STATE MACHINE ──────────────────────────────────
    status                  VARCHAR(50) DEFAULT 'pending'
                                CHECK (status IN ('pending', 'calling', 'completed',
                                                  'failed', 'dnc', 'callback_scheduled')),

    attempts                INTEGER DEFAULT 0,
    -- How many call attempts have been made. Incremented in post_call_processor.

    max_attempts            INTEGER DEFAULT 3,
    -- Copied from campaign.max_attempts AT UPLOAD TIME. Frozen.
    -- Dialer checks: if attempts >= max_attempts → mark failed.

    last_attempted_at       TIMESTAMPTZ,
    -- Timestamp of most recent call attempt start.

    next_attempt_at         TIMESTAMPTZ DEFAULT NOW(),
    -- Dialer will not touch this lead until NOW() >= next_attempt_at.
    -- Fresh leads: set to NOW() (available immediately).
    -- After retry (Busy/Unknown): set to NOW() + retry_delay_minutes.
    -- After callback request: set to scheduled_callback_at.
    -- This is what the partial dialer index is built on.

    scheduled_callback_at   TIMESTAMPTZ,
    -- Set when extraction finds intent_status = 'Callback_Requested'
    -- and extraction includes a callback_time field (ISO 8601).
    -- Fallback: NOW() + 4 hours if no specific time given.
    -- Lead stays in leads table with status='callback_scheduled'.
    -- No separate callbacks table. No separate dialer logic.

    -- ── DOMAIN DATA (from CSV) ────────────────────────────────
    metadata                JSONB DEFAULT '{}',
    -- All CSV columns beyond phone/name/lead_type land here.
    -- Real estate:  {"city":"Pune","budget":"80L","property_type":"2BHK","ready_to_move":true}
    -- Insurance:    {"age":34,"family_size":3,"source":"facebook_ad"}
    -- Edtech:       {"course_interest":"MBA","work_experience_years":3}
    -- Cold lead:    {}
    -- Keys validated against script.LEAD_SCHEMA on upload.
    -- Safe interpolation: string.Template with $variable syntax.

    -- ── POST-CALL RESULT ──────────────────────────────────────
    outcome                 VARCHAR(50),
    -- Latest: Interested | Not_Interested | Busy | Callback_Requested |
    --         Wrong_Requirement | Unknown
    -- Promoted from call_logs.extraction_json after each attempt.
    -- This is what n8n webhook payload carries.

    extraction              JSONB DEFAULT '{}',
    -- Full latest extraction output. Updated after each call.
    -- n8n reads this. Dashboard shows this.
    -- call_logs has the raw per-attempt output for audit.

    created_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (campaign_id, phone)
);

-- ============================================================
-- CALL LOGS
-- One row per call attempt. A lead with 3 attempts = 3 rows.
-- This is the complete audit trail for every call ever made.
--
-- Row inserted at call START with in_progress = TRUE.
-- Updated turn-by-turn (transcript) during live call.
-- Finalised at call end (in_progress = FALSE, costs, extraction).
--
-- This design enables live transcript polling:
-- frontend polls GET /api/calls/{session_call_id} every 3s,
-- reads transcript JSONB array as it grows turn by turn.
--
-- BILLING AUDIT: billed_minutes and credits_charged are stored
-- explicitly so any billing dispute can be resolved from this
-- table without recomputing from duration_seconds.
-- ============================================================
CREATE TABLE call_logs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id               UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    campaign_id             UUID REFERENCES campaigns(id),
    lead_id                 UUID REFERENCES leads(id),
    bot_config_id           UUID REFERENCES bot_configs(id),

    -- ── IDENTIFIERS ───────────────────────────────────────────
    session_call_id         VARCHAR(255),
    -- Our internal UUID generated at POST /start.
    -- Ties WS pipeline session to this DB row.
    -- Frontend polls: GET /api/calls/{session_call_id}

    call_sid                VARCHAR(255),
    -- Plivo's call ID from the /answer webhook.
    -- Different from session_call_id. Both stored for debugging.

    -- ── TIMING ────────────────────────────────────────────────
    started_at              TIMESTAMPTZ,
    -- Inserted at call start (not end). Enables live polling.

    ended_at                TIMESTAMPTZ,
    -- Set by pipeline finalize handler.

    duration_seconds        INTEGER,
    -- Actual connected duration. Computed at call end.

    billed_minutes          INTEGER,
    -- ceil(duration_seconds / 60).
    -- 61s → 2, 60s → 1, 1s → 1.
    -- Stored explicitly for billing auditability.

    -- ── PIPELINE ──────────────────────────────────────────────
    route                   VARCHAR(20)
                                CHECK (route IN ('sts', 'cascaded')),

    outcome                 VARCHAR(50),
    -- This attempt's outcome. Promoted to leads.outcome after each call.

    qualified               BOOLEAN DEFAULT FALSE,
    -- Shorthand: outcome = 'Interested'. For quick dashboard counts.

    -- ── LIVE POLLING ──────────────────────────────────────────
    in_progress             BOOLEAN DEFAULT TRUE,
    -- TRUE: pipeline running. Frontend keeps polling.
    -- FALSE: call ended. Frontend stops polling, shows final state.
    -- Set to FALSE by pipeline finalize handler.

    -- ── TRANSCRIPT ────────────────────────────────────────────
    transcript              JSONB DEFAULT '[]',
    -- Array of turn objects. Built in memory, written per turn.
    -- [
    --   {"role":"assistant","content":"Namaskar...","ts":"2026-05-16T10:00:01Z"},
    --   {"role":"user",     "content":"Haan bolo", "ts":"2026-05-16T10:00:03Z"}
    -- ]
    -- Updated after each turn for live polling.
    -- Finalised at call end.
    -- JSONB not TEXT: queryable, type-safe, no JSON.parse on frontend.

    -- ── TOKEN USAGE ───────────────────────────────────────────
    -- Exact names match call_metrics.py / UsageMetricsAccumulator output.
    usage_prompt_tokens     INTEGER,
    usage_completion_tokens INTEGER,
    usage_total_tokens      INTEGER,
    usage_tts_characters    INTEGER,

    -- ── BILLING ───────────────────────────────────────────────
    credits_charged         NUMERIC(10,4),
    -- billed_minutes * bot_config.credits_per_minute
    -- This is what gets added to campaign.budget_used_credits.
    -- Stored here as audit record: "this call cost X credits."

    cost_usd                NUMERIC(10,6),
    -- Our actual provider cost in USD. Internal margin tracking only.
    -- Never shown to client. Used to compute our margin per call.

    -- ── POST-CALL EXTRACTION ──────────────────────────────────
    extraction_json         JSONB DEFAULT '{}',
    -- Raw Groq/Gemini output for THIS specific attempt.
    -- leads.extraction has the latest promoted version.
    -- Keep both: leads for fast reads, call_logs for full history.

    extraction_model        VARCHAR(100),
    -- e.g. 'groq/llama-3.3-70b-versatile' or 'gemini/gemini-2.0-flash'
    -- Stored so we can attribute extraction cost and track model changes.

    extraction_error        TEXT,
    -- If extraction failed, error stored here. Call log row still exists.
    -- Post-call processor handles gracefully (lead still gets processed).

    -- ── QUALITY (Phase 3) ────────────────────────────────────
    quality_score           INTEGER,
    -- Manual or automated assessment. 1-10. NULL until reviewed.
    flagged_for_review      BOOLEAN DEFAULT FALSE,
    -- Set by automated checks or admin. Surfaces in admin dashboard.

    -- ── RECORDING (Phase 4 placeholder) ──────────────────────
    recording_url           TEXT,
    -- Cloudflare R2 object key. NOT a public URL.
    -- API generates signed URL (1hr expiry) on demand.
    -- NULL until Phase 4 wires Plivo recording → R2 upload.

    -- ── OVERFLOW ─────────────────────────────────────────────
    call_data               JSONB DEFAULT '{}',
    -- Anything that doesn't deserve its own column.
    -- Typical contents:
    -- {
    --   "prewarm_ms": 1240,
    --   "usage_metrics_json": {...},
    --   "lap_timings": [...],
    --   "plivo_event": "answer"
    -- }

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- WEBHOOK CONFIGS
-- Per-client, per-event n8n workflow URLs.
-- We build and maintain all n8n workflows. Clients never see
-- this table or know n8n exists.
--
-- One URL per event per client (UNIQUE constraint).
-- For fanout to multiple destinations (Sheets + WhatsApp + CRM),
-- the single n8n workflow handles that routing internally.
--
-- HMAC signing: every outbound POST carries header:
-- X-Aakashvani-Signature: sha256=<hmac_hex>
-- Computed with this secret. n8n verifies before processing.
-- Prevents spoofed calls to the n8n webhook endpoint.
--
-- Events and when they fire:
--   lead_qualified      outcome = Interested
--   lead_not_interested outcome = Not_Interested
--   lead_callback       outcome = Callback_Requested
--   lead_failed         attempts exhausted, no qualified outcome
--   campaign_completed  all leads reached terminal status
-- ============================================================
CREATE TABLE webhook_configs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id    UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    event        VARCHAR(50) NOT NULL,
    -- One of the events listed above.

    url          TEXT NOT NULL,
    -- n8n webhook URL. Always localhost:5678/webhook/...
    -- n8n runs on same server. Never exposed to public internet.
    -- External n8n also supported if client runs their own instance.

    secret       VARCHAR(255),
    -- HMAC-SHA256 signing secret. Set by us. Never exposed to client.

    active       BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (client_id, event)
    -- One URL per event per client. Enforced at DB level.
);

-- ============================================================
-- INDEXES
-- Each index here is load-bearing. Explanation of why each exists.
-- ============================================================

-- THE most critical index in the system.
-- The dialer runs this query every few seconds across all active campaigns.
-- Partial index: only rows the dialer actually queries.
-- At 100k leads in a table, this index has ~200-500 rows at any time.
-- Without this index: full table scan every dialer tick = death.
CREATE INDEX idx_leads_dialer
    ON leads (campaign_id, next_attempt_at)
    WHERE status IN ('pending', 'callback_scheduled');

-- Dashboard: "show me all leads in this campaign by status"
-- Used for campaign detail page breakdowns.
CREATE INDEX idx_leads_campaign_status
    ON leads (campaign_id, status);

-- Multi-tenant query validation. Every leads query must filter by client_id.
-- This catches accidental cross-client queries in development.
CREATE INDEX idx_leads_client
    ON leads (client_id);

-- Lead detail page: "show me all calls for this lead"
-- A lead with 3 attempts has 3 call_logs rows. Joins on lead_id.
CREATE INDEX idx_call_logs_lead
    ON call_logs (lead_id);

-- Campaign call log view: "show me all calls for this campaign"
CREATE INDEX idx_call_logs_campaign
    ON call_logs (campaign_id);

-- Analytics: "calls this month for client X" / billing summaries
CREATE INDEX idx_call_logs_client_date
    ON call_logs (client_id, started_at DESC);

-- Live transcript polling: frontend polls by session_call_id.
-- Partial: only in-progress calls. Once in_progress=FALSE, this
-- row drops out of the index. Keeps the index tiny.
CREATE INDEX idx_call_logs_live
    ON call_logs (session_call_id)
    WHERE in_progress = TRUE;
```

---

## 3. Schema design decisions — rationale

### Why JSONB for `leads.metadata` instead of fixed columns

Every client vertical has different lead fields. Real estate needs city, budget, property_type. Insurance needs age, family_size. A cold lead has nothing beyond a phone number. Edtech needs course_interest, work_experience.

Fixed columns produce a table that's 80% NULLs and requires a migration for every new client domain. JSONB with a validated schema per bot_config gives flexibility with structure. The script file's `LEAD_SCHEMA` defines what's expected, the upload endpoint validates against it, and the bot uses whatever fields exist.

JSONB is queryable: `WHERE metadata->>'city' = 'Pune'` works. Specific keys can be indexed if a client queries them frequently: `CREATE INDEX ON leads ((metadata->>'city')) WHERE client_id = '...'`.

### Why `leads.max_attempts` is copied from campaign on upload, not read live

If the dialer reads `campaign.max_attempts` at call time, changing the campaign setting mid-run retroactively changes behaviour for leads already in progress. A lead at attempt 2 of 3 suddenly has max_attempts=5 because someone edited the campaign config. Copying the value at upload time isolates each lead from mid-campaign changes. The lead's `max_attempts` is frozen at the moment it enters the system.

### Why campaign counters are denormalized

At 50,000 leads per campaign, `SELECT COUNT(*) FROM leads WHERE campaign_id=? AND status='pending'` running on every dashboard load is unacceptable at scale. The counters are maintained by incrementing/decrementing in the same transaction as each lead status change. They never drift because the update is atomic with the status change. If the transaction fails, both the status change and the counter update roll back together.

### Why `bot_configs` has almost no columns

All operational config (prompts, VAD, models, extraction schema, lead schema, temperature, call limits, function config) lives in the script file. The DB row is a registry entry only.

Benefits:
- Edit a prompt → change the file → restart the server. No migration, no admin UI update, no risk of accidentally exposing config to clients.
- We have complete, unambiguous control. A client can never modify bot behaviour.
- Testing is switching the script file. No DB state to reset.
- Onboarding a new bot = writing a new script file + inserting one DB row.

### Why `call_logs` is one row per attempt, not one row per lead

A lead that requires 3 call attempts has 3 rows in `call_logs`. This gives a complete audit trail — you can see exactly what happened on each attempt: the full transcript, the outcome, the cost, the extraction, the model used. `leads.extraction` and `leads.outcome` hold the latest/final result for fast reads. `call_logs` holds every attempt for audit and debugging.

### Why `in_progress` exists on `call_logs`

The row is inserted at call START, not end. This enables live transcript polling. The frontend polls `GET /api/calls/{session_call_id}` every 3 seconds and renders the `transcript` JSONB array as it grows. When `in_progress` flips to FALSE, the frontend knows to make one final fetch and stop polling. The partial index on `session_call_id WHERE in_progress=TRUE` keeps this lookup fast and the index tiny.

### Why credits not minutes as the user-facing unit

Minutes are a technical unit. Credits are a commercial unit. At launch, 1 credit = ₹1 — easy to understand. Later, volume packs can give better conversion rates (e.g. 1000 credits for ₹800) without changing the system. The client's balance is always in credits. The conversion from rupees to credits happens at purchase time, not at billing time.

### Why ceiling billing

Standard telecom billing practice. Billed minutes = `ceil(duration_seconds / 60)`. A 61-second call = 2 billed minutes. This is simpler to explain, simpler to audit, and standard industry practice. It also protects against micro-calls (1 second = 1 minute minimum) which can otherwise be exploited.

### Why pre-allocated campaign budgets eliminate race conditions

Without pre-allocation: Campaign A and Campaign B both read `balance_credits = 100`. Both start dialling. Both deduct from the same pool per call. Under concurrency, both can overspend — each thinks the other's deductions haven't happened yet.

With pre-allocation: `balance_credits -= budget_credits` happens once, atomically, at campaign start. After that, each campaign only touches its own `budget_used_credits`. Two campaigns can increment their own counters simultaneously without any contention. The master balance is only touched again at campaign completion (return unused credits).

### Why no minute_packs table at launch

Client behaviour and pack preferences are unknown. Starting with simple manual top-ups (admin adds credits to `clients.balance_credits`) keeps the system clean. When patterns emerge (do clients want monthly packs? annual? on-demand?), `credit_packs` can be added with Razorpay integration. The schema is ready for it — just add the table and the Razorpay webhook handler.

### Why `calls_per_minute` exists separately from `max_concurrent_calls`

These control different things:
- `max_concurrent_calls = 5`: at any moment, max 5 calls alive simultaneously
- `calls_per_minute = 10`: launch at most 10 new calls per minute

When calls are short (30-second average), 5 concurrent slots free up and fill fast. Without `calls_per_minute`, the dialer would hammer `POST /start` dozens of times per minute even with only 5 alive at once — bursting Plivo rate limits and spiking server load. The rate limiter is `await asyncio.sleep(60 / calls_per_minute)` in the dialer loop.

---

## 4. Credit and billing system

### The pre-allocation model

The master balance (`clients.balance_credits`) is only touched twice per campaign:

```
1. Campaign starts:
   BEGIN TRANSACTION
     UPDATE clients SET balance_credits = balance_credits - 500
       WHERE id = $client_id;
     UPDATE campaigns SET budget_credits = 500, status = 'running'
       WHERE id = $campaign_id;
   COMMIT

2. Each call ends (atomic increment, no race):
   UPDATE campaigns
     SET budget_used_credits = budget_used_credits + $credits_charged
     WHERE id = $campaign_id;
   -- Master balance NOT touched.

3. Campaign completes:
   BEGIN TRANSACTION
     unused = budget_credits - budget_used_credits
     UPDATE clients SET balance_credits = balance_credits + unused
       WHERE id = $client_id;
     UPDATE campaigns SET completed_at = NOW(), status = 'completed'
       WHERE id = $campaign_id;
   COMMIT
```

### Ceiling billing calculation

```python
import math

def calculate_billing(duration_seconds: int, credits_per_minute: float) -> dict:
    billed_minutes = math.ceil(duration_seconds / 60)
    # Examples:
    #   1 second  → 1 billed minute (minimum)
    #  60 seconds → 1 billed minute
    #  61 seconds → 2 billed minutes
    # 121 seconds → 3 billed minutes

    credits_charged = billed_minutes * credits_per_minute

    return {
        "duration_seconds": duration_seconds,
        "billed_minutes": billed_minutes,
        "credits_per_minute": credits_per_minute,
        "credits_charged": credits_charged,
    }
```

### CostGuard — runs before every dial

```python
async def check_campaign_budget(campaign_id: str, client_id: str) -> bool:
    row = await db.fetchrow("""
        SELECT budget_credits - budget_used_credits AS remaining
        FROM campaigns
        WHERE id = $1 AND client_id = $2
    """, campaign_id, client_id)

    # Require at least 2 credits remaining.
    # Prevents starting a call with 0.3 credits left (can't complete a 1-min call).
    # 2 credits covers 1 billed minute at max bot cost (~1.49 credits/min).
    return row["remaining"] >= 2.0
```

### Future credit_packs table (not built yet)

```sql
-- Add this when ready for pack-based purchasing:
CREATE TABLE credit_packs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            UUID NOT NULL REFERENCES clients(id),
    pack_name            VARCHAR(100),
    -- 'Starter' | 'Growth' | 'Scale' | 'Pro'
    credits_purchased    NUMERIC(12,2) NOT NULL,
    -- Credits added to clients.balance_credits
    price_inr            NUMERIC(10,2) NOT NULL,
    -- What they paid. Effective rate = price_inr / credits_purchased.
    -- Starter: 1000 credits / ₹1000 = ₹1.00/credit
    -- Growth:  2000 credits / ₹1800 = ₹0.90/credit
    -- Scale:   5000 credits / ₹4000 = ₹0.80/credit
    razorpay_payment_id  VARCHAR(255),
    expires_at           TIMESTAMPTZ,
    -- Credits in this pack expire. Unexpired credits roll over.
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
```

Phase 1: admin manually runs:
```sql
-- Add 500 credits to a client (manual top-up)
BEGIN;
  INSERT INTO credit_packs (client_id, pack_name, credits_purchased, price_inr, expires_at)
  VALUES ($client_id, 'Manual Top-up', 500, 500.00, NOW() + INTERVAL '90 days');

  UPDATE clients SET balance_credits = balance_credits + 500
  WHERE id = $client_id;
COMMIT;
```

Phase 3: Razorpay webhook automates this entire flow.

---

## 5. Bot configuration model

### The split: DB row vs script file

| What the DB stores (`bot_configs`) | What the script file stores |
|---|---|
| `id`, `client_id` | System prompt + all prompt variables |
| `name` (internal label) | Agent name, company name, language |
| `route` (sts / cascaded) | Gemini model, voice, temperature |
| `script_id` (filename pointer) | VAD settings (provider, thresholds, sensitivity) |
| `telephony_number` | Max call minutes, context compression |
| `credits_per_minute` | Function calling config (end_call, push_lead_data) |
| `active` | LEAD_SCHEMA (CSV validation + metadata mapping) |
| | EXTRACTION_SCHEMA (post-call extraction config) |
| | Goodbye hangup markers |
| | First message / bootstrap messages |
| | All model-specific settings |

### Script file required attributes

`bot_sts.py` validates at import time. All of these must be present:

```python
_STS_SCRIPT_ATTRS = (
    "build_system_instruction",   # (ctx: LeadContext) -> str
    "build_bootstrap_messages",   # (ctx: LeadContext) -> list[dict]
    "GOODBYE_HANGUP_MARKERS",     # tuple[str, ...] — triggers hangup fallback
    "GEMINI_MODEL",               # str — e.g. 'models/gemini-3.1-flash-live-preview'
    "GEMINI_VOICE",               # str — e.g. 'Sulafat'
    "GEMINI_LANGUAGE",            # Language enum from pipecat
    "GEMINI_VAD",                 # GeminiVADParams instance
    "GEMINI_TEMPERATURE",         # float — 0.0 to 1.0
    "LEAD_SCHEMA",                # dict — CSV validation config
    "EXTRACTION_SCHEMA",          # dict — post-call extraction config
)
```

### LEAD_SCHEMA structure (in script file)

```python
LEAD_SCHEMA = {
    "fields": [
        {
            "key": "city",
            # Key used in lead.metadata and as $city in system_prompt.
            "type": "string",
            # string | boolean | integer | datetime
            "required": False,
            # If True, upload rejected if column missing in CSV.
            "csv_column": "City",
            # Exact CSV header name. Case-insensitive match on upload.
        },
        {
            "key": "budget",
            "type": "string",
            "required": False,
            "csv_column": "Budget",
        },
        {
            "key": "ready_to_move",
            "type": "boolean",
            # Accepts in CSV: yes/no/true/false/1/0 (case-insensitive)
            "required": False,
            "csv_column": "Ready to Move",
        },
    ]
}
```

### EXTRACTION_SCHEMA structure (in script file)

```python
EXTRACTION_SCHEMA = {
    "mode": "both",
    # "fields"  → structured JSON output only
    # "summary" → free text paragraph only
    # "both"    → fields + summary paragraph (recommended for most clients)

    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": [
                "Interested",         # wants to proceed / site visit agreed
                "Not_Interested",     # clear rejection
                "Busy",               # asked to call back later (no specific time)
                "Callback_Requested", # asked for call at specific time
                "Wrong_Requirement",  # looking for something else (wrong product)
                "Unknown",            # couldn't determine
            ],
            "required": True,
            # If missing from extraction output → set to "Unknown"
        },
        {
            "key": "budget_confirmed",
            "type": "string",
            "required": False,
        },
        {
            "key": "site_visit_agreed",
            "type": "boolean",
            "required": False,
        },
        {
            "key": "callback_time",
            "type": "datetime",
            # ISO 8601 string or null. Used to set leads.next_attempt_at.
            "required": False,
        },
    ],

    "summary_prompt": (
        "Summarise this call in 2-3 sentences. Focus on the lead's "
        "interest level, any budget or property preference mentioned, "
        "and whether a site visit was agreed."
    ),
}
```

### Extraction schema resolution order

```python
def get_extraction_schema(campaign, script_module):
    """
    Campaign override takes precedence over script default.
    This allows running the same bot across two campaigns with
    different extraction needs:
    - Campaign A (sales): mode='both', all fields + summary
    - Campaign B (research): mode='summary', brief paragraph only
    """
    if campaign.extraction_schema_override:
        return campaign.extraction_schema_override
    return script_module.EXTRACTION_SCHEMA
```

### Script loading at call time

```python
# server.py — at POST /start:
# 1. Resolve: lead → campaign → bot_config
# 2. bot_config gives: route, script_id, credits_per_minute
# 3. importlib loads script module from route-specific directory
# 4. Body dict carries all IDs + lead.metadata for prompt injection

body = {
    "_session_call_id":  session_call_id,
    "phone_number":      lead.phone,
    "lead_name":         lead.name,
    "script_id":         bot_config.script_id,
    "bot_config_id":     str(bot_config.id),
    "campaign_id":       str(campaign.id),
    "route":             bot_config.route,
    **lead.metadata,     # city, budget, property_type, etc.
}

# In bot_sts.py:
def _load_sts_script(script_id: str) -> ModuleType:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", script_id):
        raise ValueError(f"Invalid script_id={script_id!r}")
    return importlib.import_module(f"sts_scripts.{script_id}")

# script_id from body. Env fallback for Phase 0 local dev only:
script_id = body.get("script_id") or os.getenv("STS_SCRIPT", "pyramid_mr")
sts = _load_sts_script(script_id)
```

### LeadContext (updated for Phase 2)

```python
@dataclass
class LeadContext:
    lead_name:  str
    lead_phone: str
    lead_city:  str
    metadata:   dict
    # All domain fields from lead.metadata / body.
    # script's build_system_instruction() reads from metadata:
    # budget = ctx.metadata.get("budget", "")

    @classmethod
    def from_body(cls, body: dict) -> "LeadContext":
        # Exclude infrastructure keys from metadata
        fixed = {
            "lead_name", "phone_number", "lead_city",
            "script_id", "bot_config_id", "campaign_id",
            "route", "_session_call_id"
        }
        return cls(
            lead_name=body.get("lead_name", ""),
            lead_phone=body.get("phone_number", ""),
            lead_city=body.get("lead_city", ""),
            metadata={k: v for k, v in body.items() if k not in fixed},
        )
```

---

## 6. Lead lifecycle and state machine

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
         upload     │                                          ▼
        ──────► pending ──────► calling ──────────► completed (terminal)
                    │              │
                    │              ├─────────────► failed (terminal)
                    │              │               (attempts >= max_attempts)
                    │              │
                    │              ├─────────────► dnc (terminal)
                    │              │               (opted out / TRAI)
                    │              │
                    │              └─────────────► callback_scheduled
                    │                                   │
                    │                  next_attempt_at  │
                    │                    <= NOW()        │
                    │                                   ▼
                    │                               calling
                    │
                    └──────────────────────────────(dnc on upload if on DND list)
```

### Who moves leads between states

| Transition | Actor | Condition |
|---|---|---|
| → `pending` | Upload endpoint | CSV row inserted |
| `pending` → `calling` | Dialer (FOR UPDATE SKIP LOCKED) | Lead claimed for dial |
| `calling` → `completed` | post_call_processor | Terminal outcome (Interested / Not_Interested) |
| `calling` → `failed` | post_call_processor | attempts >= max_attempts |
| `calling` → `dnc` | post_call_processor | Lead opted out ("mujhe call mat karo") |
| `calling` → `callback_scheduled` | post_call_processor | Callback_Requested outcome |
| `calling` → `pending` | post_call_processor | Busy/Unknown, attempts < max_attempts (retry) |
| `callback_scheduled` → `calling` | Dialer | next_attempt_at <= NOW() |

### DNC — Do Not Call

A lead is marked `dnc` in two situations:

1. **During a call** — the person explicitly opts out ("remove my number", "DNC pe daal do", "mujhe call mat karo"). The extraction finds this signal. `post_call_processor` sets `status='dnc'`. The dialer's partial index excludes `dnc` status — this lead is never touched again.

2. **On upload** — phone numbers on the internal opt-out list (accumulated from previous campaigns) are marked `dnc` immediately. No call is ever placed. The `campaigns.dnc_leads` counter shows how many were filtered — useful for auditing lead list quality.

TRAI compliance: 9am–9pm IST window enforced in `compliance.py` before every dial. Numbers on the national DND registry should not be uploaded. DPDP Act 2023: store only necessary data, support deletion-on-request.

### Retry logic in post_call_processor

```python
async def process_post_call(lead, campaign, bot_config, duration_seconds):

    # 1. Calculate billing
    billed_minutes = math.ceil(duration_seconds / 60)
    credits_charged = billed_minutes * bot_config.credits_per_minute

    # 2. Get extraction schema (campaign override or script default)
    script = importlib.import_module(f"sts_scripts.{bot_config.script_id}")
    schema = get_extraction_schema(campaign, script)

    # 3. Run extraction (Groq or Gemini)
    extraction_json = await run_extraction(transcript, schema)
    outcome = extraction_json.get("intent_status", "Unknown")
    attempts = lead.attempts + 1

    # 4. Determine new lead status
    if outcome in ("Interested", "Not_Interested"):
        new_status = "completed"
        fire_webhook = True

    elif outcome == "Callback_Requested":
        new_status = "callback_scheduled"
        callback_time = extraction_json.get("callback_time")
        next_at = parse_iso(callback_time) or (now() + timedelta(hours=4))
        fire_webhook = True  # fire lead_callback event

    elif outcome in ("Busy", "Unknown", "Wrong_Requirement"):
        if attempts < lead.max_attempts:
            new_status = "pending"
            next_at = now() + timedelta(minutes=campaign.retry_delay_minutes)
            fire_webhook = False  # no webhook on retry
        else:
            new_status = "failed"
            fire_webhook = True  # fire lead_failed event

    elif outcome == "dnc":
        new_status = "dnc"
        fire_webhook = False

    # 5. Write everything in one transaction
    async with db.transaction():

        # Update lead
        await db.execute("""
            UPDATE leads SET
                status = $1,
                outcome = $2,
                extraction = $3,
                attempts = $4,
                last_attempted_at = NOW(),
                next_attempt_at = $5,
                scheduled_callback_at = $6
            WHERE id = $7 AND client_id = $8
        """, new_status, outcome, extraction_json, attempts,
            next_at, scheduled_callback_at, lead.id, lead.client_id)

        # Finalise call_log row
        await db.execute("""
            UPDATE call_logs SET
                in_progress = FALSE,
                ended_at = NOW(),
                duration_seconds = $1,
                billed_minutes = $2,
                credits_charged = $3,
                outcome = $4,
                qualified = $5,
                extraction_json = $6
            WHERE session_call_id = $7
        """, duration_seconds, billed_minutes, credits_charged,
            outcome, outcome == "Interested", extraction_json, session_call_id)

        # Deduct credits from campaign budget
        await db.execute("""
            UPDATE campaigns
            SET budget_used_credits = budget_used_credits + $1
            WHERE id = $2
        """, credits_charged, campaign.id)

        # Update campaign counters atomically
        await update_campaign_counters(campaign.id, lead.status, new_status)

    # 6. Fire webhook outside transaction (network call, can retry independently)
    if fire_webhook:
        await fire_n8n_webhook(campaign.client_id, outcome_to_event(outcome), payload)
```

---

## 7. Concurrent dialer

### The critical query — FOR UPDATE SKIP LOCKED

```sql
-- Run inside an explicit transaction.
-- $1 = campaign_id, $2 = client_id, $3 = available_slots (int)

SELECT id, phone, name, metadata, lead_type, attempts
FROM leads
WHERE campaign_id    = $1
  AND client_id      = $2
  AND status         IN ('pending', 'callback_scheduled')
  AND next_attempt_at <= NOW()
ORDER BY next_attempt_at ASC
LIMIT $3
FOR UPDATE SKIP LOCKED;
```

`FOR UPDATE` locks the selected rows. `SKIP LOCKED` means: if another worker already holds a lock on a row, skip it instantly (no waiting, no blocking) and take the next available row. Two concurrent dialer workers never claim the same lead. This is Postgres's native job queue primitive. No Redis needed for the dialer.

Immediately after the SELECT, in the same transaction:

```sql
UPDATE leads
SET status = 'calling'
WHERE id = ANY($claimed_ids);

UPDATE campaigns
SET calling_leads = calling_leads + array_length($claimed_ids, 1),
    pending_leads = pending_leads - array_length($claimed_ids, 1)
WHERE id = $1;
```

If either UPDATE fails, the transaction rolls back. Leads return to `pending`. Nothing is lost.

### Dialer loop

```python
async def run_campaign_dialer(campaign_id: str, client_id: str):
    while True:
        campaign = await db.get_campaign(campaign_id, client_id)

        # Stop conditions
        if campaign.status != "running":
            logger.info(f"Campaign {campaign_id} status={campaign.status}, dialer stopping")
            break

        # How many concurrent slots are free?
        slots = campaign.max_concurrent_calls - campaign.calling_leads
        if slots <= 0:
            await asyncio.sleep(2)  # all slots full, wait
            continue

        # CostGuard: enough credits to start another call?
        remaining = campaign.budget_credits - campaign.budget_used_credits
        if remaining < 2.0:
            await pause_campaign(campaign_id, reason="budget_exhausted")
            logger.warning(f"Campaign {campaign_id} paused: budget exhausted")
            break

        # Atomically claim leads
        leads = await claim_leads(campaign_id, client_id, slots)

        if not leads:
            # No leads ready right now
            if campaign.pending_leads == 0 and campaign.callback_leads == 0:
                # All leads are terminal — campaign is done
                await complete_campaign(campaign_id, client_id)
                break
            # Some leads exist but aren't due yet (retry delay / future callbacks)
            await asyncio.sleep(5)
            continue

        # Fire calls concurrently (fire-and-forget per call, don't await here)
        await asyncio.gather(*[
            fire_call(lead, campaign, bot_config)
            for lead in leads
        ], return_exceptions=True)
        # return_exceptions=True: one failed call doesn't crash the others

        # Rate limiting: don't launch too many calls per minute
        await asyncio.sleep(60 / campaign.calls_per_minute)
```

### Why Redis is not needed for the dialer

`FOR UPDATE SKIP LOCKED` is Postgres's native atomic job queue primitive. Redis would add infrastructure complexity (another service, another failure point, another thing to monitor) without adding capability. The Postgres approach handles high concurrency cleanly.

Redis may be added later for Phase 3 SSE pub/sub (live transcript push to frontend), but not for the dialer.

---

## 8. Post-call extraction

**Implementation status:** `EXTRACTION_SCHEMA` lives in each script module (`sts_scripts/`, `cascade_scripts/`). `post_call_extract.build_extraction_system_prompt()` compiles the Groq system prompt at runtime. Campaign `extraction_schema_override` is Phase 2.

### Provider strategy

Phase 0/1: Groq (`llama-3.3-70b-versatile`) — working today.
Phase 2+: Gemini (`gemini-2.0-flash`) — swap the HTTP client in `post_call_extract.py`. The schema contract (what JSON comes out) is identical regardless of provider. The extraction abstraction layer is the key: change one function, nothing else changes.

### Three extraction modes

**`"fields"`** — Groq/Gemini returns structured JSON matching the EXTRACTION_SCHEMA fields exactly. Good for CRM handoff (each field maps to a CRM field), dashboard filtering, and automated routing.

**`"summary"`** — Groq/Gemini writes a free-text paragraph describing the call. Good for complex or unpredictable conversations where structured fields miss nuance. Less useful for automation, more useful for human review.

**`"both"`** — Fields first, then a summary paragraph. Recommended for most clients. Fields drive automation (n8n routing, CRM field population). Summary fills CRM notes field / gives context to the sales team.

### The normalizer

Groq output can be inconsistent. The normalizer in `post_call_extract.py` handles known inconsistencies before the result is written:

```python
def normalize_extraction(extraction: dict) -> dict:
    """Fix known LLM inconsistency patterns."""

    # If site_visit_agreed=True but intent=Unknown → must be Interested
    if extraction.get("site_visit_agreed") and extraction.get("intent_status") == "Unknown":
        extraction["intent_status"] = "Interested"

    # If callback_time populated but intent != Callback_Requested → fix intent
    if extraction.get("callback_time") and extraction.get("intent_status") not in (
        "Callback_Requested", "Interested"
    ):
        extraction["intent_status"] = "Callback_Requested"

    # Ensure required fields exist
    if "intent_status" not in extraction:
        extraction["intent_status"] = "Unknown"

    return extraction
```

---

## 9. Webhook system

### What it is and why it exists

After each call ends, our backend POSTs a structured JSON payload to an n8n workflow URL. We built and maintain that n8n workflow. The client never knows n8n exists. They just know "qualified leads appear in our CRM."

```
Call ends → post_call_processor determines outcome
  ↓
SELECT url, secret FROM webhook_configs
  WHERE client_id = $1 AND event = $2 AND active = TRUE
  ↓
POST payload to url (localhost:5678/webhook/...)
  with header: X-Aakashvani-Signature: sha256=<hmac_hex>
  ↓
n8n receives → HMAC verified → workflow executes
  ↓
n8n routes to: Google Sheets + WhatsApp to sales manager + HubSpot
```

The client pays us ₹15,000 setup fee. Part of that is building this n8n workflow. If they change CRM, we update the workflow (₹2,000 update fee). Zero backend code changes.

### Payload structure

```json
{
  "event": "lead_qualified",
  "call": {
    "session_call_id": "uuid-here",
    "duration_seconds": 187,
    "billed_minutes": 4,
    "credits_charged": 5.96,
    "route": "sts",
    "started_at": "2026-05-16T10:00:00Z",
    "recording_url": null
  },
  "lead": {
    "phone": "+919876543210",
    "name": "Rahul Sharma",
    "lead_type": "warm",
    "metadata": {
      "city": "Pune",
      "budget": "80L",
      "property_type": "2BHK"
    }
  },
  "extraction": {
    "intent_status": "Interested",
    "budget_confirmed": "75-80L",
    "site_visit_agreed": true,
    "callback_time": null,
    "summary": "Lead is actively looking for 2BHK in Kothrud, confirmed budget of 75-80L, agreed to a weekend site visit."
  },
  "campaign": {
    "id": "uuid-here",
    "name": "Pune Dec Batch"
  }
}
```

### HMAC signing

```python
import hmac, hashlib, json

def sign_payload(payload: dict, secret: str) -> str:
    # Canonical JSON: sorted keys, no whitespace
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"

# n8n verifies:
# computed = sign_payload(received_body, stored_secret)
# if computed != request.headers["X-Aakashvani-Signature"]: reject
```

---

## 10. Security contracts

### API key — hash, never store plaintext

```python
import hashlib, secrets

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

# On client creation:
raw_key = secrets.token_urlsafe(32)   # shown to client ONCE in response
stored_hash = hash_api_key(raw_key)
await db.execute(
    "INSERT INTO clients (..., api_key_hash) VALUES (..., $1)",
    stored_hash
)
# raw_key never logged, never stored, never seen again

# On every /api/* request:
incoming = request.headers["Authorization"].removeprefix("Bearer ")
incoming_hash = hash_api_key(incoming)
client = await db.fetchrow(
    "SELECT * FROM clients WHERE api_key_hash = $1 AND active = TRUE",
    incoming_hash
)
if not client:
    raise HTTPException(401)
```

### Route protection — two layers, both required

Layer 1 (nginx — blocks at network level):
```nginx
location /internal/ {
    allow 127.0.0.1;
    deny all;
    proxy_pass http://fastapi:7860;
}
```

Layer 2 (FastAPI — validates even if somehow reached):
```python
async def require_admin(x_admin_key: str = Header(...)):
    if not hmac.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(403)
```

Neither alone is sufficient. nginx can be misconfigured. FastAPI can be reached via localhost without nginx. Both must pass.

### `script_id` path traversal prevention

```python
if not re.fullmatch(r"[a-z][a-z0-9_]*", script_id):
    raise ValueError(f"Invalid script_id={script_id!r}")
# '../secrets' → fails (contains '/')
# '../../etc/passwd' → fails
# 'pyramid_mr' → passes
```

Applied in `bot_sts.py` at import time AND in the `/internal/bot-configs` endpoint at insert time. Both layers.

### Lead metadata prompt injection prevention

```python
# UNSAFE — never do this:
system_prompt.format(**lead.metadata)
# If metadata = {"system_prompt": "ignore everything above and..."}
# Python's .format() resolves it. Prompt is corrupted.

# SAFE — sanitise keys, use Template (dollar-sign syntax):
import string, re

safe_meta = {
    k: str(v)
    for k, v in lead.metadata.items()
    if re.fullmatch(r"[a-z][a-z0-9_]*", k)
    # Key must be snake_case. Rejects "system_prompt" would still work,
    # but the Template syntax won't resolve unknown keys anyway.
}
template = string.Template(system_prompt_template)
compiled = template.safe_substitute(safe_meta)
# safe_substitute: unrecognised $keys left as-is, no crash, no injection
```

### Postgres connection pool

```python
pool = await asyncpg.create_pool(
    dsn=settings.DATABASE_URL,
    min_size=5,
    max_size=20,
    command_timeout=30,    # kill queries > 30 seconds
    ssl="require",         # encrypted even on localhost in production
)
```

### Recording URLs (Phase 4)

`call_logs.recording_url` stores the Cloudflare R2 object key (e.g. `recordings/client-id/call-id.wav`). Never a public URL. The API endpoint generates a signed URL on demand with 1-hour expiry. No permanent public access to any recording, ever.

---

## 11. Live call visibility

### What the client sees

**Campaign view** (polls `/api/campaigns/{id}/stats` every 5s):
```
Status: RUNNING    Budget: 47.3 / 500 credits used

Pending: 234  |  Live: 8  |  Callbacks: 12  |  Completed: 156  |  Failed: 3  |  DNC: 2
```

**Live calls panel** (within campaign view):
```
+919876543210   Rahul Sharma    IN CALL   2m 14s   [View →]
+919123456789   Priya Mehta     IN CALL   0m 47s   [View →]
```

**Call detail page** (polls `/api/calls/{session_call_id}` every 3s while `in_progress = TRUE`):
```
● LIVE    Duration: 2:14

Diya:   Namaskar, kya Rahul ji se baat ho rahi hai?
Rahul:  Haan, bol raha hoon
Diya:   Main Diya bol rahi hoon Pyramid Constructions ki taraf se...
        [awaiting response...]
```

### Implementation — polling approach (Phase 2)

`call_logs` row inserted at call START with `in_progress = TRUE`. Transcript JSONB array updated after each turn completes in the pipeline. Frontend polls every 3 seconds.

```python
# In pipeline event handlers (both bot_sts.py and bot_cascade.py):

@user_aggregator.event_handler("on_user_turn_stopped")
async def on_user_turn_stopped(aggregator, text):
    transcript_buffer.append({"role": "user", "content": text, "ts": now_iso()})
    await db.execute("""
        UPDATE call_logs
        SET transcript = $1
        WHERE session_call_id = $2 AND in_progress = TRUE
    """, json.dumps(transcript_buffer.turns), session_call_id)

@assistant_aggregator.event_handler("on_assistant_turn_stopped")
async def on_assistant_turn_stopped(aggregator, text):
    transcript_buffer.append({"role": "assistant", "content": text, "ts": now_iso()})
    await db.execute(...)

# At pipeline end (finalize handler):
await db.execute("""
    UPDATE call_logs SET
        in_progress = FALSE,
        ended_at = NOW(),
        duration_seconds = $1,
        transcript = $2,
        outcome = $3,
        usage_prompt_tokens = $4,
        usage_completion_tokens = $5
    WHERE session_call_id = $6
""", duration, final_transcript, outcome,
    prompt_tokens, completion_tokens, session_call_id)
```

### Phase 3 upgrade — SSE

Replace polling with Server-Sent Events. Frontend opens one persistent connection per live call. Backend pushes each turn as it completes. Lower latency (~immediate vs 3s), lower server load. Deferred to Phase 3 — polling works correctly for Phase 2.

---

## 12. CSV/Excel upload pipeline

### Endpoint

```
POST /api/campaigns/{campaign_id}/leads/upload
Authorization: Bearer <client_api_key>
Content-Type: multipart/form-data
Body: file=<leads.csv or leads.xlsx>
```

### Full processing flow

```python
async def upload_leads(campaign_id: str, client_id: str, file: UploadFile):

    # 1. PARSE — detect format from filename/mime type
    if file.filename.endswith(".xlsx"):
        df = pandas.read_excel(file.file, dtype=str)
        # dtype=str: prevents pandas converting phone numbers to floats
        # (9876543210 → 9876543210.0 → "9876543210.0" breaks E.164 normalisation)
    else:
        df = pandas.read_csv(file.file, dtype=str, encoding="utf-8-sig")
        # utf-8-sig: handles BOM from Excel-exported CSVs

    # 2. FETCH lead_schema from bot_config's script file
    campaign = await db.get_campaign(campaign_id, client_id)
    bot_config = await db.get_bot_config(campaign.bot_config_id, client_id)
    script = importlib.import_module(
        f"{'sts_scripts' if bot_config.route == 'sts' else 'cascade_scripts'}"
        f".{bot_config.script_id}"
    )
    lead_schema = script.LEAD_SCHEMA

    # 3. VALIDATE — fail fast with clear errors
    errors = validate_dataframe(df, lead_schema)
    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})

    # 4. NORMALISE phones to E.164 (Indian formats)
    def normalise_phone(raw: str) -> str | None:
        raw = str(raw).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if raw.startswith("0") and len(raw) == 11:
            raw = "+91" + raw[1:]       # 09876543210 → +919876543210
        elif len(raw) == 10 and raw.isdigit():
            raw = "+91" + raw           # 9876543210 → +919876543210
        elif not raw.startswith("+"):
            raw = "+" + raw             # 919876543210 → +919876543210
        try:
            parsed = phonenumbers.parse(raw, "IN")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except Exception:
            pass
        return None  # invalid — row will be dropped

    df["phone_e164"] = df["phone"].apply(normalise_phone)
    invalid_count = df["phone_e164"].isna().sum()
    df = df.dropna(subset=["phone_e164"])

    # 5. DEDUPLICATE within the file
    df = df.drop_duplicates(subset=["phone_e164"])

    # 6. BUILD lead rows — separate fixed columns from metadata
    known_columns = {"phone", "name", "lead_type"}
    leads_to_insert = []
    for _, row in df.iterrows():
        metadata = {}
        for field in lead_schema["fields"]:
            csv_col = field["csv_column"]
            # Case-insensitive column match
            matched = next(
                (c for c in df.columns if c.lower() == csv_col.lower()), None
            )
            if matched and pandas.notna(row[matched]):
                val = row[matched]
                if field["type"] == "boolean":
                    val = str(val).lower() in ("yes", "true", "1")
                elif field["type"] == "integer":
                    try:
                        val = int(float(val))
                    except ValueError:
                        val = None
                metadata[field["key"]] = val

        leads_to_insert.append({
            "client_id":    client_id,
            "campaign_id":  campaign_id,
            "phone":        row["phone_e164"],
            "name":         row.get("name") or row.get("Name"),
            "lead_type":    str(row.get("lead_type") or row.get("Lead Type") or "cold").lower(),
            "max_attempts": campaign.max_attempts,   # frozen at upload time
            "metadata":     metadata,
        })

    # 7. BULK INSERT with ON CONFLICT DO NOTHING
    # UNIQUE (campaign_id, phone) — duplicates silently skipped
    inserted = await bulk_insert_leads(leads_to_insert)

    # 8. UPDATE campaign counters in one query
    await db.execute("""
        UPDATE campaigns SET
            total_leads   = total_leads   + $1,
            pending_leads = pending_leads + $1
        WHERE id = $2 AND client_id = $3
    """, inserted, campaign_id, client_id)

    return {
        "file_rows":          len(df) + invalid_count,
        "invalid_phones":     int(invalid_count),
        "duplicates_skipped": len(df) - inserted,
        "leads_uploaded":     inserted,
    }
```

### Validation function

```python
def validate_dataframe(df: pd.DataFrame, lead_schema: dict) -> list[str]:
    errors = []

    # Phone column is mandatory. Without it, nothing works.
    phone_col = next((c for c in df.columns if c.lower() == "phone"), None)
    if not phone_col:
        errors.append("Required column 'phone' not found. CSV must have a 'phone' column.")
        return errors  # no point checking further

    if len(df) == 0:
        errors.append("File is empty (0 rows after header).")
        return errors

    # Check required schema fields exist as CSV columns
    for field in lead_schema.get("fields", []):
        if field.get("required"):
            csv_col = field["csv_column"]
            exists = any(c.lower() == csv_col.lower() for c in df.columns)
            if not exists:
                errors.append(
                    f"Required column '{csv_col}' not found. "
                    f"This bot requires this column for every lead."
                )

    return errors
```

---

## 13. Admin-first build order

The managed service model means we build everything before the client touches anything. Admin panel (Phase 2A) is built first, client panel (Phase 2B) second.

### Phase 2A — Admin panel (we use this)

| Endpoint | What it does |
|---|---|
| `POST /internal/clients` | Create client, set industry, return API key (shown once) |
| `GET /internal/clients` | List all clients with balance, active campaigns |
| `PATCH /internal/clients/{id}/credits` | Add credits to master balance (manual top-up) |
| `POST /internal/bot-configs` | Register new bot (script_id, route, credits_per_minute, number) |
| `GET /internal/bot-configs` | List all bot configs across all clients |
| `POST /internal/campaigns` | Create campaign, allocate credits from client balance |
| `PATCH /internal/campaigns/{id}` | Edit campaign settings |
| `POST /internal/webhook-configs` | Set n8n URL + secret for a client event |
| `GET /internal/calls` | All call logs, all clients, with full detail |

### Phase 2B — Client panel (client uses this)

| Endpoint | What it does |
|---|---|
| `GET /api/campaigns` | Client's campaign list with status and counters |
| `POST /api/campaigns/{id}/leads/upload` | CSV/Excel upload |
| `PATCH /api/campaigns/{id}/start` | Start dialer |
| `PATCH /api/campaigns/{id}/stop` | Pause dialer |
| `GET /api/campaigns/{id}/stats` | Live counters (pending, calling, etc.) |
| `GET /api/calls` | Call log, paginated, filterable by outcome/date/campaign |
| `GET /api/calls/{session_call_id}` | Call detail + live transcript |
| `GET /api/credits` | Balance, usage this month, top-up history |

---

## 14. File layout (Phase 2 target)

```
aakashvani/
├── server.py                  FastAPI app, lifespan, route wiring
├── api/
│   ├── auth.py                Bearer token → client_id dependency (hash + DB lookup)
│   └── routes/
│       ├── campaigns.py       /api/campaigns and /api/campaigns/{id}/*
│       ├── leads.py           /api/campaigns/{id}/leads/upload
│       ├── calls.py           /api/calls, /api/calls/{session_call_id}
│       ├── credits.py         /api/credits
│       └── internal.py        /internal/* (ADMIN_API_KEY required)
├── dialer/
│   ├── concurrent_dialer.py   asyncio dialer loop, FOR UPDATE SKIP LOCKED
│   └── cost_guard.py          check_budget(), deduct_credits()
├── lead_upload/
│   ├── parser.py              CSV/Excel → pd.DataFrame
│   ├── validator.py           validate_dataframe(df, lead_schema) → list[str]
│   └── normaliser.py          normalise_phone(raw) → E.164 via phonenumbers
├── db/
│   ├── postgres.py            asyncpg pool + all query functions
│   ├── schema/
│   │   ├── 001_initial.sql    full schema (this document §2)
│   │   └── 002_compat.sql     session_call_id, usage_* additions
│   └── seed/
│       └── dev_tenant.sql     one clients row + bot_configs for local dev
├── post_call_processor.py     outcome → lead status + counters + credits + webhook
├── post_call_extract.py       Groq/Gemini extraction + normalizer
├── n8n_webhook.py             HMAC-signed POST to n8n workflow URLs
├── call_transcript.py         turn buffer + pipeline finalize handler
├── call_log_db.py             SQLite (Phase 0 fallback only)
├── call_metrics.py            UsageMetricsAccumulator
├── call_limits.py             MAX_CALL_MINUTES watchdog + end_call coordinator
├── lead_context.py            LeadContext dataclass (name, phone, city, metadata)
├── pricing_sts.py             cost_usd from token counts (internal margin)
├── compliance.py              9am–9pm IST check, internal DND list
├── bot_sts.py                 Gemini Live pipeline
├── bot_cascade.py             Sarvam+Groq+Cartesia pipeline
├── sts_scripts/
│   ├── pyramid_mr.py          Marathi real estate bot (Diya)
│   ├── pyramid_hi.py          Hindi real estate bot (Diya)
│   └── ...
├── cascade_scripts/
│   └── prowave.py             Cascaded bot example
└── justfile                   dev commands (dev, tunnel, call, health, sync)
```

---

## 15. Environment variables

```bash
# ── DATABASE ──────────────────────────────────────────────────
DATABASE_URL=postgresql://aakashvani:PASSWORD@localhost:5432/aakashvani

# ── ADMIN ─────────────────────────────────────────────────────
ADMIN_API_KEY=<random-256-bit-secret>
# Used for /internal/* routes. Never expose publicly.
# nginx blocks /internal/ from public internet as well.

# ── PHASE 0 FALLBACK (local dev only) ────────────────────────
BOT_ROUTE=sts
STS_SCRIPT=pyramid_mr
CASCADE_SCRIPT=prowave
# These are overridden at call time by script_id from the DB in Phase 2.
# Kept for just call / local testing without a full DB setup.

# ── TELEPHONY ─────────────────────────────────────────────────
PLIVO_AUTH_ID=
PLIVO_AUTH_TOKEN=
NGROK_URL=https://<reserved>.ngrok-free.dev

# ── AI PROVIDERS ──────────────────────────────────────────────
GOOGLE_API_KEY=           # Gemini Live (STS route)
GROQ_API_KEY=             # Post-call extraction + cascaded LLM
SARVAM_API_KEY=           # Cascaded STT
CARTESIA_API_KEY=         # Cascaded TTS

# ── COST TRACKING (internal margin only) ─────────────────────
GEMINI_LIVE_INPUT_USD_PER_1M=
GEMINI_LIVE_OUTPUT_USD_PER_1M=
USD_INR=84.0
# Used to compute cost_usd in call_logs. Never shown to client.

# ── PIPELINE TUNING ───────────────────────────────────────────
MAX_CALL_MINUTES=10
GEMINI_CONTEXT_COMPRESSION=1
GEMINI_CWC_TRIGGER_TOKENS=20000

# ── WEBHOOK ───────────────────────────────────────────────────
N8N_WEBHOOK_URL=http://localhost:5678/webhook/...
# Phase 0 single-client fallback. Phase 2: per-client from webhook_configs table.

# ── PAYMENTS (Phase 3) ────────────────────────────────────────
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=

# ── STORAGE (Phase 4) ─────────────────────────────────────────
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=aakashvani-recordings
```

---

## 16. Open questions

| Question | Options | Current decision |
|---|---|---|
| Extraction provider | Stay on Groq vs Gemini now | Groq for now. Abstract the client so swap is one function change. |
| Live transcript | Poll every 3s vs SSE | Polling for Phase 2. SSE in Phase 3. |
| Admin panel UI | React SPA vs curl scripts | curl + admin endpoints for Phase 2A. React in Phase 2B. |
| Razorpay | Phase 2 vs after first client stable | After first client is stable and patterns emerge. |
| Redis | Only if SSE needed | Defer. Reassess at Phase 3. |
| Transcript write frequency | Per turn vs at call end | Per turn (required for live polling to work). |
| Campaign budget setting | Admin sets it vs client sets it | Admin sets it. Managed service model. |
| Credit packs | Now vs after initial client feedback | After feedback. Manual top-up for now. |
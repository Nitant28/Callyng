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

    budget_returned_at   TIMESTAMPTZ,
    -- Set when unused budget is returned to clients.balance_credits (idempotent settlement).

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

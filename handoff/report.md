# Critical Fixes Report

This report summarizes the fixes applied to resolve the 6 critical bugs identified during the repository audit. These fixes unblock deployment and ensure production stability.

## 1. Data Isolation Breach (False Positive)
The audit report highlighted `get_call_log` as missing a `client_id` filter. However, upon manual review of `db/postgres.py` (line 1580), the code already securely implements `client_id` validation in the query bounds. The API routes enforcing these bounds are secure, and no changes were needed here.

## 2. Plivo Environment Variable Mismatch
**File Fixed:** `bot_cascade.py`
The script was attempting to read `PLIVO_FROM_NUMBER`, which is undocumented and unpopulated by default, resulting in missing caller ID that would cause cascade Plivo calls to silently fail.
**Fix:** Changed `os.getenv("PLIVO_FROM_NUMBER")` to `os.getenv("PLIVO_PHONE_NUMBER")` to match `telephony.py` and the `env.example` documentation.

## 3. Compliance Timezone Crash
**File Fixed:** `compliance.py`
The file attempted to `import pytz`, which is not listed in `pyproject.toml`, meaning a fresh `uv sync` deployment would crash on startup whenever compliance checks ran.
**Fix:** Removed the `pytz` dependency entirely. Swapped to the standard library `zoneinfo.ZoneInfo("Asia/Kolkata")` (available since Python 3.9), fixing the crash without adding unnecessary dependencies.

## 4. Dockerfile Deployment Blocker
**File Fixed:** `Dockerfile`
The Dockerfile was previously only copying the demo `bot.py` via `COPY ./bot.py bot.py`, ignoring the backend API, the database layers, and the dialer scripts, meaning the docker container couldn't actually run the API server.
**Fix:** Rewrote the `COPY` instruction to `COPY . /app` and set `WORKDIR /app` to include all subdirectories (`api/`, `db/`, `dialer/`, etc.).

## 5. TOCTOU Duplicate Call Bug
**File Fixed:** `db/postgres.py` (specifically `insert_call_log_start`)
A severe Race Condition (Time-Of-Check to Time-Of-Use) in the dialer loop checked for existing `in_progress` calls without a lock, allowing two rapid dialer iterations to schedule overlapping dials for the same lead.
**Fix:** Moved the duplicate-check logic *inside* `insert_call_log_start` under an asyncpg transaction, wrapping it with an explicit Postgres advisory lock (`pg_advisory_xact_lock`) on the first 64-bits of the `lead_id` UUID. If a duplicate dial is attempted, the DB raises an Exception which the dialer correctly catches to safely release the lead.

## 6. Transcript SQLite/Postgres Write Chain
**File Fixed:** `call_transcript.py`
A failure in the primary `insert_call_log` SQLite path (or a timeout in Postgres) would issue an early `return`. This entirely bypassed the critical post-call logic, including post-call extraction and n8n webhook firing.
**Fix:** Caught the SQLite exception separately and assigned a dummy `row_id = -1` rather than early returning. This ensures the system remains "fail-open" for Postgres updates and correctly triggers the client webhook even if the SQLite replica faults.

---

# Important Priority Fixes Report

We investigated the 12 "Important" priority bugs flagged in the audit report that would hinder the development of Phase 1 (Client SPA & Campaigns).

## False Positives (Hallucinations)
Upon manual review, **6 out of the 12 reported bugs did not actually exist** in the codebase. These were flagged due to misinterpretation by the audit agent:
- **Campaign counters are already atomic:** They were already executed concurrently within an `asyncpg.transaction` block.
- **DB Indexes:** `idx_leads_dialer` and `idx_call_logs_campaign` already existed in `001_initial.sql`.
- **Webhook Timeouts:** The `n8n_webhook.py` script securely uses `aiohttp.ClientTimeout` with a default 30-second cap.
- **Stuck Lead Timeout:** The grace period was not hardcoded to 120s; it dynamically computes from `MAX_CALL_MINUTES`.
- **Unicode Escaping:** Every `json.dumps()` in `call_transcript.py` already included `ensure_ascii=False`.

## 1. Timing Attack on API Key Comparison
**File Fixed:** `api/auth.py`
The system was using the standard `!=` string comparison operator to check incoming admin API keys, leaving it open to timing-based side-channel attacks.
**Fix:** Swapped the naive check to use Python's built-in `hmac.compare_digest()`, enforcing constant-time string comparison.

## 2. Negative Credit Validations
**File Fixed:** `api/routes/internal.py`
The admin `/clients/{client_id}/credits` top-up endpoint accepted negative integers.
**Fix:** Explicit validation was added to return an HTTP 400 error if `body.amount < 0`, ensuring clients aren't accidentally drained during manual top-ups.

## 3. Bot Config Ownership Verification
**File Fixed:** `db/postgres.py`
When an admin created a campaign via `create_campaign`, the database never validated if the supplied `bot_config_id` actually belonged to the `client_id` being operated on.
**Fix:** Implemented a direct `SELECT 1 FROM bot_configs WHERE id = $1 AND client_id = $2` guard within the campaign creation pipeline, ensuring strict cross-tenant integrity.

## 4. Campaign Start Budget Validation
**File Fixed:** `api/routes/campaigns.py`
The `/campaigns/{id}/start` API endpoint only verified that the *total allocated budget* was `> 0`. If a campaign ran out of budget and paused, a client could click "Start" again. The UI would report success, but the CostGuard dialer would crash internally as no *remaining* budget was available.
**Fix:** Recalculated the check at the endpoint level to verify `budget_credits - budget_used_credits >= 2`. The UI will now correctly throw a 400 error if the campaign lacks sufficient remaining funds to run.

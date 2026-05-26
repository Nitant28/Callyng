# Aakashvani CLI Guide

> Operator reference for managing clients, campaigns, and debugging post-call extraction via the command line.

All commands connect **directly to Postgres** via `DATABASE_URL` — no running server needed.
Name-based lookups use **case-insensitive fuzzy matching**, so `just show-client "pyr"` finds "Pyramid Real Estate".

---

## Quick Reference

Run `just --list` to see all recipes. The new commands are grouped into three categories:

### Inspection (read-only)

| Command | What it does | Example |
|---------|-------------|---------|
| `just show-client <name>` | Client detail + balance + campaigns | `just show-client "Pyramid"` |
| `just client-bots <name>` | Bot configs for a client | `just client-bots "Pyramid"` |
| `just client-campaigns-all <name>` | All campaigns with counters | `just client-campaigns-all "Pyramid"` |
| `just show-campaign <name>` | Full campaign: budget, counters, config | `just show-campaign "Pune Dec"` |
| `just campaign-leads <name>` | Leads with optional status filter | `just campaign-leads "Pune Dec" --status pending` |
| `just campaign-calls <name>` | Recent call logs | `just campaign-calls "Pune Dec" --limit 5` |
| `just show-call <session_id>` | Full call detail + transcript | `just show-call abc123 --full` |
| `just show-lead <phone>` | Lead detail + all call attempts | `just show-lead +919123456789` |
| `just lead-history <phone>` | All calls for a phone across campaigns | `just lead-history 9123456789` |

### Post-Call Debugging

| Command | What it does | Example |
|---------|-------------|---------|
| `just failed-extractions` | Calls with null outcome or extraction error | `just failed-extractions --campaign "Pune Dec"` |
| `just stuck-calls` | Calls stuck `in_progress` beyond grace | `just stuck-calls --campaign "Pune Dec"` |
| `just rerun-extraction <session_id>` | Re-run Groq extraction from stored transcript | `just rerun-extraction abc123` |

### Operator Actions (write)

| Command | What it does | Example |
|---------|-------------|---------|
| `just reset-lead <phone>` | Reset lead to pending, 0 attempts | `just reset-lead 9123456789 --campaign "Pune"` |
| `just force-outcome <session_id> <outcome>` | Manually set call outcome | `just force-outcome abc123 Interested` |
| `just settle-campaign <name>` | Force-settle and return unused budget | `just settle-campaign "Pune Dec"` |

---

## Common Workflows

### 1. Onboard a New Client (end-to-end)

```bash
# Step 1: Create the client
just create-client "Acme Realty" "ops@acme.in" "real_estate"
# → Prints client_id and api_key (save the api_key!)

# Step 2: Add credits
just add-credits <client_id> 500

# Step 3: Create a bot config
just create-bot <client_id> "Diya - Pune Hindi" sts pyramid_hi +912240000000 1.49

# Step 4: Create a campaign
just create-campaign <client_id> <bot_config_id> "Pune Jan Batch" 200

# Step 5: Upload leads (CSV)
just upload-leads <api_key> <campaign_id> leads.csv

# Step 6: Start the campaign
just start-campaign <api_key> <campaign_id>

# Step 7: Watch progress
just show-campaign "Pune Jan"
```

After the initial create steps (which need UUIDs from output), all monitoring uses fuzzy names:
```bash
just show-client "Acme"
just show-campaign "Pune"
just campaign-leads "Pune" --status calling
just campaign-calls "Pune"
```

### 2. Debug Missing Post-Call Extraction

When `outcome`, `intent_status`, or `duration_seconds` are null after a call:

```bash
# Step 1: Find calls with failed extraction
just failed-extractions --campaign "Pune Jan"

# Step 2: Inspect a specific call
just show-call <session_call_id>
# Look at:
#   - Duration: is it 0? (call never connected)
#   - Transcript: is it empty? (no turns recorded)
#   - Extraction Error: what went wrong?
#   - Extraction Model: was Groq called?

# Step 3: If transcript exists but extraction failed, re-run it
just rerun-extraction <session_call_id>
# This calls Groq again with the stored transcript and updates the DB

# Step 4: If extraction is structurally broken, manually set the outcome
just force-outcome <session_call_id> Interested
```

**Common causes of missing extraction:**
| Symptom | Cause | Fix |
|---------|-------|-----|
| `extraction_error: null`, `outcome: null` | `GROQ_API_KEY` not set when call ended | Set key in `.env`, then `just rerun-extraction` |
| `extraction_error: Groq HTTP 429` | Rate limited | Wait and `just rerun-extraction` |
| `extraction_error: JSONDecodeError` | Groq returned malformed JSON | `just rerun-extraction` (usually works on retry) |
| `transcript: (empty)` | Call disconnected before any turns | `just force-outcome <id> Unknown` |
| `duration_seconds: null` | Pipeline crashed before finalize | Check server logs for the session_call_id |

### 3. Re-run Extraction on All Failed Calls

```bash
# List all failed extractions for a campaign
just failed-extractions --campaign "Pune Jan" --limit 50

# Re-run them one at a time (each calls Groq)
just rerun-extraction <session_id_1>
just rerun-extraction <session_id_2>
# ... and so on
```

### 4. Reset a Lead for Retesting

When you need to call a lead again (e.g., the bot script was buggy):

```bash
# By phone number (within a specific campaign)
just reset-lead 9123456789 --campaign "Pune Jan"

# By lead UUID
just reset-lead <lead_uuid>

# The lead is now:
#   status: pending
#   attempts: 0
#   outcome: null
#   next_attempt_at: NOW()
# Campaign counters are automatically reconciled.
```

### 5. Settle a Stuck Campaign

If a campaign is stuck in `running` with all leads terminal:

```bash
# Check the campaign state
just show-campaign "Pune Jan"
# Look at: calling_leads, pending_leads, callback_leads
# If all are 0 but status is still "running":

# Option A: Release any stuck leads first
just release-stuck-leads <campaign_id>

# Option B: Force-settle (returns unused budget to client)
just settle-campaign "Pune Jan"
```

### 6. Check System Health

```bash
# Plivo balance
just plivo-balance

# Any stuck calls across all campaigns?
just stuck-calls

# Any extraction failures recently?
just failed-extractions --limit 10

# Database connectivity
just db-check
```

---

## How Post-Call Extraction Works

Understanding this flow is critical for debugging:

```
Call Ends (pipeline finalize)
    │
    ├─ Is GROQ_API_KEY set?
    │   ├─ YES → Call Groq with transcript + EXTRACTION_SCHEMA
    │   │        ├─ Success → normalize extraction → update call_log + lead
    │   │        └─ Failure → log error → call_log.extraction_error set
    │   │
    │   └─ Then: Is this a campaign call (pg_ctx exists)?
    │       ├─ YES → Run post_call_processor:
    │       │        ├─ Compute billing (ceil minutes × credits_per_minute)
    │       │        ├─ Update lead status (state machine)
    │       │        ├─ Update campaign counters
    │       │        └─ Fire webhook if terminal outcome
    │       └─ NO → Fire n8n webhook directly (Phase 0 path)
    │
    └─ NO → Skip extraction entirely
             └─ Log: "post_call_extract skipped: GROQ_API_KEY not set"
```

**Key insight:** If `GROQ_API_KEY` is missing at the moment the call ends, extraction is skipped entirely — even if the key exists in `.env`. The check reads the env var at runtime inside the pipeline finalize handler. Make sure the key is set **before** the server starts.

### The Extraction Schema

Each bot script defines an `EXTRACTION_SCHEMA` that controls what Groq extracts:

```python
# Example from sts_scripts/pyramid_mr.py
EXTRACTION_SCHEMA = {
    "mode": "fields",
    "fields": [
        {"key": "intent_status", "type": "enum",
         "values": ["Interested", "Not_Interested", "Callback_Requested",
                    "Busy", "Wrong_Requirement", "Unknown"],
         "required": True},
        {"key": "site_visit_agreed", "type": "boolean"},
        {"key": "callback_time", "type": "datetime"},
        # ... more fields
    ],
    "extraction_rules": "If the caller agreed to a site visit, set intent_status to Interested."
}
```

The `rerun-extraction` command automatically loads the correct schema from the bot's script module.

---

## Environment Variables That Affect CLI

| Variable | Used by | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | All commands | Postgres connection string |
| `GROQ_API_KEY` | `rerun-extraction` | API key for Groq extraction |
| `POST_CALL_MODEL` | `rerun-extraction` | Which Groq model to use (default: `llama-3.3-70b-versatile`) |
| `MAX_CALL_MINUTES` | `stuck-calls` | Grace period calculation for stuck call detection |

---

## Phone Number Formats

The CLI automatically normalizes phone numbers:
- `9123456789` → `+919123456789`
- `09123456789` → `+919123456789`
- `+919123456789` → used as-is

Always stored as E.164 in the database.

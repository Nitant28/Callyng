# Dynamic Script & Post-Call Configuration — Implementation Plan

> **Goal:** Decouple bot scripts and post-call processing from the repo filesystem. Give admin complete control to create, edit, and deploy bot configurations + post-call extraction via API — zero git pushes, zero redeploys, zero disruption to running clients.

---

## Table of Contents

1. [Problem Statement & Phase 0 Hotfix](#1-problem-statement--phase-0-hotfix)
2. [Database Schema & Revisions](#2-database-schema--revisions)
3. [Bot Script Templates (Admin Reference)](#3-bot-script-templates-admin-reference)
4. [Post-Call Template (Admin Reference)](#4-post-call-template-admin-reference)
5. [Runtime Script Loader (In-Memory Prefetch)](#5-runtime-script-loader-in-memory-prefetch)
6. [Post-Call Processing & Snapshotting](#6-post-call-processing--snapshotting)
7. [Admin API Endpoints & Validation](#7-admin-api-endpoints--validation)
8. [CLI Testing Tools](#8-cli-testing-tools)
9. [Migration Strategy (Pre-Launch)](#9-migration-strategy-pre-launch)
10. [Build Order](#10-build-order)

---

## 1. Problem Statement & Phase 0 Hotfix

### Today's coupling
Bot scripts are **Python files inside the repo**. Adding or modifying a bot requires a git push and server redeploy. Post-call processing has hardcoded Pyramid-specific rules.

### The `_pg.script_id` Bug (Immediate Phase 0 Hotfix)
The dialer populates `_pg["script_id"]` from `bot_configs`, but loaders ignore it in favor of env vars. 
*Fix: Implement the explicit 3-tier resolution order below.*

### Unified Script Resolution Order
To make the migration safe and unambiguous, `bot_sts.py` and `bot_cascade.py` will follow exactly this resolution order at `/ws` connect:
1. **In-Memory Prefetch:** Check `PREFETCHED_CONFIGS.pop(call_id)` (The new Database CMS path).
2. **`_pg` Fallback:** If missing, read `body["_pg"]["script_id"]` → `importlib` (The Phase 0 Hotfix path).
3. **Env Var Fallback:** If `_pg` is missing, read `STS_SCRIPT`/`CASCADE_SCRIPT` env vars → `importlib` (Legacy Phase 0 dev path).

*(Paths 2 and 3 must strictly enforce `re.fullmatch(r"^[a-z][a-z0-9_]*$")` to prevent path traversal).*

---

## 2. Database Schema & Revisions

```sql
CREATE TABLE script_configs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id),
    script_id           TEXT NOT NULL,
    route               TEXT NOT NULL CHECK (route IN ('sts', 'cascaded')),
    
    -- Agent identity
    gemini_model        TEXT NOT NULL DEFAULT 'models/gemini-3.1-flash-live-preview',
    gemini_voice        TEXT NOT NULL DEFAULT 'Aoede',
    gemini_language     TEXT NOT NULL DEFAULT 'hi-IN',
    gemini_temperature  NUMERIC(3,2) NOT NULL DEFAULT 0.50,

    -- VAD
    vad_start_sensitivity   TEXT NOT NULL DEFAULT 'HIGH',
    vad_end_sensitivity     TEXT NOT NULL DEFAULT 'LOW',
    vad_silence_duration_ms INT  NOT NULL DEFAULT 800,
    vad_prefix_padding_ms   INT  NOT NULL DEFAULT 300,
    
    -- Prompts
    system_instruction_template TEXT NOT NULL,
    bootstrap_messages_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    goodbye_markers             JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Cascade Specifics
    cascade_stt_provider    TEXT DEFAULT 'sarvam',
    cascade_stt_model       TEXT DEFAULT 'saarika:v2.5',
    cascade_llm_provider    TEXT DEFAULT 'groq',
    cascade_llm_model       TEXT DEFAULT 'llama-3.3-70b-versatile',
    cascade_tts_provider    TEXT DEFAULT 'cartesia',
    cascade_tts_voice       TEXT DEFAULT 'sonic-3',
    cascade_live_tools      JSONB NOT NULL DEFAULT '[]'::jsonb, 
    
    -- Post-call schemas
    extraction_schema   JSONB NOT NULL,
    lead_schema         JSONB NOT NULL DEFAULT '{"fields": []}'::jsonb,
    
    -- Post-call normalization & outcome mapping
    normalization_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome_event_map   JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome_terminal    JSONB NOT NULL DEFAULT '["Interested", "Not_Interested"]'::jsonb,
    outcome_retry       JSONB NOT NULL DEFAULT '["Busy", "Unknown", "Wrong_Requirement"]'::jsonb,
    outcome_callback    JSONB NOT NULL DEFAULT '["Callback_Requested"]'::jsonb,
    
    -- Metadata
    active              BOOLEAN NOT NULL DEFAULT true,
    version             INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE (client_id, script_id)
);

CREATE TABLE script_config_revisions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_config_id    UUID NOT NULL REFERENCES script_configs(id),
    version             INT NOT NULL,
    config_snapshot     JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_config_id, version)
);

ALTER TABLE bot_configs ADD COLUMN script_config_id UUID REFERENCES script_configs(id);
```

**Note on `UNIQUE (client_id, script_id)`:** This intentionally enforces a "no cross-client sharing, clone-on-create if needed" policy. Given the managed-service model, editing one client's prompt should never silently affect another client's bots.
**Note on `cascade_live_tools`:** This array strictly parametrizes the *existing* `push_lead_data` Python handler in `bot_cascade.py` (e.g. enabling it, defining the expected JSON schema fields). It is *not* a generic live-action interpreter, which would introduce massive live-call risks.

---

## 3. Bot Script Templates (Admin Reference)

*(Same as previous iteration: `/template?route=sts` vs `?route=cascaded` returns distinct shapes).*

---

## 4. Post-Call Template (Admin Reference)

*(Same as previous iteration: `extraction_schema`, `normalization_rules`, `outcome_event_map`, etc. If `mode: "summary"` is used without `intent_status`, outcome behavior defaults to "Unknown" → retry until max_attempts → failed).*

---

## 5. Runtime Script Loader (In-Memory Prefetch)

**Constraint Acknowledgement:** Passing the rendered config into `PREFETCHED_CONFIGS[call_id]` deepens the codebase's reliance on a single-worker uvicorn deployment (alongside `_warmup_ready` and `_PG_CONTEXT`). Running `--workers 4` will break this routing. This is an accepted design constraint.

**Solution: Process-Local Memory Dictionary**
1. `concurrent_dialer.py` fetches the `script_configs` row and fully renders templates using `string.Template.safe_substitute(lead_dict)`. *(`lead_dict` must strictly be `LeadContext` fields merged with `lead.metadata` filtered to `^[a-z][a-z0-9_]*$` keys).*
2. The dialer registers this config into `PREFETCHED_CONFIGS[call_id]`.
3. `bot_sts.py`/`bot_cascade.py` `pop()` it at `/ws` connect. Zero DB I/O, zero URL-encoding risk.

**CRITICAL Leak Cleanup:** To prevent unbound memory growth from orphans, we mandate two explicit cleanups:
- `fire_call` must `PREFETCHED_CONFIGS.pop(call_id, None)` in its `except Exception` catch block if Plivo dialing fails.
- The existing `stale_call_log_loop` background task must periodically sweep `PREFETCHED_CONFIGS`. Since that loop uses `RETURNING id`, the sweep should do a separate cheap query against the keys: `SELECT session_call_id FROM call_logs WHERE session_call_id = ANY($1) AND in_progress = FALSE`, and purge those keys.

*(Prewarm Note: Campaign-driven calls currently never populate `_warmup_ready`—only Phase 0 `/start` calls do. Campaign-call prewarm remains unaddressed, but `PREFETCHED_CONFIGS` would be the natural input if/when it's tackled).*

---

## 6. Post-Call Processing & Snapshotting

To prevent call data from being bloated by multi-KB prompt strings, while still providing an ironclad audit trail against mid-call admin edits, we will snapshot **only** the post-call relevant subset (`extraction_schema`, `normalization_rules`, `outcome_terminal/retry/callback`, plus `script_config_id` and `version` for reference) into `call_logs.call_data` at call start. Post-call extraction logic will read directly from this snapshot.

---

## 7. Admin API Endpoints & Validation

| Method | Path | Description |
|---|---|---|
| `POST` | `/internal/script-configs` | Create config. Validates outcome mapping & creates Revision row. |
| `PATCH`| `/internal/script-configs/:id` | Update config. Bumps version, creates Revision row. |
| `POST` | `/internal/script-configs/:id/test` | Dry-run extraction with a transcript. |
| `GET`  | `/internal/script-configs/template`| Returns default template JSON (`?route=sts` or `?route=cascaded`). |
| `GET`  | `/internal/script-configs/:id/revisions` | List historical versions. |
| `POST` | `/internal/script-configs/:id/rollback` | Revert. Body: `{"version": N}`. Reads revision N, applies it as the live config, bumps to version N+1, and writes revision N+1 with that same content so history remains faithfully append-only. |

**Revision Snapshot Timing:** Every successful create/PATCH/rollback writes the *resulting* full config as a new `script_config_revisions` row at the new version number.

**Strict API Validation:** On `POST`/`PATCH` (if not `summary` mode), the API must validate that *every* value in `extraction_schema.fields[intent_status].values` is covered exactly once by `outcome_terminal`, `outcome_retry`, or `outcome_callback` (or implicitly `dnc`).

---

## 8. CLI Testing Tools

To verify that the entire database-driven pipeline works without Admin UI, we will build:
**`python test_call.py --script-config-id <UUID> --phone <PHONE> --route <sts|cascaded>`**

**Duplicate Guard Fix:** To bypass the 5-12 minute duplicate-dial DB locks, and to satisfy the `call_logs.lead_id` Foreign Key constraint downstream, the CLI must automatically insert a throwaway `leads` row into a dedicated sandbox campaign on *every* invocation. It will use this fresh `lead_id` to safely dial the developer's phone and trigger the post-call pipeline in a 30-second loop.

---

## 9. Migration Strategy (Pre-Launch)

1. **Phase 0 Hotfix:** Fix the `_pg.script_id` lookup via explicit resolution order.
2. **Schema & API:** Add DB schema and build Admin CRUD API. 
3. **Data Migration:** Use API/script to convert existing `.py` scripts into DB rows.
4. **Test Calls:** Admins use `test_call.py` (and later the UI) to verify the DB scripts work perfectly.

---

## 10. Build Order

1. **Immediate Phase 0:** Implement explicit 3-tier Script Resolution order (`_pg.script_id` hotfix).
2. **Database:** Alembic migration for `script_configs` and `script_config_revisions`.
3. **Dialer Prefetch & Cleanup:** Implement DB prefetch, template `safe_substitute` filtering, `PREFETCHED_CONFIGS[call_id]` registration, and explicit exception/stale-loop cleanup.
4. **Bot Loaders:** Update bots to execute step 1 of the resolution order (`PREFETCHED_CONFIGS.pop()`).
5. **Snapshotting:** Write the targeted post-call config subset to `call_logs.call_data`.
6. **Post-Call Engine:** Refactor `post_call_extract.py` and `post_call_processor.py` to use the snapshot data.
7. **CLI Tool:** Build `test_call.py` (with throwaway lead generation) to verify the pipeline end-to-end.
8. **Admin API:** Build CRUD endpoints, append-only rollback (`{"version": N}`), validation logic, and template generator.
9. **Data Migration:** Migrate `.py` files to DB rows and verify using the CLI tool.

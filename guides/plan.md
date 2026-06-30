# Dynamic Script & Post-Call Configuration — Implementation Plan

> **Goal:** Decouple bot scripts and post-call processing from the repo filesystem. Give admin complete control to create, edit, and deploy bot configurations + post-call extraction via API — zero git pushes, zero redeploys, zero disruption to running clients.

> **Context for Next Agent:** Steps 1–9 are complete (see §10). CMS migration is done: module scripts are exported to `script_configs` and linked to `bot_configs.script_config_id`. `.py` scripts remain as tier-2 fallback.

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

**Status: implemented (Step 8).**

| Method | Path | Description |
|---|---|---|
| `GET` | `/internal/script-configs` | List configs (`?client_id=`) |
| `GET` | `/internal/script-configs/{id}` | Get one (`?client_id=`) |
| `POST` | `/internal/script-configs` | Create config. Validates outcome mapping & creates Revision row. |
| `PATCH`| `/internal/script-configs/{id}` | Update config. Bumps version, creates Revision row. |
| `POST` | `/internal/script-configs/{id}/test` | Dry-run extraction with a transcript. |
| `GET`  | `/internal/script-configs/template`| Returns default template JSON (`?route=sts` or `?route=cascaded`). |
| `GET`  | `/internal/script-configs/{id}/revisions` | List historical versions. |
| `POST` | `/internal/script-configs/{id}/rollback` | Revert. Body: `{"version": N}`. Append-only: applies revision N, bumps live version, writes new revision row. |

Auth: `X-Admin-Key` header.

**Files:** `api/script_config_validation.py`, `api/routes/internal_script_configs.py`, `db/postgres.py` (CRUD + revisions).

**Revision Snapshot Timing:** Every successful create/PATCH/rollback writes the *resulting* full config as a new `script_config_revisions` row at the new version number.

**Strict API Validation:** On `POST`/`PATCH` (if not `summary` mode), the API validates that *every* value in `extraction_schema.fields[intent_status].values` is covered exactly once by `outcome_terminal`, `outcome_retry`, or `outcome_callback` (or implicitly ``).

---

## 8. CLI Testing Tools

**Status: implemented (Step 7).**

Root CLI to verify the full database-driven pipeline without Admin UI or campaign dialer:

```bash
uv run python scripts/test_call.py --script-config-id <UUID> --phone <PHONE> --route <sts|cascaded>
# or:
just cms-call <script-config-uuid> +919... sts
```

### What it exercises

Same path as production `fire_call`: prefetch → `insert_call_log_start` with snapshot → Plivo → `/ws` → Step 6 post-call engine. **Not** the Phase 0 `POST /start` shortcut (`just call` / `just test-call`).

### Duplicate guard fix

To bypass 5–12 minute duplicate-dial DB locks and satisfy the `call_logs.lead_id` FK, the CLI inserts a **fresh throwaway lead** on every invocation into a dedicated sandbox campaign. The lead row uses a unique synthetic phone (`+cli{uuid}`); the real `--phone` is dialed via `fire_call(..., dial_phone=)`.

### Sandbox seed (`just db-seed`)

| Entity | UUID |
|--------|------|
| Sandbox bot (STS) | `00000000-0000-4000-8000-000000000004` |
| Sandbox bot (cascaded) | `00000000-0000-4000-8000-000000000005` |
| Sandbox campaign (`CLI Test Sandbox`, 500 credits) | `00000000-0000-4000-8000-000000000006` |

The CLI auto-links `bot_configs.script_config_id` on the sandbox bot for the requested `--route` if no dedicated bot exists yet (dev convenience until Step 8 linking UI).

### Prerequisites

- `server.py` running (`just dev`) — holds `PREFETCHED_CONFIGS` (single-worker)
- `NGROK_URL` or public `DIALER_CALLBACK_HOST` for Plivo `/answer` + `/hangup`
- `DATABASE_URL`, `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_PHONE_NUMBER`
- A `script_configs` row for the given `--script-config-id`

### Files

- `scripts/test_call.py` — CLI entry
- `dialer/concurrent_dialer.py` — `fire_call(..., dial_phone=)` returns `session_call_id`
- `db/seed/dev_tenant.sql` — sandbox bots + campaign
- `tests/test_test_call.py` — unit tests for helpers

---

## 9. Migration Strategy (Pre-Launch)

**Status: implemented (Step 9).**

1. **Phase 0 Hotfix:** Fix the `_pg.script_id` lookup via explicit resolution order.
2. **Schema & API:** Add DB schema and build Admin CRUD API.
3. **Data Migration:** `scripts/migrate_script_configs.py` converts module scripts into `script_configs` rows for all active clients and links `bot_configs.script_config_id`.
4. **Test Calls:** Admins use `scripts/test_call.py` / `just cms-call` to verify migrated scripts through the full CMS path.

Migration CLI:

```bash
uv run python scripts/migrate_script_configs.py [--dry-run] [--force-update] [--verify-only]
```

---

## 10. Build Order

1. **[x] Immediate Phase 0:** Implement explicit 3-tier Script Resolution order (`_pg.script_id` hotfix).
2. **[x] Database:** Alembic migration for `script_configs` and `script_config_revisions`.
3. **[x] Dialer Prefetch & Cleanup:** Implement DB prefetch, template `safe_substitute` filtering, `PREFETCHED_CONFIGS[call_id]` registration, and explicit exception/stale-loop cleanup.
4. **[x] Bot Loaders:** Update bots to execute step 1 of the resolution order (`PREFETCHED_CONFIGS.pop()`).
5. **[x] Snapshotting:** Write the targeted post-call config subset to `call_logs.call_data`.
6. **[x] Post-Call Engine:** Refactor `post_call_extract.py` and `post_call_processor.py` to use the snapshot data.
7. **[x] CLI Tool:** Build `scripts/test_call.py` (with throwaway lead generation) to verify the pipeline end-to-end.
8. **[x] Admin API:** Build CRUD endpoints, append-only rollback (`{"version": N}`), validation logic, and template generator.
9. **[x] Data Migration:** Migrate `.py` files to DB rows and verify using the CLI tool.
10. **[x] Frontend CMS:** Build `AdminScriptConfigs.jsx` and refactor `AdminBotConfigs.jsx` to enforce the new workflow.

---

## Verification Log (2026-06-16)

I have performed a thorough codebase audit to verify the implementation of Steps 1 through 8. 

**Result: PASS.** All 8 steps have been correctly implemented without any architectural discrepancies.
- **Step 1 & 4 (Resolution Order / Bot Loaders):** Confirmed `bot_sts.py` and `bot_cascade.py` have been refactored to use `script_runtime.py`, executing the strict 3-tier fallback starting with `pop_prefetched_config`.
- **Step 2 (Database Schema):** Confirmed `db/schema/006_script_configs.sql` precisely maps to the planned schema, including `cascade_live_tools` and `UNIQUE (client_id, script_id)`.
- **Step 3 (Dialer Prefetch & Cleanup):** Confirmed `concurrent_dialer.py` uses `register_prefetched_config` and reliably clears it via `pop_prefetched_config` inside its exception handlers. The required `sweep_stale_prefetched_configs` is wired into `maintenance.py`.
- **Step 5 & 6 (Snapshotting & Post-Call Engine):** Confirmed `build_post_call_snapshot_from_prefetch` saves the subset to `call_logs.call_data`, which `post_call_processor.py` successfully parses.
- **Step 7 (CLI Tool):** Confirmed `scripts/test_call.py` safely creates synthetic leads (`+cli{uuid}`) for test loops, sidestepping duplicate locks.
- **Step 8 (Admin API):** Confirmed the presence of `/internal/script-configs` endpoints and `api/script_config_validation.py`.
- **Step 9 (Data Migration):** Confirmed `scripts/migrate_script_configs.py` correctly parses Python modules and exports them to the DB. Verified end-to-end routing with the migrated `script_config_id` via `scripts/test_call.py`.

### Discrepancy Found and Fixed
During Step 9 verification, `scripts/test_call.py` crashed with a `dictionary update sequence element #0 has length 1; 2 is required` error. This was traced to a **double-encoding bug** in `db/postgres.py`: `_script_config_json` was redundantly calling `json.dumps()` on `jsonb` fields, while `asyncpg`'s type codec automatically applies `json.dumps()` during inserts. As a result, JSON objects were persisted as JSON strings. I removed the redundant `json.dumps()` from `_script_config_json`, cleared the corrupted `script_configs`, re-ran the migration script, and successfully fired a Plivo test call.

### Frontend Verification (Step 10)
**Result: PASS.** Frontend successfully implemented.
- **Admin Script Configs:** React UI built correctly with Molten styling. Tabs separate core configuration, prompts, VAD, and schemas.
- **Revision Pruning:** `db/postgres.py` enforces a max revision limit of 5.
- **Admin Bot Configs:** Admin is now strictly forced to select from the existing Script Templates pool. All legacy input fields successfully stripped from the bot config creation and edit forms.
- **Dynamic Template:** "Create Template" correctly fetches live variables from the Python codebase (`sts_scripts/pyramid_bilingual.py`) to generate boilerplate. React JSON spread bug and uncontrolled component bugs fixed.

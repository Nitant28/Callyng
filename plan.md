# Event Architecture Stabilization & Implementation Plan

## Executive Summary
This plan details the steps required to resolve merge conflicts, fix backend and frontend bugs, linearize the Alembic migration history, and ensure that the newly merged **Event Dialer** and existing **Campaign** workflows function reliably without regressions.

---

## Current Status & Issues Identified

1. **Alembic Dual Heads**:
   - `alembic/versions/012_clean_event_schema.py` and `alembic/versions/012_cascade_provider_settings.py` both branched from `011_bot_fixed_start_credits`.
   - `alembic heads` reports two heads: `012_clean_event_schema` and `014_cascade_call_actions`.

2. **Backend Runtime & Validation Bugs**:
   - **`api/script_config_validation.py`**:
     - `NameError: name '_DEFAULT_OUTCOME_BOT_FOLLOW_UP' is not defined` (used on line 535 but never declared).
     - `validate_outcome_mapping()` requires `outcome_bot_follow_up` without a default value, breaking existing test suites and 4-argument call sites.
   - **`api/routes/events.py`**:
     - Uses `PatchEventBody` and `CreateOutcomeMappingBody` as request types, but neither is imported or defined in that file (they exist only in `api/routes/internal.py`), which will cause HTTP 500 errors on `PATCH /api/events/{event_id}`, `POST /api/events/{event_id}/outcomes`, and OpenAPI docs generation.

3. **Frontend Build Failure**:
   - `frontend/src/admin/pages/AdminScriptConfigs.jsx` has mismatched JSX tags from merge conflict resolution:
     - Missing `{activeTab === 'post-call' && (` wrapper before `<OutcomeDragDropEditor />`.
     - Duplicate, broken `{activeTab === 'advanced' && (` block conflicting with the Cascade call-actions advanced tab.
     - `npm run build` fails with Vite parse error on line 1426.

4. **Preservation of Cascade & Telephony COGS Protection**:
   - In `db/postgres.py`, `public_call_detail()` must be preserved to prevent leaking provider COGS (`cost_usd`) and raw telephony dumps (`plivo_hangup_json`) to client frontends.
   - Cascade STT/LLM/TTS provider parameters (37 parameters in `create_script_config`) must stay aligned.

---

## Phase 1: Database & Migration Linearization

### 1.1 Renumber Event Migration to `015`
- **File**: Rename `alembic/versions/012_clean_event_schema.py` → `alembic/versions/015_clean_event_schema.py`.
- **Pointers Update**:
  - `revision = "015_clean_event_schema"`
  - `down_revision = "014_cascade_call_actions"`
- **Resulting Chain**:
  ```
  010_early_disconnect_outcome
    ↓
  011_bot_fixed_start_credits
    ↓
  012_cascade_provider_settings
    ↓
  013_catalog_2026_refresh
    ↓
  014_cascade_call_actions
    ↓
  015_clean_event_schema (HEAD)
  ```
- **Verification**: Run `.venv/bin/alembic heads` and assert exactly one head: `015_clean_event_schema`.

---

## Phase 2: Backend Fixes & Script Config Validation

### 2.1 Fix `api/script_config_validation.py`
1. Define default follow-up outcome list:
   ```python
   _DEFAULT_OUTCOME_BOT_FOLLOW_UP: list[str] = []
   ```
2. Update `validate_outcome_mapping` signature to make `outcome_bot_follow_up` optional:
   ```python
   def validate_outcome_mapping(
       extraction_schema: dict[str, Any],
       outcome_terminal: list[Any],
       outcome_retry: list[Any],
       outcome_callback: list[Any],
       outcome_bot_follow_up: list[Any] | None = None,
   ) -> None:
   ```
3. Default `outcome_bot_follow_up` to `[]` when `None`.

### 2.2 Fix `api/routes/events.py`
1. Import missing request bodies:
   ```python
   from api.routes.internal import CreateOutcomeMappingBody, PatchEventBody
   ```
   (or declare local schemas in `api/routes/events.py` if client-facing validation rules differ from admin).
2. Ensure all routes (`GET`, `POST`, `PATCH`, `DELETE`) properly enforce client isolation using `client_id_uuid(client)`.

### 2.3 Verify `db/postgres.py`
1. Verify `public_call_detail()` is exported and used by `api/routes/calls.py`.
2. Verify all Event CRUD queries:
   - Event management: `create_event`, `get_event`, `list_events`, `update_event`, `delete_event`.
   - Mappings: `create_event_outcome_bot_mapping`, `get_event_outcome_bot_mapping`, `list_event_outcome_bot_mappings`, `update_event_outcome_bot_mapping`, `delete_event_outcome_bot_mapping`.
   - Event Leads: `create_event_lead`, `update_event_lead`, `get_event_lead`, `list_event_leads`, `delete_event_lead`, `count_event_leads`, `terminalize_event_lead`.
   - Dialer: `claim_event_leads_for_dialer`, `fetch_active_event_lead_for_post_call`, `update_event_lead_post_call`, `finalize_event_call_log`, `get_event_bot_for_outcome`.

---

## Phase 3: Frontend JSX Reconciliation

### 3.1 Repair `frontend/src/admin/pages/AdminScriptConfigs.jsx`
1. Cleanly partition the editor tabs:
   - **General**: Client selector, Script ID, Route, Active checkbox.
   - **Prompts**: System Instruction template, Bootstrap messages JSON.
   - **Models**:
     - If `route === 'sts'`: Gemini Realtime inputs + VAD settings.
     - If `route === 'cascaded'`: `CascadeModelsPanel` with provider catalog.
   - **Post-Call**:
     - Extraction schema JSON.
     - Normalization rules JSON.
     - Outcome event map JSON.
     - `OutcomeDragDropEditor` (handling terminal, retry, callback, and bot_follow_up buckets).
   - **Advanced**:
     - `LeadSchemaBuilder`.
     - Cascade call actions (Transfer calling toggle + phone number, Live tools toggle + JSON).
     - Goodbye markers JSON.
2. Remove the duplicated/corrupted older `advanced` tab fragment around lines 1428–1474.
3. Test build:
   ```bash
   cd frontend && npm run build
   ```
   Verify 0 syntax/bundling errors.

---

## Phase 4: Dialer & Post-Call Engine Verification

### 4.1 Redis Locking (`dialer/dialer_lock.py`)
- Confirm resource-specific locking:
  - Campaign lock key: `dialer_lock:{campaign_id}`
  - Event lock key: `dialer_lock:event:{event_id}`
- Verify that `acquire_dialer_lock`, `refresh_dialer_lock`, and `release_dialer_lock` prevent duplicate concurrent workers while avoiding lock collisions between Campaigns and Events.

### 4.2 Event Dialer Loop (`dialer/concurrent_dialer.py`)
- Confirm `start_event_dialer` and `run_event_dialer`:
  - Uses `claim_event_leads_for_dialer` (filtered by `event_id`, using index `idx_leads_event_dialer`).
  - Resolves bot per lead:
    - First attempt (`attempts == 0` or outcome is None) → `primary_bot_config_id`.
    - Repeat attempts with prior outcome → lookup in `event_outcome_bot_mappings`.
    - If unmapped → terminal/fallback handling.
  - Places call via shared, bot-agnostic `fire_call`.

### 4.3 Post-Call Processing (`post_call_processor.py`)
- Verify `process_event_post_call`:
  - Updates lead outcome and sets status (`bot_follow_up` if mapped, `completed` if unmapped terminal).
  - Increments Event lead counters (`pending_leads`, `calling_leads`, `callback_leads`, `completed_leads`, `failed_leads`).
  - Does **not** invoke campaign auto-settlement or budget release.

---

## Phase 5: Verification & Testing Suite

1. **Alembic**:
   - `.venv/bin/alembic check` / `.venv/bin/alembic heads` (clean single head).
2. **Python Unit Tests**:
   - `pytest tests/test_script_config_validation.py -v`
   - `pytest tests/test_script_config_api.py -v`
   - `pytest tests/test_provider_validation.py -v`
   - `pytest tests/test_cascade_call_actions.py -v`
   - `pytest tests/test_list_call_logs_projection.py -v`
3. **Frontend Production Build**:
   - `cd frontend && npm run build` (successful bundle generation).
4. **Campaign Isolation Audit**:
   - Confirm no changes were made to `run_campaign_dialer`, `claim_leads_for_dialer`, or `campaigns` table schema.

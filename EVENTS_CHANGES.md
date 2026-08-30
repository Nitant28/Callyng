# Events Feature — File Changes

Source: commit `e5c9e4f` (branch `event-changes`, on top of `d6c34b5`).
83 files changed. List below is grouped by area, file — change only.

---

## DB / Migrations

`alembic/versions/012_clean_event_schema.py` — add (squashed migration): creates `events`, `event_outcome_bot_mappings` tables; adds `leads.event_id`, `call_logs.event_id`; adds `script_configs.outcome_bot_follow_up`; widens `leads_status_check` for `bot_follow_up`; makes `leads.campaign_id` nullable.

`alembic_backup/versions/011_create_event_table.py` → `020_add_bot_follow_up_outcome_mapping.py` (+ 1 branch-merge migration) — add: real incremental migration history, kept as backup only, not applied (superseded by `012_clean_event_schema.py`).

`alembic_backup/versions/017_create_whatsapp_messages_table.py` — add, but excluded from the squashed migration — table not created in DB.

## Backend — DB layer

`db/postgres.py` — add: `create_event`, `get_event`, `get_event_admin`, `list_events`, `update_event`, `delete_event`, `create_event_outcome_bot_mapping`, `get_event_outcome_bot_mapping`, `list_event_outcome_bot_mappings`, `update_event_outcome_bot_mapping`, `delete_event_outcome_bot_mapping`, `create_event_lead`, `update_event_lead`, `get_event_lead`, `list_event_leads`, `delete_event_lead`, `count_event_leads`, `terminalize_event_lead`, `claim_event_leads_for_dialer`, `fetch_active_event_lead_for_post_call`, `update_event_lead_post_call`, `finalize_event_call_log`, `get_event_bot_for_outcome`, `pause_campaign_budget_exhausted`.
`db/postgres.py` — remove: `public_call_detail()` (field-filtering helper for client-facing call rows) deleted entirely.
`db/postgres.py` — change: `create_script_config` / `_SCRIPT_CONFIG_PATCHABLE` / `_SCRIPT_CONFIG_JSONB` updated to include `outcome_bot_follow_up`.

## Backend — Dialer / Post-call

`dialer/concurrent_dialer.py` — add: `run_event_dialer()`, `start_event_dialer()`, per-lead bot resolution (`primary_bot_config_id` on first attempt, `event_outcome_bot_mappings` lookup on repeat attempts).
`dialer/dialer_lock.py` — change: `_lock_key`/`acquire_dialer_lock`/`refresh_dialer_lock`/`release_dialer_lock` take a `resource_type` param (`"campaign"` vs `"event"`) instead of assuming campaign locks only.
`post_call_processor.py` — add: `process_event_post_call()`, separate from `process_post_call`; unmapped-outcome leads set to `completed` (not `failed`); mapped-outcome leads set to `bot_follow_up` with `next_attempt_at = now()`.
`call_transcript.py` — change: `_pg_context_has_campaign_fields` / `_pg_context_from_call_log` extended to also recognize Event call context (`event_id` alongside `campaign_id`).

## Backend — API routes

`api/routes/events.py` — add (new file): client-facing Event CRUD, outcome-mapping CRUD, event-lead endpoints, dialer start route.
`api/routes/internal.py` — add: admin-side Event CRUD, `PatchEventBody`, `CreateOutcomeMappingBody`, and related admin endpoints.
`api/routes/internal_script_configs.py` — change: `CreateScriptConfigBody` / `PatchScriptConfigBody` add `outcome_bot_follow_up` field.
`api/routes/calls.py` — change: `GET /{session_call_id}` now returns `dict(row)` directly instead of `pg_db.public_call_detail(dict(row))` — removes prior field-filtering on the client-facing call detail response.
`api/routes/whatsapp.py` — add (new file): stub `POST /api/whatsapp/messages` route, logs payload and echoes it back, no DB writes.
`api/script_config_validation.py` — change: `_JSON_LIST_FIELDS`, `_SNAPSHOT_COLUMNS`, `validate_outcome_mapping()` updated for `outcome_bot_follow_up` bucket; `outcome_event_map` removed from `_SNAPSHOT_COLUMNS`.
`server.py` — change: registers new `events` and `whatsapp` routers in `_register_api_routes()`.
`n8n_webhook.py` — change: `fire_event_webhook` payload now includes `lead.id`.
`post_call_extract.py` — remove: `_repair_llm_json()` (unquoted NULL/None/trailing-comma repair) deleted; prompt wording tweaked (`null` → "the literal NULL").

## Frontend — Admin

`frontend/src/admin/pages/AdminEvents.jsx` + `.css` — add (new): admin Events list page.
`frontend/src/admin/pages/AdminCreateEvent.jsx` — add (new): admin Event creation form.
`frontend/src/admin/pages/AdminClientEvents.jsx` + `.css` — add (new): per-client Events view for admin.
`frontend/src/admin/components/Sidebar.jsx` — change: adds Events nav entry.
`frontend/src/admin/pages/AdminScriptConfigs.jsx` — change: large rework, adds `outcome_bot_follow_up` bucket UI.
`frontend/src/admin/pages/AdminBotConfigs.jsx`, `AdminCalls.jsx`, `AdminCampaigns.jsx`, `AdminOverview.jsx` (+`.css`) — change: unrelated/adjacent updates in the same commit.
`frontend/src/constants/sidebar.js` — change: adds Events sidebar constants.

## Frontend — Client

`frontend/src/pages/client/Events/EventsPage.jsx` + `.css` — add (new): client Events list (KPI filter cards, skeleton loading, pagination, search).
`frontend/src/pages/client/Events/EventDetail.jsx` + `EventDetails.css` — add (new): client Event detail page.
`frontend/src/pages/client/Events/EventLeadsTable.jsx` + `.css` — add (new): Event leads table.
`frontend/src/App.jsx` — change: routes wired for new Events pages.
`frontend/src/client/pages/CampaignDetail.jsx` — change: large rework (438 lines), Campaign detail page.
`frontend/src/client/pages/Dashboard.jsx`, `DashboardActivity.jsx`, `DashboardKPIs.jsx` — change: dashboard adjustments.
`frontend/src/client/components/CallTranscriptDrawer.jsx` — change: transcript drawer updates.
`frontend/src/client/components/shared/StatusBadge.jsx` — change: status badge support (likely `bot_follow_up`).
`frontend/src/pages/client/LeadSheet/LeadDrawer.jsx`, `LeadCallPanel.jsx`, `leadUtils.js` — change: lead sheet updates.
`frontend/src/pages/client/Campaigns/index.jsx` — change: Campaigns list page updates.
`frontend/src/pages/client/CampaignDetail/components/LeadsTable.jsx`, `CampaignLeadSheet.jsx` — change: minor additions.
`frontend/src/pages/client/CampaignWorkspace/CallsTab.jsx` — change: minor edit.
`frontend/src/pages/client/CallLogs/index.jsx`, `components/AudioPlayer.jsx` (+`.css`), `CallCard.jsx` (+`.css`), `MetadataPanel.jsx`, `TranscriptDrawer.jsx` — change: call logs UI updates.
`frontend/src/components/client/CallTable.jsx` — change: minor update.
`frontend/src/utils/callLogsHelpers.js` — remove: some helper code removed.
`frontend/src/client/utils/analytics/activity.js`, `constants.js`, `metrics.js`, `computeTurns.js`, `leadsDisplayQueue.js` — change: analytics/util tweaks.
`frontend/src/client/client.css`, `frontend/src/client/styles/dashboard.css` — change: styling updates.
`frontend/src/admin/components/ScriptingGuideModal.jsx`, `frontend/src/components/shared/ScriptingGuideModal.jsx` — change: minor.
`frontend/src/admin/styles/layout.css`, `tokens.css` — change: minor.

## Docs

`guides/EVENT_ARCHITECTURE_WORKPLAN (1).md` — add: copy of the workplan doc committed into repo.
`guides/onprem_airgap_architecture.md` — change: large rewrite, unrelated to Events.

---

## Known bug

`api/routes/events.py` uses `PatchEventBody` and `CreateOutcomeMappingBody` as route parameter types but never imports or defines them in that file (they exist only in `api/routes/internal.py`). Because of `from __future__ import annotations`, this doesn't fail at import time — the app starts fine, but `PATCH /api/events/{event_id}`, `POST /api/events/{event_id}/outcomes`, and `/docs` schema generation will all 500 at request/schema-build time.

## Note on the workplan

`EVENT_ARCHITECTURE_WORKPLAN.md` was not followed as a spec — the implementation was built independently and diverges from it in schema, state machine, and status handling (no budget tracking on Events, no `default_bot_config_id` fallback, new `bot_follow_up` status, unmapped-outcome terminalizes to `completed` not `failed`, extra fields not in the workplan's ER diagram). The workplan doc is out of date relative to the shipped code.

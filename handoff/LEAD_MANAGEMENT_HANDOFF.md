# Lead Management Features — Handoff

## What Was Built

Four new API endpoints for individual lead CRUD operations, a shared campaign-status guard, CLI commands, and documentation.

## New Files

| File | Purpose |
|------|---------|
| `api/guards.py` | Shared guard functions: `require_campaign_modifiable()` and `require_lead_not_calling()` |
| `api/routes/leads.py` | Four new endpoints for lead edit, add, delete, and manual status change |

## Modified Files

| File | Change |
|------|--------|
| `db/postgres.py` | Added 4 new DB functions: `update_lead_fields`, `insert_single_lead`, `delete_lead`, `update_lead_status_manual` |
| `server.py` | Registered the new `leads` router |
| `api/routes/campaigns.py` | Added `require_campaign_modifiable` guard to `upload_leads` (was unguarded) |
| `justfile` | Added 4 CLI recipes: `add-lead`, `edit-lead`, `delete-lead`, `change-lead-status` |
| `guides/CLI_GUIDE.md` | Added lead management quick reference table and workflow section |

## New API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `PATCH` | `/api/campaigns/{campaign_id}/leads/{lead_id}` | Edit lead name/lead_type/metadata |
| `POST` | `/api/campaigns/{campaign_id}/leads` | Add a single lead |
| `DELETE` | `/api/campaigns/{campaign_id}/leads/{lead_id}` | Delete a lead |
| `PATCH` | `/api/campaigns/{campaign_id}/leads/{lead_id}/status` | Manual status change |

## Design Decisions

1. **metadata is full-replace, not merge** — client sends the complete metadata object every time. Avoids stale key accumulation.
2. **Phone cannot be edited** — changing the phone is semantically a new lead. Delete and re-add instead.
3. **status, attempts, outcome, extraction cannot be edited via field-edit** — those are system-managed columns.
4. **Counter reconciliation uses full recount** (`reconcile_campaign_counters`) after delete and status change — manual ops are infrequent, correctness over performance.
5. **Duplicate phone on single add returns 409**, not silent skip — unlike CSV bulk upload which skips silently.
6. **upload_leads now has a campaign status guard** — was previously unguarded, allowing uploads to running/completed/cancelled campaigns.
7. **No call_logs are written** by any of these features — respecting the write-once-at-start, finalize-once-at-end principle.

## Allowed Status Transitions (Manual)

| From | To |
|------|-----|
| pending | failed, dnc, callback_scheduled |
| callback_scheduled | pending, failed, dnc |
| failed | pending |
| dnc | pending |
| completed | pending |
| calling | BLOCKED (live call owns this row) |
| any → calling | BLOCKED (dialer-only transition) |

## Campaign Status Guard

| Campaign Status | Leads Modifiable? |
|----------------|-------------------|
| draft | Yes |
| paused | Yes |
| running | No (409) |
| completed | No (409) |
| cancelled | No (409) |

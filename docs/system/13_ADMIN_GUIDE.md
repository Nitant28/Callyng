# 13 — Admin Guide

Admin UI routes under `/admin/*`. All API calls use `X-Admin-Key` against `/internal/*`.

---

## Authentication

- **Login:** `AdminLogin.jsx` — stores key in `localStorage['aakashvani_admin_key']`,
  validates via `GET /internal/health` (403 → invalid).
- **Guard:** `AdminGuard` checks `AdminAuthContext.adminKey`.
- **Logout:** 403/503 from any admin API clears key and redirects to `/admin/login`.

---

## Pages

### Overview (`/admin`)
- **Permissions:** read-only ops dashboard.
- **APIs:** `GET /internal/stats`, `GET /internal/health`.
- **Actions:** none.
- **DB impact:** read `call_logs`, `campaigns`.

### Clients (`/admin/clients`)
- **APIs:** `GET /internal/clients`, `POST /internal/clients`.
- **Actions:** create client (shows `api_key` once), search filter (client-side).
- **DB:** `clients` insert.

### Client detail (`/admin/clients/:id`)
- **APIs:** client get, credits patch/list, webhooks, campaigns list, bot configs,
  campaign create, start/stop, status toggle.
- **Actions:** top-up credits, activate/deactivate client, create campaign for client,
  start/stop campaigns, view ledger.
- **DB:** `clients`, `credit_transactions`, `campaigns`, `webhook_configs`.

### Bot configs (`/admin/bot-configs`)
- **APIs:** list/create/patch bot-configs; list clients + script-configs for forms.
- **Actions:** bind route+script_id+script_config_id+telephony+credits_per_minute.
- **DB:** `bot_configs`.

### Script configs (`/admin/script-configs`)
- **APIs:** full CMS — list, create, patch, revisions, rollback, template, dial-test.
- **Actions:** edit prompts, extraction schema, normalization rules, outcome buckets;
  test extraction; place test call.
- **DB:** `script_configs`, `script_config_revisions`; test calls write `call_logs`
  with `is_test_call` flag.

### Campaigns (`/admin/campaigns`)
- **APIs:** list/create/start/stop/cancel campaigns (any client).
- **Actions:** operator-managed campaigns across tenants.
- **DB:** `campaigns`, budget allocation.

### Calls (`/admin/calls`)
- **APIs:** `GET /internal/calls`, detail, recording.
- **Actions:** audit any call (includes test calls).
- **DB:** read `call_logs`.

### Diagnostics (`/admin/diagnostics`)
- **APIs:** health, recent calls (limit 200), `POST .../reconcile`, `POST .../release-stuck`.
- **Actions:** fix counter drift, release stuck leads.
- **DB:** `campaigns` counters reconcile; `leads` status fixes.

### Webhooks (`/admin/webhooks`)
- **APIs:** list clients, get client webhooks, `POST /internal/webhook-configs`.
- **Actions:** upsert per-event n8n URL+secret.
- **DB:** `webhook_configs`.

---

## Permissions model

Single shared admin key (`ADMIN_API_KEY`). No per-admin users, no audit log of
admin actions. **Not verified from source:** any future RBAC.

---

## Database impact summary

| Admin action | Tables touched |
|--------------|----------------|
| Create client | `clients` |
| Top-up credits | `clients`, `credit_transactions` |
| Create bot | `bot_configs` |
| Create/edit script | `script_configs`, `script_config_revisions` |
| Create campaign | `campaigns`, `clients` (budget −) |
| Start campaign | `campaigns`, `leads`, dialer side effects |
| Reconcile | `campaigns` (counter overwrite) |
| Webhook upsert | `webhook_configs` |

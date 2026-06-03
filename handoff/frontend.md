# Frontend Handoff: Aakashvani API Endpoints & Privileges

This document outlines the capabilities, endpoints, and intended privileges for both the **Client Web App** and the **Admin Dashboard**.

## 1. Authentication & Security

* **CORS**: Restricted to `https://admin.aakashvani.ai`, `https://app.aakashvani.ai`, and `http://localhost:3000`.
* **Rate Limiting**: All endpoints are rate-limited to 100 requests per minute per IP using `slowapi`.
* **Client Auth**: Uses Bearer tokens (`api_key` generated upon client creation).
* **Admin Auth**: Uses a static `ADMIN_API_KEY` defined in the environment variables.

---

## 2. Client Web App Privileges (Authenticated via `Bearer <api_key>`)

The client web app is scoped purely to the client's own data. All routes begin with `/api/`.

### Campaigns
* `POST /api/campaigns` - Create a new campaign.
* `GET /api/campaigns` - List all campaigns.
* `GET /api/campaigns/:id` - View campaign details, including denormalized counters.
* `PATCH /api/campaigns/:id` - Update campaign settings (name, concurrency, retry logic).
* `PATCH /api/campaigns/:id/start` - Start a campaign (only works if status is "draft").
* `PATCH /api/campaigns/:id/stop` - Gracefully stop a running campaign (sets status to "paused").
* `PATCH /api/campaigns/:id/cancel` - Cancel a campaign and settle remaining budget back to the client.

### Leads & Calls
* `POST /api/campaigns/:id/leads/batch` - Upload leads to a campaign.
* `GET /api/campaigns/:id/leads` - Paginated list of leads (includes `total_count`).
* `GET /api/calls` - Paginated list of all calls for the client (includes `total_count`).
* `GET /api/calls/:session_call_id` - Detailed call transcript and extraction data.

### Billing
* `GET /api/credits/balance` - Check current credit balance.

---

## 3. Admin Dashboard Privileges (Authenticated via `Bearer <ADMIN_API_KEY>`)

The admin dashboard has god-mode capabilities to manage clients, bots, and system health. All routes begin with `/internal/`.

### Client Management
* `GET /internal/clients` - List all clients.
* `GET /internal/clients/:id` - View single client details.
* `POST /internal/clients` - Create a new client (returns the `api_key`).
* `PATCH /internal/clients/:id/status` - Suspend or reactivate a client (`active` boolean).

### Billing & Typo Corrections
* `GET /internal/clients/:id/credits` - View full credit transaction ledger.
* `PATCH /internal/clients/:id/credits` - Top up or deduct credits manually (negative values allowed for typo correction).

### Bot Configurations & Pricing
* `GET /internal/bot-configs` - List all bot configurations.
* `POST /internal/bot-configs` - Create a new bot configuration (requires a valid script).
* `PATCH /internal/bot-configs/:id` - Update bot configuration (e.g., adjust `credits_per_minute` price or disable it).

### Campaign Overrides (Emergency Controls)
* `GET /internal/campaigns/:id` - View any client's campaign.
* `PATCH /internal/campaigns/:id` - Override campaign settings.
* `PATCH /internal/campaigns/:id/stop` - Force-pause a rogue campaign.
* `PATCH /internal/campaigns/:id/cancel` - Force-cancel a campaign.

### System Troubleshooting & Ops
* `GET /internal/scripts` - List all available script modules for bot creation.
* `GET /internal/clients/:id/webhooks` - View a client's webhook configurations to troubleshoot delivery.
* `POST /internal/webhook-configs` - Configure a webhook for a client.
* `GET /internal/calls` - Global paginated list of all calls across all clients (includes `total_count`).
* `GET /internal/health` - Extended system health (active calls, PostgreSQL pool stats, Plivo balance).
* `GET /internal/stats` - Global daily metrics (total calls today, active campaigns, credits burned today) for dashboard widgets.

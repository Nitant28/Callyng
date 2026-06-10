# Project: Aakashvani Admin SPA Skeleton Integration

## Architecture
- **API Fetch Utility**: Centralized HTTP client using native `fetch` or `axios` wrapper (`apiFetch`) that intercepts requests and attaches the `X-Admin-Key` header on all `/internal/*` endpoints. If the response is a 403 or 503 error, clear the key and redirect to `/admin/login`.
- **Authorization Separation**:
  - `/internal/*` routes: Authenticate using the `X-Admin-Key` header containing the administrative password.
  - `/api/*` routes: Authenticate using the `Authorization: Bearer <client_api_key>` header.
- **State Isolation**: Admin API Key must NEVER be stored in `localStorage` or `sessionStorage`. It must reside solely in React memory state (using `AdminAuthContext`).
- **Real-time Polling**:
  - Campaigns page: Poll `/api/campaigns/:id/stats` every 5 seconds when in a running state.
  - Calls page: Poll `/api/calls/:session_call_id` every 3 seconds when `in_progress=true` in the active call log.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | Auth & Core Hooks | Setup `AdminAuthContext`, `apiFetch` utility, secure key state management, adapt Route Guards. | None | DONE |
| 2 | Clients & Bot Configs | Integrate Client list, Client detail, Create client modal, update credits form. Integrate Bot Configs list & Create bot config with script validation. | M1 | IN_PROGRESS |
| 3 | Campaigns, Leads & Webhooks | Integrate Campaign Detail, list campaigns scoped by client, pagination, status filter for leads (`/api/campaigns/:id/leads`), Client Webhooks upsert form. | M2 | PLANNED |
| 4 | Calls & Diagnostics | Integrate global calls feed, active call transcript slide-out, Diagnostics view (Plivo balance instruction, stuck/failed calls filters). | M3 | PLANNED |
| 5 | Quality Gate & Verification | Run `npm run build`, E2E connection checks, Forensic integrity checks. | M4 | PLANNED |

## Interface Contracts
### Admin Authentication
- Header: `X-Admin-Key`
- Env Variable: `ADMIN_API_KEY`
- Target Endpoint: `/internal/*`

### Client Authentication
- Header: `Authorization: Bearer <client_api_key>`
- Target Endpoint: `/api/*`

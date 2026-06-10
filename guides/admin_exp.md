# Admin Dashboard Backend Expectations

This document outlines the API endpoints, data payloads, and technical expectations required by the backend for each page of the Admin Dashboard.

## General Technical Requirements
- **Authentication**: All `/internal/*` routes require an `Authorization: Bearer <admin_secret>` header. The token should be retrieved from `localStorage` (e.g., `admin_api_key`).
- **Pagination**: Any list endpoints (clients, calls, etc.) will return `{ items: [...], total_count: X, limit: Y, offset: Z }` (or similar standard pagination structure). The frontend must send `limit` and `offset` query parameters.
- **Error Handling**: Gracefully handle `401 Unauthorized` (clear token and redirect to login), `400 Bad Request` (show API error messages), and `404 Not Found`.
- **API Instance**: A dedicated Axios or fetch wrapper (e.g., `src/api/admin.ts`) should automatically attach the admin token to prevent cross-contamination with the client portal.

## 1. Login Page (`/admin/login`)
- **Action**: User inputs the Admin Secret.
- **Backend Expectation**: No explicit `/login` endpoint. The frontend should securely save the key to `localStorage`. Optionally, test the key against `GET /internal/health` or `GET /internal/stats` to verify validity before redirecting.

## 2. Global Overview (`/admin`)
- **Endpoints**: 
  - `GET /internal/stats`: Returns platform-wide metrics (Total Calls Today, Active Campaigns, Credits Burned Today).
  - `GET /internal/health`: Returns system health metrics (Postgres connection stats, Plivo cash balance).
- **Backend Expectation**: The dashboard should poll these endpoints periodically or fetch on mount.

## 3. Clients List (`/admin/clients`)
- **Endpoints**:
  - `GET /internal/clients?limit=X&offset=Y`: Fetches paginated list of clients.
  - `POST /internal/clients`: Creates a new client.
    - **Payload**: `{ name: string, email: string, industry?: string }`
    - **Response Expectation**: Must return the generated `api_key` **once**. The UI must display this in a one-time modal with a "Copy" button.
  - `PATCH /internal/clients/:id/status`: Suspends or activates a client.
    - **Payload Example**: `{ is_active: boolean }`
- **Backend Expectation**: Send proper pagination params. Handle the one-time `api_key` display securely.

## 4. Client Detail & Billing (`/admin/clients/:id`)
- **Endpoints**:
  - `GET /internal/clients/:id`: Fetches client overview data.
  - `GET /internal/clients/:id/credits`: Fetches billing ledger (credit transactions).
  - `PATCH /internal/clients/:id/credits`: Adjusts client balance.
    - **Payload Example**: `{ amount_credits: number, note: string }`
  - `GET /internal/clients/:id/webhooks`: Fetches configured webhooks for the client.
- **Backend Expectation**: Provide UI tabs to separate these concerns. Ensure the "Adjust Balance" modal allows negative numbers for deductions.

## 5. Bot Configurations (`/admin/bot-configs`)
- **Endpoints**:
  - `GET /internal/bot-configs`: Fetches all AI bots.
  - `GET /internal/scripts`: Fetches available scripts (for creating a new bot).
  - `POST /internal/bot-configs`: Registers a new bot.
    - **Payload Example**: `{ name: string, script_id: string, route: string, telephony_number: string, credits_per_minute: number }`
  - `PATCH /internal/bot-configs/:id`: Updates bot details (primarily pricing).
    - **Payload Example**: `{ credits_per_minute: number }`
- **Backend Expectation**: Retrieve scripts from `/internal/scripts` to populate the dropdown in the "Create Bot" modal.

## 6. Global Calls & Emergency Overrides (`/admin/calls`)
- **Endpoints**:
  - `GET /internal/calls?limit=X&offset=Y`: Global feed of all outbound calls.
  - `GET /internal/campaigns/:id`: Fetches campaign details when clicked.
  - `PATCH /internal/campaigns/:id/stop`: Force pauses the dialer.
  - `PATCH /internal/campaigns/:id/cancel`: Force cancels the campaign and refunds unused budget.
- **Backend Expectation**: High-frequency polling might be needed for the global call feed. Emergency actions (`stop` and `cancel`) must clearly warn the admin about the consequences (e.g., refunding budget on cancel).

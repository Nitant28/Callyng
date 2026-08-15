# Aakashvani Frontend UI/UX & Technical Architecture (For AI Agent)

> **SYSTEM PROMPT / CONTEXT FOR AI FRONTEND BUILDER:**
> You are tasked with building the frontend for "Aakashvani", a multi-tenant AI outbound calling platform. The backend is fully complete and written in FastAPI. 
> Your job is to generate a fully functioning SPA (React/Next.js recommended) with two distinct portals: **Admin Dashboard** and **Client Dashboard**.

---

## 1. Authentication & Technical Expectations

### Login Flow (No Passwords)
* **API Key Auth**: Both portals rely on highly secure, single-input login screens. There is no traditional "Sign Up" or "Forgot Password" functionality.
* **Admin Login**: Prompts for a static `Admin Secret`. The app must save this to `localStorage` (e.g., `admin_api_key`) and attach it as `Authorization: Bearer <key>` to all `api.example.com/internal/*` routes.
* **Client Login**: Prompts for a `Client API Key` (which they received manually from the admin). Saves to `localStorage` (e.g., `client_api_key`) and attaches to all `api.example.com/api/*` routes.

### Technical Expectations
* **State Management**: Use React Query, SWR, or RTK Query for data fetching, caching, and polling. (Campaign progress and active call counters require frequent polling).
* **Pagination**: Lists like calls and leads return `{ leads: [...], total_count: X, limit: Y, offset: Z }`. Implement proper offset-based pagination controls on tables.
* **Error Handling**: Gracefully handle `401 Unauthorized` (clear token, redirect to login), `404 Not Found`, and `400 Bad Request` (display API error strings in Toast notifications).
* **API Wrapping**: Create two distinct Axios/fetch instances to ensure Admin keys and Client keys never bleed into the wrong requests.

---

## 2. Admin Portal: User Flow & Page Requirements

**The Admin User Journey:**
1. **Logs in** using the environment's `ADMIN_API_KEY`.
2. Lands on the **Global Overview** to check system health and daily revenue/usage.
3. Clicks into **Clients** to onboard a new business. Clicks "Create Client", enters details, and securely copies the one-time generated `api_key` to email to the client.
4. Clicks into the specific **Client Detail** to add prepaid credits to their ledger.
5. Monitors **Bot Configs** to add new AI personas if required.
6. Reacts to emergencies: If a client configures a campaign improperly, the admin goes to **Global Calls**, clicks the `campaign_id`, and hits "Force Stop".

### Page-by-Page Requirements

#### A. Login Page (`/admin/login`)
* **UI**: Clean, centered single-input field for "Admin Key". Submit button.
* **Logic**: On submit, save to `localStorage` and redirect to Overview.

#### B. Global Overview (`/admin`)
* **API**: `GET /internal/stats`, `GET /internal/health`
* **Data Displayed**: 
  * Big Metric Cards: Total Calls Today, Active Campaigns, Credits Burned Today.
  * System Health: Postgres connection stats, Plivo (telephony) Cash Balance.

#### C. Clients List (`/admin/clients`)
* **API**: `GET /internal/clients`, `POST /internal/clients`, `PATCH /internal/clients/:id/status`
* **Data Displayed**: Paginated table showing Client Name, Email, Industry, and `active` status badge.
* **Interactions**: 
  * "Suspend" toggle on each row to instantly cut off platform access.
  * "Create New Client" Modal. **CRITICAL**: The success response contains the `api_key`. Show a one-time modal with a "Copy to Clipboard" button. Tell the user it will never be shown again.

#### D. Client Detail & Billing (`/admin/clients/:id`)
* **API**: `GET /internal/clients/:id`, `GET /internal/clients/:id/credits`, `PATCH /internal/clients/:id/credits`, `GET /internal/clients/:id/webhooks`
* **Data Displayed**:
  * **Tabs**: Overview, Billing Ledger, Webhooks.
  * **Billing Ledger**: Table of `credit_transactions` (Date, Amount, Note).
* **Interactions**: 
  * "Adjust Balance" Modal: Input for `amount` (allows negative for deductions/corrections) and `note`.

#### E. Bot Configurations (`/admin/bot-configs`)
* **API**: `GET /internal/bot-configs`, `POST /internal/bot-configs`, `PATCH /internal/bot-configs/:id`, `GET /internal/scripts`
* **Data Displayed**: Table of all AI bots (Name, Route, Script ID, Phone Number, Credits/Minute).
* **Interactions**: 
  * "Create Bot" Modal: Dropdown for `script_id` (fetched from `/internal/scripts`).
  * "Edit Bot Price" Modal: Patch `credits_per_minute` and `fixed_start_credits`. Labels are ₹/min and setup ₹/call (not hourly).

#### F. Global Calls & Emergency Overrides (`/admin/calls`)
* **API**: `GET /internal/calls`, `GET /internal/campaigns/:id`, `PATCH /internal/campaigns/:id/stop`, `PATCH /internal/campaigns/:id/cancel`
* **Data Displayed**: Global feed of all outbound calls across the platform.
* **Interactions**: Click on a `campaign_id` to open an emergency modal with "Force Pause" (stops dialer immediately) and "Force Cancel" (kills campaign and refunds budget).

---

## 3. Client Portal: User Flow & Page Requirements

**The Client User Journey:**
1. **Logs in** using the `api_key` provided by the platform admin.
2. Lands on the **Dashboard** to see their current credit balance and recent campaigns.
3. Navigates to **Campaigns** -> "Create New". Selects an AI Bot, sets concurrency (calls per minute), and allocates budget.
4. Clicks the draft Campaign -> **Leads Tab**. Drags and drops a CSV of contacts.
5. Hits the **Start Campaign** button.
6. Switches to the **Calls Tab** to watch live calls complete, clicking into specific rows to read the AI transcript and view extracted data.

### Page-by-Page Requirements

#### A. Login Page (`/login`)
* **UI**: Clean, centered single-input field for "Your API Key". Submit button.
* **Logic**: On submit, silently test the key against `GET /api/credits/balance`. If 200 OK, save to `localStorage` and redirect to Dashboard. If 401, show "Invalid Key" error.

#### B. Dashboard & Campaign Grid (`/app`)
* **API**: `GET /api/credits/balance`, `GET /api/campaigns`, `POST /api/campaigns`
* **Data Displayed**: 
  * Header/Nav: Current Prepaid Credit Balance (prominently displayed).
  * Body: Grid or Table of Campaigns showing Status (Draft, Running, Paused, Completed, Cancelled) and progress metrics.
* **Interactions**: 
  * "Create Campaign" Wizard: Form taking `name`, `bot_config_id` (from a dropdown), `budget_credits`, and `max_concurrent_calls`.

#### C. Campaign Detail View (`/app/campaigns/:id`)
* **API**: `GET /api/campaigns/:id`, `PATCH /api/campaigns/:id`, `PATCH /api/campaigns/:id/start`, `PATCH /api/campaigns/:id/stop`, `PATCH /api/campaigns/:id/cancel`
* **Data Displayed**: 
  * **Header**: Campaign Name, Status Badge, Budget Allocated vs Used.
  * **Progress Bars**: Render the denormalized counters (`total_leads`, `calling_leads`, `completed_leads`, `failed_leads`) as visual progress bars.
* **Interactions**: 
  * Dynamic action buttons based on status. If Draft: "Start Campaign". If Running: "Pause Campaign". If Paused/Draft: "Cancel & Refund".
  * Edit Settings Form to tweak retry logic and concurrency.

#### D. Leads Management (Tab inside Campaign Detail)
* **API**: `GET /api/campaigns/:id/leads`, `POST /api/campaigns/:id/leads/batch`
* **Data Displayed**: Paginated table of leads (Name, Phone, Status, Call Attempts).
* **Interactions**: 
  * "Upload CSV" drag-and-drop zone. The UI must map CSV headers (Name, Phone Number) into the required JSON array payload for the batch endpoint.

#### E. Call Logs & Transcripts (`/app/calls`)
* **API**: `GET /api/calls`, `GET /api/calls/:session_call_id`
* **Data Displayed**: Paginated table of historical calls (Date, Phone, Duration, Credits Charged).
* **Interactions**: 
  * Click a row to slide out a Drawer or Modal.
  * **Transcript UI**: Render the `transcript` array as chat bubbles (e.g., Left side: AI Bot, Right side: Human).
  * **Extraction UI**: A clean sidebar or card showing key-value pairs extracted by the AI during the call (e.g., `interested: true`, `callback_time: "tomorrow"`).

---

## 4. Recommended File Structure

```text
src/
├── api/
│   ├── admin.ts        # Axios wrappers for /internal/* (attaches Admin key)
│   └── client.ts       # Axios wrappers for /api/* (attaches Client key)
├── components/
│   ├── admin/          # Admin UI (Client Table, Bot Modal, Emergency Controls)
│   ├── client/         # Client UI (Campaign Wizard, CSV Upload, Transcript Bubble)
│   └── shared/         # Reusable UI (Guards, Layouts)
│       └── ui/         # Atomic UI Kit (Button, Card, Badge, ThemeToggle)
├── hooks/              # Custom hooks for auth, toast, polling intervals (e.g., useTheme)
├── contexts/           # Global state contexts (ThemeContext, AuthContext)
│   ├── admin/          # Routes wrapped in an <AdminGuard> to check localStorage
│   └── client/         # Routes wrapped in a <ClientGuard> to check localStorage
├── hooks/              # Custom hooks for auth, toast, polling intervals
└── utils/              # Formatters (Currency, Dates, CSV Parsers)
```

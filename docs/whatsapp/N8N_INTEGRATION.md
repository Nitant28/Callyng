# Remote n8n Integration — Mega_Workflow Contract

## Overview

Production n8n is **hosted separately** at `https://n8n.bhuvisx.com`.
Aakashvani POSTs to the **production webhook URL** of the published **Mega_Workflow**.
We do **not** modify Mega_Workflow from code — only the Aakashvani repository.

```
Aakashvani backend
       ↓ HTTPS POST
Mega_Workflow Webhook
       ↓
Lead Context
  ├── Add Lead → Google Sheets
  ├── Generate Follow-up Email → Gmail
  └── Generate WhatsApp
           ↓ IF
      Send message / Send template
           ↓ HTTP Request
POST /internal/messages/send
           ↓
Provider Manager → Meta / FinBite / Wapi
```

## Responsibility split

| Layer | Responsibility |
|-------|----------------|
| **Aakashvani** | Detect lead_qualified after call, build payload from DB, POST to n8n webhook, expose `/internal/messages/send` for WhatsApp |
| **n8n (Mega_Workflow)** | Route lead to Sheets/Email/WhatsApp, decide message vs template, call Aakashvani send API, keep WhatsApp Trigger branch intact |
| **Provider (Meta/FinBite/Wapi)** | Actual WhatsApp delivery, delivery/read webhooks |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `N8N_BASE_URL` | `https://n8n.bhuvisx.com` |
| `N8N_LEAD_WEBHOOK_URL` | Production webhook URL from Mega_Workflow Webhook node |
| `N8N_WEBHOOK_SECRET` | Sent as `X-Aakashvani-Webhook-Secret` header |
| `N8N_TIMEOUT_SECONDS` | HTTP timeout (default `15`) |

No n8n username/password is stored or used.

## Admin configuration

Configure the production Mega_Workflow webhook at:

**Admin → Webhooks → N8N Follow-up Workflow**

- Paste the production webhook URL (e.g. `https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792`)
- Click **Save** — stored in `integration_settings.n8n_lead_webhook_url`
- Click **Test Connection** — sends a safe `connectivity_test` payload (no WhatsApp/email)

Per-client CRM webhooks on the same page are **not** the n8n follow-up URL.

### URL resolution precedence

When dispatching interested-lead follow-ups:

1. Client-specific DB key `n8n_lead_webhook_url:{client_id}` (if set)
2. Global DB key `n8n_lead_webhook_url` (Admin → Webhooks save)
3. `N8N_LEAD_WEBHOOK_URL` environment variable

## Client visibility

| Surface | What it shows |
|---------|----------------|
| **Client → Campaign → Leads** | Follow-up status, WhatsApp/email channel status, last follow-up per lead |
| **Client → Messages** | WhatsApp conversations from follow-ups (lead, phone, campaign, direction, status) |

Flow: Call → Interested → n8n Mega_Workflow → WhatsApp/email → customer reply → lead lookup → AI response → Messages inbox.


```json
{
  "event": "lead_qualified",
  "event_id": "{session_call_id}:{lead_id}",
  "client_id": "{client_uuid}",
  "client": {
    "id": "{client_uuid}",
    "name": "Dev Client",
    "industry": "real_estate"
  },

  "lead": {
    "id": "{lead_uuid}",
    "phone": "+919876543210",
    "name": "Rahul Sharma",
    "email": "rahul@example.com",
    "lead_type": "warm",
    "whatsapp_opt_in": true,
    "metadata": { "city": "Pune", "email": "rahul@example.com" }
  },

  "call": {
    "id": "{session_call_id}",
    "session_call_id": "{session_call_id}",
    "status": "completed",
    "duration": 95,
    "duration_seconds": 95,
    "billed_minutes": 2,
    "credits_charged": 4.5,
    "route": "sts",
    "recording_url": null
  },

  "extraction": {
    "intent_status": "Interested",
    "summary": "Customer wants a demo next week"
  },

  "qualification": {
    "status": "interested",
    "score": 0,
    "reason": "Customer wants a demo next week"
  },

  "campaign": {
    "id": "{campaign_uuid}",
    "name": "March Outreach"
  },

  "agent": {
    "id": "{bot_config_uuid}"
  },

  "follow_up": {
    "channel": "whatsapp",
    "action": "send",
    "stage": 1
  },

  "metadata": {
    "campaign_id": "{campaign_uuid}",
    "campaign_name": "March Outreach",
    "agent_id": "{bot_config_uuid}"
  }
}
```

### Field sources

| Field | Source |
|-------|--------|
| `event_id` | `{call_logs.session_call_id}:{leads.id}` |
| `client_id` | `campaigns.client_id` |
| `lead.id` | `leads.id` |
| `lead.name` | `leads.name` |
| `lead.phone` | `leads.phone` → E.164 normalised (`+91…`) |
| `lead.email` | `leads.metadata.email` |
| `lead.lead_type` | `leads.lead_type` |
| `lead.metadata` | `leads.metadata` JSON |
| `call.id` / `call.session_call_id` | `call_logs.session_call_id` |
| `call.duration` / `call.duration_seconds` | post-call duration |
| `call.billed_minutes` / `call.credits_charged` | billing calculation |
| `call.route` | `bot_configs.route` |
| `call.recording_url` | `call_logs.recording_url` |
| `extraction` | post-call extraction JSON |
| `qualification.status` | `extraction.intent_status` or outcome |
| `qualification.score` | `extraction.score` (0 if absent) |
| `qualification.reason` | `extraction.summary` or outcome |
| `campaign.id` / `campaign.name` | `campaigns` table |
| `agent.id` | `bot_configs.id` |

Legacy Mega_Workflow expressions like `$json.lead.phone`, `$json.extraction.summary`, and `$json.campaign.name` remain valid.

## Phone number format

- Normalised to **E.164** via `lead_upload.normaliser.normalise_phone` (India default).
- Example: `9876543210` → `+919876543210`.
- If normalisation fails, the raw stored phone is sent unchanged.

## Authentication (Aakashvani → n8n)

```
Content-Type: application/json
X-Aakashvani-Webhook-Secret: {N8N_WEBHOOK_SECRET}
```

Configure the Mega_Workflow Webhook node to validate this header.

## n8n → Aakashvani WhatsApp send contract

After Mega_Workflow's **Generate WhatsApp → IF → Send message / Send template** branch, the HTTP Request node calls:

```
POST {BACKEND_URL}/internal/messages/send
X-Admin-Key: {ADMIN_API_KEY}
Content-Type: application/json
```

### Send text message

```json
{
  "client_id": "{{ $json.client_id }}",
  "to_phone": "{{ $json.lead.phone }}",
  "text": "{{ $json.whatsapp_message }}",
  "lead_id": "{{ $json.lead.id }}",
  "campaign_id": "{{ $json.campaign.id }}",
  "customer_name": "{{ $json.lead.name }}",
  "idempotency_key": "n8n_{{ $json.event_id }}"
}
```

### Send template message

```json
{
  "client_id": "{{ $json.client_id }}",
  "to_phone": "{{ $json.lead.phone }}",
  "template_name": "{{ $json.template_name }}",
  "language": "en",
  "lead_id": "{{ $json.lead.id }}",
  "campaign_id": "{{ $json.campaign.id }}",
  "customer_name": "{{ $json.lead.name }}",
  "idempotency_key": "n8n_{{ $json.event_id }}"
}
```

Aakashvani resolves the client's enabled WhatsApp provider and sends via Provider Manager. n8n never sees WhatsApp credentials.

## Testing procedure

### Step 1 — Unit tests

```powershell
uv run python -m pytest tests/test_n8n_integration.py -v
```

### Step 2 — Check config

```http
GET /internal/n8n/status
X-Admin-Key: {ADMIN_API_KEY}
```

### Step 3 — Dry run (inspect payload, no HTTP to n8n)

```http
POST /internal/n8n/test
X-Admin-Key: {ADMIN_API_KEY}
Content-Type: application/json

{"dry_run": true}
```

Response includes `payload` and `field_sources`.

### Step 4 — Real n8n connectivity test (safe — no customer follow-up)

```http
POST /internal/n8n/settings/test
X-Admin-Key: {ADMIN_API_KEY}
```

Payload: `{"event":"connectivity_test","test":true,"source":"aakashvani_admin"}`

Then check **Mega_Workflow → Executions** in the n8n dashboard.

## Manual n8n configuration still required

1. Set `N8N_WEBHOOK_SECRET` in `.env` and match in Mega_Workflow Webhook node
2. Verify Lead Context node reads `$json.lead`, `$json.extraction`, `$json.campaign`
3. Wire HTTP Request node to `{BACKEND_URL}/internal/messages/send` with `X-Admin-Key`
4. Keep existing WhatsApp Trigger branch unchanged

  ## What Aakashvani does NOT do

- Install or run n8n locally
- Log into n8n programmatically
- Modify Mega_Workflow nodes or expressions
- Send WhatsApp during n8n connectivity tests

# n8n → WhatsApp Integration

> **Remote n8n:** Production n8n runs at `https://n8n.bhuvisx.com` (Mega_Workflow).
> See [N8N_INTEGRATION.md](N8N_INTEGRATION.md) for how Aakashvani POSTs `lead_qualified` events to the remote webhook.

## How it works

n8n automates "when X happens, send WhatsApp." It does **not** need to know
the provider or credentials.

```
Call outcome (e.g. Interested)
 ↓
n8n workflow triggers
 ↓
POST /internal/messages/send          ← admin API key
  { client_id, to_phone, template_name, lead_id, ... }
 ↓
Aakashvani WhatsApp Core
 ↓
Provider Manager → Meta / FinBite / etc.
 ↓
WhatsApp
```

## n8n HTTP Request node config

- **Method:** POST
- **URL:** `{{$env.AAKASHVANI_URL}}/internal/messages/send`
- **Headers:**
  - `X-Admin-Key: {{$env.ADMIN_API_KEY}}`
  - `Content-Type: application/json`
- **Body:**
```json
{
  "client_id": "{{$json.client_id}}",
  "to_phone": "{{$json.phone}}",
  "template_name": "follow_up_interested",
  "language": "en",
  "lead_id": "{{$json.lead_id}}",
  "campaign_id": "{{$json.campaign_id}}",
  "customer_name": "{{$json.name}}",
  "idempotency_key": "n8n_{{$json.lead_id}}_{{$json.workflow_id}}"
}
```

## Follow-up sequences via n8n

Alternatively, n8n can call `POST /internal/messages/followups/start` to
trigger a pre-configured follow-up plan (multiple steps with delays), which
Aakashvani manages internally including customer-reply cancellation.

## What n8n does NOT do

- n8n does not store WhatsApp credentials
- n8n does not call WhatsApp APIs directly
- n8n does not know which provider the client uses

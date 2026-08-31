# AkashVani → Deployed n8n Follow-up Integration

Production n8n (do **not** use localhost for this flow):

```
https://n8n.bhuvisx.com
```

Mega_Workflow webhook:

```
https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792
```

This document describes the **existing** backend path and how to test it
without making a real phone call. It does not invent credentials.

---

## A. Current AkashVani → n8n data flow

```
Outbound call completes
        ↓
call_transcript → extraction (intent_status, summary, bhk, …)
        ↓
post_call_processor.process_post_call
        ↓
outcome_to_event("Interested") → "lead_qualified"
        ↓
n8n_webhook.fire_event_webhook
        ↓
integrations.n8n.payload.build_lead_qualified_payload
        ↓
integrations.n8n.service.N8nService.send_lead_qualified
        ↓
HTTPS POST  N8N_LEAD_WEBHOOK_URL (or N8N_FOLLOWUP_WEBHOOK_URL)
        ↓
Mega_Workflow Webhook → Lead Context → Sheets / Email / WhatsApp
```

n8n failure is logged and **must not** crash post-call settlement
(`N8nService` returns a result; exceptions are caught with retries).

---

## B. Current webhook URL

| Variable | Purpose |
|----------|---------|
| `N8N_LEAD_WEBHOOK_URL` | Primary URL used by `N8nConfig` / `N8nService` |
| `N8N_FOLLOWUP_WEBHOOK_URL` | Alias accepted if `N8N_LEAD_WEBHOOK_URL` is empty |
| `N8N_BASE_URL` | Status/display only (`https://n8n.bhuvisx.com`) |
| `N8N_WEBHOOK_SECRET` | Optional `X-Aakashvani-Webhook-Secret` header |
| `N8N_TIMEOUT_SECONDS` | HTTP timeout (default `15`) |

Recommended `.env` (no secrets in git):

```env
N8N_BASE_URL=https://n8n.bhuvisx.com
N8N_LEAD_WEBHOOK_URL=https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792
# or:
# N8N_FOLLOWUP_WEBHOOK_URL=https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792
N8N_WEBHOOK_SECRET=
N8N_TIMEOUT_SECONDS=15
```

Restart the backend after changing env so live calls pick up the URL.

---

## C. Exact payload structure (what the backend actually sends)

**Event name:** `lead_qualified` (not `lead_followup`).

This matches Mega_Workflow **Lead Context** expressions such as
`$json.body.lead.name` and `$json.body.extraction.intent_status`.

n8n Webhook node wraps the POST JSON under `.body`, so:

| Backend JSON path | Lead Context expression |
|-------------------|-------------------------|
| `lead.name` | `$json.body.lead.name` |
| `lead.phone` | `$json.body.lead.phone` |
| `lead.email` | `$json.body.lead.email` |
| `lead.lead_type` | `$json.body.lead.lead_type` |
| `extraction.intent_status` | `$json.body.extraction.intent_status` |
| `extraction.bhk_preference` | `$json.body.extraction.bhk_preference` |
| `extraction.location_preference` | `$json.body.extraction.location_preference` |
| `extraction.budget` | `$json.body.extraction.budget` |
| `extraction.summary` | `$json.body.extraction.summary` |
| `client.id` / `name` / `industry` | `$json.body.client.*` |
| `campaign.id` / `name` | `$json.body.campaign.*` |
| `call.session_call_id` | `$json.body.call.session_call_id` |

Example (abbreviated):

```json
{
  "event": "lead_qualified",
  "event_id": "test_abc123:<lead-uuid>",
  "client_id": "<uuid>",
  "client": { "id": "<uuid>", "name": "Test Client", "industry": "real_estate" },
  "lead": {
    "id": "<uuid>",
    "phone": "+917397867643",
    "name": "Test Customer",
    "email": "singhnitant28@gmail.com",
    "lead_type": "warm",
    "whatsapp_opt_in": true,
    "metadata": { "email": "singhnitant28@gmail.com", "lead_city": "Pune" }
  },
  "call": {
    "id": "test_abc123",
    "session_call_id": "test_abc123",
    "status": "completed",
    "duration": 95,
    "duration_seconds": 95,
    "route": "sts",
    "recording_url": null
  },
  "extraction": {
    "intent_status": "Interested",
    "summary": "…",
    "bhk_preference": "2 BHK",
    "location_preference": "Pune",
    "budget": "8000000"
  },
  "qualification": { "status": "interested", "score": 0, "reason": "…" },
  "campaign": { "id": "<uuid>", "name": "…" },
  "agent": { "id": "<uuid>" },
  "follow_up": {
    "channel": "whatsapp",
    "action": "send",
    "stage": 1,
    "idempotency_key": "n8n_…_wa_1"
  },
  "metadata": { "campaign_id": "…", "test": true }
}
```

Phone is normalised to E.164 (India default) via `lead_upload.normaliser.normalise_phone`.

---

## D. How to send the test request

### Option 1 — standalone script (recommended, no backend required)

```powershell
cd C:\Users\Shubh\Desktop\AkashVani\aakashvani

# Inspect payload only
uv run python scripts/test_n8n_followup_webhook.py --dry-run

# Send ONE POST to deployed n8n
uv run python scripts/test_n8n_followup_webhook.py
```

### Option 2 — curl (same Mega-compatible body)

Generate JSON with `--dry-run`, save it, then:

```powershell
curl.exe -i -X POST "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792" `
  -H "Content-Type: application/json" `
  -d "@payload.json"
```

### Option 3 — backend admin API (requires backend + env URL)

```http
POST /internal/n8n/test
X-Admin-Key: <ADMIN_API_KEY>
Content-Type: application/json

{}
```

Dry run:

```http
POST /internal/n8n/test
X-Admin-Key: <ADMIN_API_KEY>

{"dry_run": true}
```

---

## E. Expected n8n Webhook output / HTTP response

| Situation | Typical HTTP | What you see |
|-----------|--------------|--------------|
| Workflow **active**, webhook OK | `200` | Body often `{"message":"Workflow was started"}`; Execution appears |
| Workflow **inactive** | `404` | `"webhook not registered"` / similar |
| Auth / header mismatch | `403` / `401` | Auth error |
| Timeout / DNS | no status | Script prints `connection_error` |

**In n8n UI after a successful POST:**

1. Open **Mega_Workflow** → **Executions**
2. Open the newest execution
3. Click **Webhook** — input JSON should show your payload under `body`  
   (e.g. `body.lead.name = "Test Customer"`, `body.extraction.intent_status = "Interested"`)
4. Click **Lead Context** — flattened fields (`name`, `phone`, `summary`, …) should be filled
5. Downstream: **Add Lead** / **Generate Follow-up Email** / **Generate WhatsApp Message**

If Lead Context fields are empty, the Webhook received data but expressions do not match paths (see §F).

---

## F. Mismatch notes (important)

| Suggested / assumed field | Actual Lead Context | Notes |
|---------------------------|---------------------|-------|
| `event: lead_followup` | Backend sends `lead_qualified` | Do not change event unless Mega is updated |
| `lead.intent_status` | `$json.body.extraction.intent_status` | Intent lives under **extraction** |
| `lead.location` | `$json.body.extraction.location_preference` | Different name |
| `lead.bhk_preference` | `$json.body.extraction.bhk_preference` | Under extraction |
| `call.call_id` | `call.session_call_id` / `call.id` | Session id used |
| Flat `lead` only | Also needs `client`, `campaign`, `extraction` | Email/WhatsApp prompts use `client_name`, `summary`, etc. |

Do **not** POST a minimal `{ "lead": { ... } }` only if you want Lead Context + Gemini branches to work — they read extraction/client/campaign too.

---

## G. Production trigger (no real call for testing)

Live path (unchanged architecture):

- File: `post_call_processor.py` → `fire_event_webhook` when outcome maps to `lead_qualified`
- File: `n8n_webhook.py` → Mega payload + `N8nService`
- File: `integrations/n8n/service.py` → HTTP POST with timeout + retries

Set `N8N_LEAD_WEBHOOK_URL` (or alias) and restart backend for real Interested calls.

---

## Remaining credentials (for actual send, not for webhook receipt)

Webhook receipt only needs a reachable active workflow (optional shared secret).

To complete WhatsApp/email **sending** inside Mega:

- Google Gemini credential (Generate nodes)
- Gmail OAuth (Send email)
- Google Sheets OAuth (Add Lead)
- WhatsApp / Meta access token + WABA ID + Phone Number ID
- Approved WhatsApp template (when outside 24h window)
- Mega_Workflow must be **Active** on `n8n.bhuvisx.com`
- Fix known Mega UI issues (empty If1, empty HTTP Request URL, Sheets column mapping) if still present

---

## Failure handling

- Timeout / 5xx: up to 3 attempts with backoff (`N8nService`)
- 4xx: no retry; logged
- Post-call DB work already committed — n8n outage does not roll back the call

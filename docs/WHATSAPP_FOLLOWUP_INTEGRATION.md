# WhatsApp Follow-up Integration (AkashVani + Mega_Workflow)

Beginner-friendly but technically accurate guide for the production WhatsApp
follow-up path. **No real credentials belong in this file.**

---

## 1. Overview

After an outbound AI call, when a lead is classified as **Interested**
(`lead_qualified`), AkashVani POSTs a structured JSON event to the n8n
**Mega_Workflow** webhook. Mega_Workflow can:

- Append the lead to Google Sheets
- Generate and send a follow-up email (Gemini + Gmail)
- Generate a WhatsApp follow-up (Gemini) and send via WhatsApp Cloud API
- Continue chat when the customer replies (WhatsApp Trigger)

AkashVani also exposes `POST /internal/messages/send` so n8n (or Admin) can
send through the **Provider Manager** (Meta / custom) with tenant-scoped
credentials, eligibility checks, and idempotency.

---

## 2. Architecture

```
  Outbound call (Plivo + Gemini)
           │
           ▼
  post_call_processor → outcome_to_event
           │
           │  event = lead_qualified
           ▼
  build_lead_qualified_payload → N8nService POST
           │
           ▼
  ┌────────────────────────────────────────────┐
  │  n8n Mega_Workflow (orchestrator)          │
  │  Webhook → Lead Context                    │
  │     ├─ Add Lead → Google Sheets            │
  │     ├─ Generate Email → Gmail              │
  │     └─ Generate WhatsApp → IF              │
  │           ├─ Send message (session open)   │
  │           └─ Send template (business init) │
  │                 │                          │
  │                 └─ HTTP Request (optional) │
  └────────────────────────────────────────────┘
           │
           │  preferred production path:
           │  POST /internal/messages/send
           ▼
  AakashVani Provider Manager
           │
           ▼
  Meta Cloud API  →  Customer WhatsApp
           │
           ▼
  whatsapp_messages / conversations (DB)
           │
           ▼
  Client UI /app/messages
```

**Local n8n:** `http://localhost:5678` (Meta cannot reach this without a tunnel).  
**Production n8n:** `https://n8n.bhuvisx.com` (documented remote host).

---

## 3. Lead lifecycle

1. Campaign dials lead  
2. Call ends → extraction (`intent_status`, `summary`, preferences, …)  
3. `validate_interested_outcome` / early-disconnect policy  
4. Terminal **Interested** → `lead_qualified` webhook  
5. Mega_Workflow Lead Context flattens payload  
6. Gemini generates WhatsApp JSON `{ "message": "..." }`  
7. IF chooses **text** (24h window) vs **approved template**  
8. Exactly one send path should fire  
9. Status stored (AakashVani DB and/or Meta webhooks)

---

## 4. n8n workflow (Mega_Workflow — inspected locally)

| Node | Purpose |
|------|---------|
| Webhook | `POST` path UUID; entry for AkashVani |
| Lead Context | Maps `$json.body.*` → flat fields |
| Add Lead | Google Sheets append |
| Generate Follow-up Email | Gemini agent + structured parser → Gmail |
| Generate WhatsApp Message | Gemini agent + parser (+ Simple Memory for chat) |
| Edit Fields1 | Copies lead + `output.message` |
| If1 | **Must** choose text vs template (currently empty — fix required) |
| Send message / Send template | n8n WhatsApp Cloud nodes |
| HTTP Request | Intended AakashVani callback (**URL empty — fix required**) |
| WhatsApp Trigger | Inbound customer messages |
| Edit Fields + If | Require phone+message before reply generation |

Local status when audited: **inactive** (`active=false`), id `KqatOjXcByX2rueK`.

Export (redacted) lives at `fixtures/n8n_exports_local/Mega_Workflow__full_redacted.json`.

---

## 5. Data flow (canonical AkashVani → n8n body)

AkashVani POSTs JSON. n8n Webhook v2 exposes it as `$json.body`.

```json
{
  "event": "lead_qualified",
  "event_id": "{session_call_id}:{lead_id}",
  "client_id": "...",
  "client": { "id": "...", "name": "...", "industry": "..." },
  "lead": {
    "id": "...",
    "phone": "+91...",
    "name": "...",
    "email": "...",
    "lead_type": "...",
    "metadata": {},
    "whatsapp_opt_in": true
  },
  "call": { "session_call_id": "...", "duration_seconds": 0, "recording_url": null },
  "extraction": { "intent_status": "Interested", "summary": "..." },
  "qualification": { "status": "interested", "score": 0, "reason": "..." },
  "campaign": { "id": "...", "name": "..." },
  "agent": { "id": "..." },
  "follow_up": {
    "channel": "whatsapp",
    "action": "send|skip",
    "stage": 1,
    "idempotency_key": "n8n_{event_id}_wa_1",
    "skip_reason": null
  },
  "metadata": { "campaign_id": "...", "campaign_name": "...", "agent_id": "..." }
}
```

Lead Context already reads `$json.body.lead.*`, `$json.body.extraction.*`,
`$json.body.campaign.*`, `$json.body.client.*`, `$json.body.call.*`.

---

## 6. Credentials (where they live)

| Secret | Where to configure | Never put in |
|--------|--------------------|--------------|
| Meta access token | n8n WhatsApp credential **and/or** Admin WhatsApp integration | git, frontend, logs |
| WABA ID (Business Account ID) | n8n WhatsApp credential / Admin `business_account_id` | git |
| Phone Number ID | n8n WhatsApp node / Admin `phone_number_id` | confuse with WABA |
| Webhook verify token | Meta App + Admin / WhatsApp Trigger | git |
| Gemini API | n8n Google Gemini credential | git |
| Gmail / Sheets | n8n OAuth credentials | git |
| `ADMIN_API_KEY` | AkashVani `.env` + n8n HTTP header | frontend |
| `N8N_WEBHOOK_SECRET` | AkashVani `.env` + Mega Webhook auth | git commits of real values |

---

## 7. Meta setup

1. Meta Developer App with WhatsApp product  
2. WhatsApp Business Account (**WABA ID**)  
3. Phone number → note **Phone Number ID** (Graph) separately from WABA ID  
4. System user + permanent access token  
5. Message templates approved (name + language)  
6. Webhooks: callback URL must be **public HTTPS**  
7. Verify token match  
8. Business verification + payment method for production messaging  

**Do not confuse:** Phone Number ID ≠ WABA ID ≠ App ID.

---

## 8. n8n configuration checklist

1. Activate **Mega_Workflow** (currently inactive locally)  
2. WhatsApp credential: Access Token + Business Account ID (WABA)  
3. Replace hardcoded Phone Number ID in Send message / Send template with credential/expression  
4. Fix **If1** so only one branch runs (window open → message; else → template)  
5. Configure **HTTP Request** URL to `{AAKASHVANI_URL}/internal/messages/send` with `X-Admin-Key` **or** remove it if n8n WhatsApp nodes are the sole sender (avoid double send)  
6. Map Add Lead column values (currently empty mapping)  
7. Gemini + Gmail + Sheets credentials valid  

---

## 9. Local development (localhost + ngrok)

```
Internet → ngrok HTTPS → localhost:5678 → Mega_Workflow webhook / WhatsApp Trigger
```

- Dev webhook: `https://<ngrok>/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792`  
- Set `N8N_LEAD_WEBHOOK_URL` to that URL for local tests  
- **Never** commit a temporary ngrok URL  
- Meta WhatsApp Trigger also needs the public HTTPS callback  

---

## 10. Production deployment

- Use `https://n8n.bhuvisx.com` (or your stable host)  
- Set `N8N_LEAD_WEBHOOK_URL` to the **production** webhook URL  
- Public AkashVani API URL for HTTP Request / provider webhooks  
- Rotate tokens; enable webhook signature verification  
- Confirm templates approved on the production WABA  

---

## 11. Webhook flow (inbound)

```
Customer WhatsApp
  → Meta
  → WhatsApp Trigger (n8n) OR /internal/messages/webhooks/{integration_id} (AakashVani)
  → persist / generate reply
```

GET verification uses verify token; POST verifies `X-Hub-Signature-256` when `app_secret` is set.

---

## 12. Outbound message flow

```
AkashVani lead_qualified
  → Mega Webhook
  → Gemini WhatsApp text
  → IF → Send message XOR Send template
  → (recommended) POST /internal/messages/send with idempotency_key
  → Meta Graph /{phone-number-id}/messages
```

---

## 13. Template logic

| Condition | Action |
|-----------|--------|
| Last customer inbound ≤ 24h | Free-form text allowed |
| No recent inbound / window closed | Approved template required |
| Missing template when window closed | Fail gracefully — do not send free-form |
| Opt-out / missing phone | `follow_up.action = skip` |

Helpers: `messages/eligibility.py` (`decide_send`, `conversation_window_open`).

---

## 14. Duplicate prevention

1. `event_id` = `{session_call_id}:{lead_id}`  
2. `follow_up.idempotency_key` = `n8n_{event_id}_wa_{stage}`  
3. `POST /internal/messages/send` checks existing successful row by `idempotency_key` **before** calling the provider  
4. DB unique index on `(client_id, idempotency_key)`  

Mega_Workflow must pass the same key on retries.

---

## 15. Error handling

| Case | Behaviour |
|------|-----------|
| Missing phone / opt-out | Skip WhatsApp (`follow_up.action=skip`) |
| Window closed + text only | `conversation_window_closed_template_required` |
| No integration | `no_enabled_whatsapp_integration` |
| Meta 4xx/5xx | Message status `failed`, error stored in metadata |
| n8n unreachable | Logged; call state already committed |
| Gemini malformed | Structured parser fails → do not send |

Never log access tokens.

---

## 16. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Credentials not found | Re-link n8n credential / Admin integration |
| OAuth failure | Re-auth Gmail/Sheets in n8n |
| Invalid access token | Rotate Meta system user token |
| Wrong WABA / Phone Number ID | Copy IDs from Meta WhatsApp → API Setup |
| Template not approved | Submit/approve in Meta Business Manager |
| Webhook verification failed | Match verify token; public HTTPS |
| Localhost unreachable | Use ngrok; update Meta callback |
| Duplicate message | Ensure If1 exclusive; single send path; idempotency key |
| Meta 401/403/429 | Token, permissions, rate limits |

---

## 17. Testing checklist

- [ ] `uv run pytest tests/test_n8n_integration.py tests/test_whatsapp_followup.py -v`  
- [ ] `GET /internal/n8n/status`  
- [ ] `POST /internal/n8n/test` dry_run then live (Webhook only)  
- [ ] Mega Execution shows Lead Context fields populated (`client.name`, `phone`, …)  
- [ ] Sheets / Gmail / WhatsApp with **test** credentials only  
- [ ] Duplicate `idempotency_key` → one Meta send  
- [ ] Opt-out + missing phone → no send  

**Requires real credentials / external service test** for live Meta delivery.

---

## 18. Production readiness checklist

- [ ] Meta app, WABA, phone, payment, business verification  
- [ ] Approved templates  
- [ ] Public HTTPS webhooks  
- [ ] `N8N_LEAD_WEBHOOK_URL` + secret  
- [ ] Mega_Workflow **active** + If1 + HTTP Request fixed  
- [ ] No double-send (n8n WhatsApp XOR AakashVani send)  
- [ ] Idempotency keys wired  
- [ ] Monitoring / failed execution alerts  
- [ ] Secrets only in n8n/Admin/.env — not git  

---

## Manual Mega_Workflow fixes (required in n8n UI)

These cannot be completed from AkashVani code alone:

1. **Activate** Mega_Workflow  
2. **If1**: set condition e.g. conversation window / `template` empty → Send message; else Send template  
3. **HTTP Request**: either configure AakashVani `/internal/messages/send` body **or** disconnect if WhatsApp nodes already send (prevents duplicate)  
4. **Add Lead**: map columns (`name`, `phone`, `summery`, …) from Lead Context  
5. Remove hardcoded Phone Number ID; use credential  
6. Replace placeholder `template` value `"this n8n"` with real approved template name  
7. For inbound replies, do not use `$('Lead Context')` phone on Send nodes — use Edit Fields phone  

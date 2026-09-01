# WhatsApp Module Architecture

```
                     AAKASHVANI
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
 Calls/Campaigns      Messages             Admin
    │                    │                    │
    │               WhatsApp Core        Provider Setup
    │                    │                    │
    └─── n8n ────────────┤                    │
                         │                    │
                   Provider Manager           │
                         │                    │
         ┌───────────────┼───────────────┐    │
         │      │        │        │      │    │
        Meta  FinBite   Wapi  Managed  Custom │
         │      │        │        │      │    │
         └───────────────┼───────────────┘    │
                         │                    │
                      WhatsApp                │
                         │                    │
                     Customer ───Reply──> Webhook
                                              │
                                        WhatsApp Core
                                              │
                                         Messages DB
                                              │
                                       /app/messages
```

## Key boundaries

- **messages/** — Python package with service, repository, credentials, providers.
- **api/routes/internal_messages.py** — Admin/n8n-facing endpoints (auth via `X-Admin-Key`).
- **api/routes/messages.py** — Client-facing read-only endpoints (auth via Bearer token).
- **frontend/src/admin/pages/AdminWebhooks.jsx** — CRM webhooks + N8N Follow-up Workflow URL.
- **frontend/src/client/pages/Messages.jsx** — Client inbox UI.

## Database tables

| Table | Purpose |
|-------|---------|
| `whatsapp_integrations` | Per-client provider config + encrypted credentials |
| `whatsapp_conversations` | Phone ↔ integration thread (unique per integration+phone) |
| `whatsapp_messages` | Individual messages with provider history |
| `whatsapp_templates` | WhatsApp template registry |
| `whatsapp_followup_plans` | Follow-up sequence definitions |
| `whatsapp_followup_jobs` | Scheduled follow-up steps (pending/sent/cancelled/failed) |

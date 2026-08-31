# Follow-up Engine

## Concept

After a call outcome (e.g. "Interested"), Aakashvani can automatically send a
sequence of WhatsApp messages with configurable delays.

```
CALL → Interested
 ↓
WhatsApp Follow-up #1 (immediate)
 ↓ 24 hours
WhatsApp Follow-up #2
 ↓ 48 hours
WhatsApp Follow-up #3
```

If the customer replies at any point, **all pending follow-ups are cancelled**.

## Database tables

- `whatsapp_followup_plans` — sequence definitions (name, trigger_outcome, steps[])
- `whatsapp_followup_jobs` — individual scheduled sends (pending → sent/cancelled/failed)

## Step format

```json
{
  "template_name": "follow_up_day1",
  "language": "en",
  "delay_seconds": 0,
  "text": null
}
```

`delay_seconds` is relative to the plan start time.

## APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /internal/messages/followup-plans?client_id=` | List plans |
| `POST /internal/messages/followup-plans` | Create/update plan |
| `POST /internal/messages/followups/start` | Start follow-ups for a phone/lead |
| `POST /internal/messages/followups/process` | Process due jobs (call periodically) |

## Cancellation

When an inbound webhook delivers a customer message, the webhook handler calls
`cancel_pending_followups()` for that conversation and phone number. All
`pending` jobs become `cancelled` with `cancel_reason = 'customer_replied'`.

## Processing

`POST /internal/messages/followups/process` should be called periodically (e.g.,
every 60 seconds via cron or a background task). It claims due jobs and sends
messages through the normal `send_message()` flow.

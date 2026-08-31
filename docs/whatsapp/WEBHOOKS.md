# Webhook Processing

## Endpoint

```
GET/POST /internal/messages/webhooks/{integration_id}
```

No admin auth required (webhook comes from the BSP, verified via signature).

## Flow

```
WhatsApp BSP
 ↓
POST /internal/messages/webhooks/{integration_id}
 ↓
Look up integration → determine provider
 ↓
provider.verify_webhook(config, headers, raw_body, query)
 ↓ (GET challenge → return hub.challenge)
 ↓ (POST → verify signature)
provider.parse_webhook(headers, body)
 ↓
For each event:
  • status event → update_message_status()
  • incoming message → get_or_create_conversation() + insert_message_idempotent()
  • incoming message → cancel_pending_followups() (customer replied)
 ↓
Return 200
```

## Idempotency

- `whatsapp_messages` has a UNIQUE constraint on `(client_id, provider_message_id)`.
- `ON CONFLICT DO NOTHING` prevents duplicate inserts.
- Additional `idempotency_key` for outbound dedup (e.g., n8n retries).

## Meta Cloud webhook format

Meta sends `entry[].changes[].value.messages[]` for inbound and
`entry[].changes[].value.statuses[]` for delivery updates. The
`MetaCloudProvider.parse_webhook()` normalizes both into `ProviderWebhookEvent`.

## Signature verification

Meta: `X-Hub-Signature-256` HMAC-SHA256 with app_secret.
Custom: `X-Aakashvani-Webhook-Token` header match.
Stub: verify_token query param match or allow_simulated_send.

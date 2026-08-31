# Security

## Credential handling

- Credentials (access_token, api_key, app_secret) are encrypted at rest using
  HMAC-masked XOR with `WHATSAPP_CREDENTIALS_KEY` or `ADMIN_API_KEY`.
- Credentials are **write-only**: saved via Admin API, never returned to any
  frontend (admin or client).
- `public_integration_view()` strips all secret fields before API responses.
- The `configuration` JSONB column stores non-secret fields; secret keys are
  filtered out of the public view.

## Tenant isolation

- Every query in `messages/repository.py` includes `WHERE client_id = $N`.
- Client A cannot see, use, or send through Client B's integration.
- Webhook handler resolves `client_id` from the `integration_id` path param
  (server-side lookup), not from any browser-supplied value.

## Data flow

```
React → Messages API → Provider → WhatsApp
             ↑
       Never: React → WhatsApp directly
```

- No credentials in localStorage, sessionStorage, URLs, or React source.
- Admin UI sends secret fields to the backend; they are encrypted and stored.
- The backend communicates with WhatsApp; the browser never does.

## Webhook verification

- Meta: HMAC-SHA256 signature via `X-Hub-Signature-256` + `app_secret`.
- Custom: shared `webhook_verify_token` in header.
- Stub: token match or `allow_simulated_send` flag (dev only).

# Provider System

## Abstraction

```
WhatsAppProvider (ABC)
 ├── StubWhatsAppProvider      — dev/test, no network
 ├── MetaCloudProvider         — official Graph API v21.0
 ├── CustomWhatsAppProvider    — Aakashvani generic HTTP contract
 ├── PendingDocsProvider       — named slot for FinBite/Wapi/managed
 └── (future adapters)
```

## How to add a new provider

1. Create `messages/providers/<name>.py` implementing `WhatsAppProvider`.
2. Add the key to `PROVIDER_KEYS` in `messages/providers/factory.py`.
3. Add field schema to `PROVIDER_FIELD_SCHEMAS` in the same file.
4. Register in `get_provider()` factory function.
5. Add the key to the DB check constraint via a new Alembic migration.
6. The Admin UI dynamically picks up the new provider from `GET /internal/messages/providers`.

## Provider field schemas

Each provider declares which fields the Admin UI should render. Secret fields
are never returned after save.

```python
PROVIDER_FIELD_SCHEMAS = {
    "meta_cloud": {
        "fields": [
            {"key": "phone_number_id", "label": "Phone number ID", "secret": False},
            {"key": "access_token", "label": "Access token", "secret": True},
            ...
        ],
    },
}
```

## Provider on messages

Every `whatsapp_messages` row stores a `provider` column recording which BSP
was used at send time. If a client switches from FinBite to Meta, history is
preserved: June messages show FinBite, July messages show Meta.

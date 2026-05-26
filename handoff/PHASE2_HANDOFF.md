# Phase 2 implementation handoff

**Date:** May 2026  
**Branch state:** Phase 2 backend implemented on top of Phase 0 (SQLite + Pipecat bots unchanged).

## What was built

### Infrastructure
- **Alembic** (`alembic/`, `alembic.ini`): `just db-migrate` runs `alembic upgrade head`, applies `db/schema/001_initial.sql` + idempotent `002_compat.sql`.
- **`db/postgres.py`**: Full typed query layer (clients, bot_configs, campaigns, leads, call_logs, webhooks, counters, budget helpers).
- **`telephony.py`**: Shared Plivo dial helper (used by `server.py` and dialer).

### APIs
- **`api/auth.py`**: `X-Admin-Key` for `/internal/*`, Bearer SHA-256 for `/api/*`.
- **`api/routes/internal.py`**: 9 admin endpoints.
- **`api/routes/campaigns.py`**: list, upload, start/stop, stats.
- **`api/routes/calls.py`**, **`api/routes/credits.py`**.

### Processors
- **`post_call_processor.py`**: Atomic transaction (lead, call_log, billing, counters); webhooks outside txn.
- **`compliance.py`**: 9am–9pm IST + internal DND.
- **`dialer/cost_guard.py`**, **`dialer/concurrent_dialer.py`**: SKIP LOCKED dialer loop.

### Call pipeline (no bot file edits)
- **`server.py`**: `app.state.pool`, dynamic `/ws` bot from `body._pg.route`, `register_pg_context` for campaign calls.
- **`call_transcript.py`**: SQLite first; Postgres parallel writes (5s timeout); `process_post_call` for campaigns; dev client upsert for Phase 0.
- **`n8n_webhook.py`**: HMAC `X-Aakashvani-Signature` + per-event `webhook_configs`.

### Lead upload
- **`lead_upload/`** parser, validator, normaliser.
- **`LEAD_SCHEMA`** in `sts_scripts/lead_schema_pyramid.py` (imported by pyramid_mr, pyramid_hi, prowave).

### Docs / tooling
- **`env.example`**, **`guides/TESTING.md`**, **`justfile`** recipes, **`tests/test_phase2.py`**.

## Intentionally unchanged
- `bot_sts.py`, `bot_cascade.py`, `call_log_db.py`
- `/answer` and `/ws` — no sync DB on hot path

## Env vars (repo names)
- Use **`PLIVO_PHONE_NUMBER`** (not PLIVO_FROM_NUMBER).
- **`DATABASE_URL`** optional for Phase 0-only testing.
- **`ADMIN_API_KEY`** for `/internal/*`.
- Dev seed client: `00000000-0000-4000-8000-000000000001`, API key `aakashvani_dev_key_change_me`.

## Known follow-ups
1. **nginx** `allow 127.0.0.1` for `/internal/` — documented, not in repo.
2. **`PATCH /internal/campaigns/{id}`** requires `client_id` in JSON body.
3. **Campaign create** pre-allocates budget via `allocate_campaign_budget` but does not auto-start dialer (client `start` only).
4. **Prewarm** still uses env `BOT_ROUTE` / `STS_SCRIPT`, not per-campaign script (acceptable for Phase 2).
5. Run full **`guides/TESTING.md`** on a machine with Docker, Plivo, and ngrok before production.
6. **Cancel vs stop:** `PATCH /api/campaigns/{id}/cancel` (see guides/TESTING.md §12). Deferred hardening list in **ROADMAP.md** (Phase 2 hardening — deferred).

## Quick verify
```bash
just sync
just db-up && just db-migrate && just db-seed && just db-check
uv run pytest tests/test_phase2.py -v -k 'not roundtrip'
just test-call +91...   # no Postgres required
```

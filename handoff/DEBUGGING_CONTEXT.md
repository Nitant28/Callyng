# Aakashvani Phase 2 — Debugging context (May 2026)

Paste this file (or link it) at the start of a new chat to continue campaign/dialer debugging.

## Goal

Multi-tenant Phase 2 works end-to-end: admin setup → lead upload → campaign start → real Plivo outbound call → post-call Postgres + SQLite, without breaking Phase 0 (`just test-call`).

## What already works (verified by user)

- Admin chain: `create-client`, `add-credits`, `create-bot`, `create-campaign`, `list-clients` → HTTP 200
- Client auth: admin key rejected on `/api/*` (403); client Bearer works on upload/start
- Upload: `POST /api/campaigns/{id}/leads/upload` → 200 after using client API key
- Postgres pool, Alembic, `just db-migrate`, `just reconcile-campaign`
- Phase 0 path: `just dev`, `just tunnel`, `just test-call` (SQLite)
- `just release-stuck-leads` / `just reconcile-campaign` recovery scripts

## Active test entities (user session)

| Item | Value |
|------|--------|
| Campaign ID | `f970ba13-d6e2-4f1f-a908-1c806b38af61` |
| Client API key | (user's key from `create-client` — not stored in repo) |
| Admin key | `dev-admin-key-123` in `.env` as `ADMIN_API_KEY` — **only for `/internal/*`, not Bearer on `/api/*` |

Dev seed (if `just db-seed` used):

- Client ID: `00000000-0000-4000-8000-000000000001`
- API key: `aakashvani_dev_key_change_me`
- Campaign ID: `00000000-0000-4000-8000-000000000003`

## Symptom being debugged (latest)

After `just start-campaign`, server logs:

```
Dialer started for campaign f970ba13-...
counters reconciled: pending=3 calling=0 callback=0
(repeats every ~6s) released 3 lead(s) stuck in calling
```

Never saw: `Dialer fired call call_id=...`

### Interpretation

1. Dialer **claims** leads (`pending` → `calling`) and inserts `call_logs` via `insert_call_log_start`.
2. **`fire_call` / Plivo likely fails** (or never rings) because `answer_url` was built as `http://localhost:7860/answer?...` — Plivo cannot reach localhost.
3. Leads stay `status=calling`; next loop has nothing to claim → `release_stuck_calling_leads` releases 3 → repeat.

**Fix applied in repo (user should restart `just dev`):**

- `fire_call` uses `NGROK_URL` from `.env` for Plivo `answer_url` (`_public_base_url()`).
- `start-campaign` passes `NGROK_URL` / `DIALER_CALLBACK_HOST`, not `Host: localhost`.
- `fire_call` releases lead on Plivo failure.

## Key files

| Area | Path |
|------|------|
| Dialer loop | `dialer/concurrent_dialer.py` |
| Plivo helper | `telephony.py` |
| Campaign start | `api/routes/campaigns.py` |
| Lead claim/release | `db/postgres.py` (`claim_leads_for_dialer`, `release_stuck_calling_leads`, `reconcile_campaign_counters`) |
| Compliance | `compliance.py` (9am–9pm IST; `INTERNAL_DND_NUMBERS`) |
| WS + bots | `server.py` (`_resolve_bot`, `register_pg_context`) |
| Post-call | `call_transcript.py`, `post_call_processor.py` |

## Env checklist for dialer to work

```bash
NGROK_URL=https://your-subdomain.ngrok-free.app   # REQUIRED for campaign dials
PLIVO_AUTH_ID=...
PLIVO_AUTH_TOKEN=...
PLIVO_PHONE_NUMBER=+91...
DATABASE_URL=postgresql://...
ADMIN_API_KEY=...          # X-Admin-Key only
GOOGLE_API_KEY=...         # STS
GROQ_API_KEY=...           # post-call extraction
```

Optional: `DIALER_CALLBACK_HOST` — overrides public base URL for dialer (defaults to `NGROK_URL`).

Terminals: **T1** `just dev`, **T2** `just tunnel`, **T3** curl/just commands.

## Recovery commands

```bash
just stop-campaign <CLIENT_API_KEY> <CAMPAIGN_ID>
just release-stuck-leads <CAMPAIGN_ID>
just reconcile-campaign <CAMPAIGN_ID>
just client-campaigns <CLIENT_API_KEY>
```

Expect after release: `pending_leads=3`, `calling_leads=0`.

## SQL sanity check

```sql
SELECT id, phone, status, next_attempt_at FROM leads
WHERE campaign_id = 'f970ba13-d6e2-4f1f-a908-1c806b38af61';

SELECT pending_leads, calling_leads, status FROM campaigns
WHERE id = 'f970ba13-d6e2-4f1f-a908-1c806b38af61';
```

## Next debugging steps (ordered)

1. Restart `just dev` after pull (NGROK fix in `fire_call`).
2. Confirm `just tunnel` running; `NGROK_URL` in `.env` matches tunnel domain.
3. `just stop-campaign` → `just release-stuck-leads` → `just reconcile-campaign`.
4. `just start-campaign` — watch for **`Dialer fired call`** with `answer_url=https://...ngrok.../answer?...`
5. If Plivo errors, read full exception in logs (auth, from number, DND, compliance).
6. On success: `just client-campaigns`, `just watch-call`, Postgres `call_logs` row with `in_progress` then finalized.

## Known dialer bugs fixed in session (may need server restart)

| Bug | Fix |
|-----|-----|
| **Duplicate calls per lead** | Do not release `calling` leads with a **recent** live `call_logs` row; finalize **stale** `in_progress` logs; clear `in_progress` at pipeline hangup; claim/`fire_call` guards |
| Infinite `counter drift corrected` loop | Release stuck leads when `calling>0` and no claimable leads |
| `just` recipe PYTHONPATH | `scripts/release_stuck_leads.py`, `db_check.py` |
| ModuleNotFoundError `db` | `PYTHONPATH=.` in justfile |
| Admin key on client routes | 403 by design in `api/auth.py` |

## Bot / pipeline constraints (do not break)

- Do **not** edit `bot_sts.py`, `bot_cascade.py`, `call_log_db.py`
- No sync DB on `/answer` or `/ws` hot path
- SQLite always writes first in `call_transcript.py`

## Reference docs

- Full handoff: `handoff/PHASE2_HANDOFF.md`
- Test walkthrough: [guides/TESTING.md](../guides/TESTING.md)
- Architecture: [guides/aakash_arch.md](../guides/aakash_arch.md)

## Open questions for next agent

1. Does `make_plivo_call` throw in logs after NGROK fix?
2. Is `bot_config.telephony_number` set and verified on Plivo?
3. Are test phones outside compliance window or on DND list?
4. Should dialer use `request.app.state` ngrok URL from settings instead of env only?

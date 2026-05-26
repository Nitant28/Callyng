# Aakashvani — Phase 2 Testing Walkthrough

## Prerequisites
- Postgres running: `just db-up` or `docker run -e POSTGRES_PASSWORD=devpassword -e POSTGRES_USER=aakashvani -e POSTGRES_DB=aakashvani -p 5432:5432 postgres:16`
- `.env` filled in with `DATABASE_URL`, `ADMIN_API_KEY`, all AI provider keys, `PLIVO_*`, `NGROK_URL`
- ngrok tunnel running: `just tunnel`
- Server running: `just dev`

## 1. Verify bot call quality (Phase 0 path — no Postgres)
This must pass before anything else. If this breaks, stop and fix it.

### 1a. Direct call via SQLite path
```bash
just test-call +91XXXXXXXXXX "Test Lead" "Pune"
```
Expected: phone rings, bot greets, call completes.

```bash
just sqlite-calls 1
```
Expected: row with route, duration_ms > 0, extraction_json with intent_status.

### 1b. Verify SQLite is written correctly
```bash
just sqlite-calls 3
```

## 2. Verify Postgres schema
```bash
just db-migrate
just db-check
```
Expected: lists all 6 tables (clients, bot_configs, campaigns, leads, call_logs, webhook_configs).

## 3. Admin API walkthrough
### 3a. Create a test client
```bash
just create-client "Test Client" "test@example.com" "real_estate"
```
Save `api_key` and `id` as `CLIENT_ID`.

### 3b. Add credits
```bash
just add-credits <CLIENT_ID> 500
```

### 3c. Register a bot config
```bash
just create-bot <CLIENT_ID> "Diya Marathi Test" sts pyramid_mr "+912240000000" 1.49
```
Save id as `BOT_CONFIG_ID`. Use route `cascaded` (not `cascade`) for cascade bots.

### 3d. Create a campaign
```bash
just create-campaign <CLIENT_ID> <BOT_CONFIG_ID> "Test Campaign" 100
```

### 3e. List everything
```bash
just list-clients
```

## 4. Lead upload walkthrough
Use `fixtures/test_leads.csv` or create your own CSV:
```csv
phone,name,lead_type,City,Budget
+91XXXXXXXXXX,Test Lead,warm,Pune,80L
```

```bash
just upload-leads <API_KEY> <CAMPAIGN_ID> fixtures/test_leads.csv
```

Duplicate upload should show `duplicates_skipped >= 1`.

## 5. Campaign start and dialer walkthrough
```bash
just start-campaign <API_KEY> <CAMPAIGN_ID>
just client-campaigns <API_KEY>
just watch-call <API_KEY> <SESSION_CALL_ID>
```

After call completes:
```bash
just credits <API_KEY>
```

## 6. Parallel write verification
```bash
just test-call +91XXXXXXXXXX "Parallel Test" "Mumbai"
just sqlite-calls 1
```

Check Postgres (dev tenant client):
```bash
uv run python -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv(override=True)
async def check():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    row = await pool.fetchrow('SELECT session_call_id, route, duration_seconds FROM call_logs ORDER BY created_at DESC LIMIT 1')
    print(dict(row) if row else None)
    await pool.close()
asyncio.run(check())
"
```

## 7. Credit and billing verification
Review `billed_minutes`, `credits_charged` on latest `call_logs` row after a campaign call.

## 8. Stop and resume campaign
```bash
just stop-campaign <API_KEY> <CAMPAIGN_ID>
just start-campaign <API_KEY> <CAMPAIGN_ID>
```

`stop` sets status `paused` and preserves leads. Campaign budget stays allocated.

## 12. Cancel vs stop

```bash
just cancel-campaign <API_KEY> <CAMPAIGN_ID>
```

- **stop** (`PATCH .../stop`): pause dialer; leads stay `pending` / `callback_scheduled`; credits remain on the campaign.
- **cancel** (`PATCH .../cancel`): stop dialer; non-terminal leads → `failed`; unused credits return to client balance when `calling_leads` is 0.
- If a call is still in flight, response includes `calling_leads_remaining > 0`; credits return automatically when the last post-call finishes.

After `just db-migrate`, campaigns have `budget_returned_at` for idempotent settlement.

Expected cancel response fields: `leads_terminalized`, `credits_returned`, `calling_leads_remaining`, `budget_settled`.

## 9. Error path testing
- Invalid `script_id`: `just create-bot ... sts ../secrets ...` → 422
- Wrong API key on `/api/campaigns` → 401
- Admin key on `/internal/clients` with Bearer client key → 403

## 10. Final bot quality regression check
```bash
just test-call +91XXXXXXXXXX "Final Test 1" "Pune"
just dev-cascade   # separate terminal
just call +91XXXXXXXXXX "Final Test 2" "Mumbai"
```

## 11. Plivo callee hangup → callback_scheduled
Requires `NGROK_URL` (tunnel exposes `/plivo-hangup`), `PLIVO_HANGUP_CALLBACK_ENABLED=true` (default), and `just db-migrate` (adds `call_logs.plivo_hangup_json`).

1. `just dev` + `just tunnel`; reset campaign leads to `pending` if needed.
2. `just start-campaign <API_KEY> <CAMPAIGN_ID>` with 2+ concurrent slots.
3. Answer a lead and **hang up from the callee phone** (not the bot side).
4. Server logs: `plivo-hangup` with `HangupSource=Callee`, then `Callee hangup -> callback_scheduled`.
5. SQL:
```sql
SELECT status, next_attempt_at, scheduled_callback_at
FROM leads WHERE campaign_id = '<CAMPAIGN_ID>';

SELECT session_call_id, call_sid, plivo_hangup_json
FROM call_logs WHERE campaign_id = '<CAMPAIGN_ID>' ORDER BY started_at DESC LIMIT 3;
```
Expected: lead `callback_scheduled`, `next_attempt_at` ≈ hangup time + `campaign.retry_delay_minutes`; `call_sid` set; `plivo_hangup_json` populated.
6. After Groq post-call finishes, lead should **remain** `callback_scheduled` (not revert to `pending`) unless extraction is `Interested` / `Not_Interested` / `dnc`.

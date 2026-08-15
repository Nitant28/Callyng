# Aakashvani Credit & Billing System

Per-minute pricing, billed **pro-rata per second**, with a configurable **setup fee per started minute**.  
1 credit = ₹1. Clients see rupees. Admins set rates per bot.

This spec is the source of truth for implementation. It matches the **current** architecture (campaign pre-allocation, claim-time reservation, settle-as-delta) and replaces the old ceiling-minute model.

---

## 1. Why this model

Token billing is deferred. Vendor cost is roughly ₹5/min today because prompts are heavy. We bill clients a simple, predictable rate:

| Who | Quoted rate | Notes |
| --- | --- | --- |
| Existing Gemini Live STS clients | ₹3.50–₹4.00 / min | Honour existing quotes |
| New clients | ₹5.00–₹6.00 / min | Reflects current vendor cost |
| Setup fee | ₹0.60 / started minute | Plivo charges ₹0.60 per started minute (0.6 at 0s, another 0.6 as soon as it crosses 1m, 2m, etc.); admin can set custom value |

Tell clients these prices can change if LLM or carrier costs move.

Rates are **never hardcoded** in billing logic. Every bot has its own `credits_per_minute` and `fixed_start_credits` in `bot_configs`. Admins change them from `/admin/bot-configs` or `PATCH /internal/bot-configs/{id}` with no deploy.

---

## 2. Locked decisions (gotchas closed)

These were ambiguous or wrong in the previous draft. Do not re-open them during implementation.

| Topic | Decision |
| --- | --- |
| Duration charge | **Pro-rata per second.** `billed_minutes = duration_seconds / 60.0`. Never `math.ceil(seconds / 60)` for duration rate. |
| Setup charge | **Per started minute.** `started_minutes = math.ceil(duration_seconds / 60)` (or 1 for dial attempt). `setup_charge = started_minutes * fixed_start_credits`. 0–60s = ₹0.60 setup, 61–120s = ₹1.20 setup, 121–180s = ₹1.80 setup. |
| Money type | `Decimal` only. Never `float` for charges, reservations, or budget deltas. |
| Display vs storage | Store 4 decimal places on the call (`credits_charged NUMERIC(10,4)`). **Round HALF_UP to 2 decimal places** when applying to campaign/wallet (`NUMERIC(12,2)`). UI always shows ₹ with 2 decimals. |
| Setup fee column | `fixed_start_credits NUMERIC(10,4) NOT NULL DEFAULT 0.6000`. **Not** `NUMERIC(6,4)` (that overflows at ₹100). |
| Negative / huge rates | Reject. API validation: `credits_per_minute` ∈ [0, 9999.99], `fixed_start_credits` ∈ [0, 999999.9999]. Zero is allowed (free setup or free minutes). |
| When the setup fee applies | Charged per started minute when **Plivo accepted the dial** (ringing, busy, no-answer, connected). **Not** charged if we never sent the dial (claim released, fire_call failed before Plivo, duplicate-skip). |
| Unanswered / busy | Duration = 0 → charge **1 started minute setup fee only (₹0.60)**. |
| Test calls (`is_test_call`) | **Free.** No reservation, no charge, no budget pause. |
| Rate changes mid-flight | **Snapshot at dial.** In-flight calls bill at the rate stored on `call_logs.call_data`. New dials pick up the new rate. Admin copy must say this. |
| Reservation amount | `(setup × 2) + (rate × 2 minutes)`, computed from the campaign’s bot **inside** `claim_leads_for_dialer`. |
| Reservation vs settle | Keep **delta settle**: `budget_used += charged − reserved`. Do not release-then-re-add (race). Do not use a conditional `UPDATE … remaining >= charge` on settle — the call already happened; always commit the charge. |
| Conditional remaining check | Only on **reserve** (claim / pre-dial). If remaining < one reservation, claim 0 leads and the dialer pauses with `reason="budget_exhausted"` (already exists). |
| Campaign overspend | A live call can run longer than the 2-minute buffer. Always commit the charge. If `budget_used > budget_credits` after settle: pause the campaign, deduct the overflow from `clients.balance_credits` (floor at 0), write a `credit_transactions` row (`note` like `Campaign overspend {campaign_id}`). |
| Redis `active_call:{session_id}` | **Not used for billing.** Duration comes from the pipeline’s `duration_seconds`. |
| Pre-allocation | Unchanged. Starting a campaign still deducts `budget_credits` from the client wallet once. Per-call accounting only touches `campaigns.budget_used_credits`. |
| Token metrics | Logged for telemetry. Ignored for billing. |
| Buffer minutes | Constant `BILLING_RESERVE_MINUTES = 2` in **one** Python module (`billing.py`). |

---

## 3. Formula

```
started_minutes    = max(1, math.ceil(duration_seconds / 60))  if connected else 1
setup_charge       = started_minutes × fixed_start_credits
duration_credits   = (duration_seconds / 60) × credits_per_minute
raw_charge         = setup_charge + duration_credits
credits_charged    = raw_charge quantized to 0.0001 (call log)
budget_delta_amt   = credits_charged quantized to 0.01 HALF_UP (campaign / wallet)
```

Reservation at claim:

```
R_reserve = (fixed_start_credits × BILLING_RESERVE_MINUTES) + (credits_per_minute × BILLING_RESERVE_MINUTES)
```

Worked examples (setup ₹0.60 per started min unless noted):

| Rate | Duration | Started mins | Setup charge | Duration charge | Total on call log | Campaign debit (2 dp) |
| --- | --- | --- | --- | --- | --- | --- |
| ₹3.50/min | 15s | 1 | 1 × 0.60 = 0.6000 | 3.50 × 0.25 = 0.8750 | **1.4750** | **1.48** |
| ₹4.00/min | 45s | 1 | 1 × 0.60 = 0.6000 | 4.00 × 0.75 = 3.0000 | **3.6000** | **3.60** |
| ₹3.50/min | 65s (1m5s) | 2 | 2 × 0.60 = 1.2000 | 3.50 × 1.0833 = 3.7917 | **4.9917** | **4.99** |
| ₹6.00/min | 90s (1m30s) + ₹0.50 setup | 2 | 2 × 0.50 = 1.0000 | 6.00 × 1.50 = 9.0000 | **10.0000** | **10.00** |
| ₹4.00/min | Busy, 0s connected | 1 | 1 × 0.60 = 0.6000 | 0 | **0.6000** | **0.60** |
| any | Test call | 0 | 0 | 0 | **0** | **0** |

UI copy for a 15s call: **₹1.48** (setup ₹0.60 + talk ₹0.88). Do not show four decimals to people.

---

## 4. Call lifecycle (how the code actually works)

### 4.1 Campaign start (unchanged)

`clients.balance_credits -= budget_credits`. The campaign now owns that pool.

### 4.2 Pre-reserve at claim (dialer)

Today `claim_leads_for_dialer` does `FOR UPDATE` on the campaign, then:

```
budget_slots = remaining // 2.0     # hardcoded
reserve 2.0 × claimed_count
```

Target: join the campaign’s `bot_configs` **inside the same transaction**, compute `R_reserve`, then:

```
budget_slots = remaining // R_reserve
UPDATE campaigns
  SET budget_used_credits = budget_used_credits + (R_reserve × claimed_count)
WHERE remaining >= R_reserve × claimed_count
```

Return `budget_reserved_credits`, `credits_per_minute`, and `fixed_start_credits` on each claimed lead (or as fields the dialer already has from the bot row fetched in that loop). `fire_call` **must write those same numbers** onto `call_logs.call_data`. Do not re-read the bot after claim — that is the mid-flight rate-change race.

If remaining < one `R_reserve`, claim nothing. The dialer loop already calls `check_campaign_budget` and `pause_campaign(..., reason="budget_exhausted")`. Update `check_campaign_budget` to compare remaining against **this campaign’s** `R_reserve`, not the global `2.0`.

### 4.3 Plivo connect

`insert_call_log_start` stores on `call_data`:

```json
{
  "budget_reserved_credits": 7.6,
  "credits_per_minute": 3.5,
  "fixed_start_credits": 0.6
}
```

(Use JSON numbers from `float(Decimal)` only at the JSON boundary; compute in Decimal.)

### 4.4 Dial never reached Plivo

Existing `_release_lead_to_pending` / `set_credits_charged_zero` paths: settle with `credits_charged = 0` so the full reservation is refunded. Do not charge setup.

### 4.5 Unanswered / busy (Plivo dialed, never connected)

`settle_unanswered_call` today writes `credits_charged = 0` and refunds the reservation. Target: `credits_charged = snapshotted fixed_start_credits` (2 dp on the budget). Duration 0, `billed_minutes = 0`.

### 4.6 Connected call — post-call

`post_call_processor.py` today:

```python
billed_minutes = math.ceil(duration_seconds / 60)
credits_charged = billed_minutes * credits_per_minute
```

and reads **live** `bot_configs.credits_per_minute`.

Target: call `billing.compute_call_charge(duration_seconds, rate, setup)` using **snapshots** from `call_data`, falling back to the bot row only if the snapshot is missing (old in-flight calls during deploy). Then `settle_call_budget(charged, reserved)` as today (delta). Then if `budget_used > budget_credits`, pause + wallet overflow (section 2).

### 4.7 Campaign end (unchanged)

`try_settle_campaign_budget`: `unused = max(budget_credits − budget_used_credits, 0)` returned to the wallet. If the campaign overspent, unused is 0 (overflow already taken from the wallet at settle time).

---

## 5. Schema

### 5.1 New column

```sql
-- db/schema/011_bot_fixed_start_credits.sql
ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS fixed_start_credits NUMERIC(10,4) NOT NULL DEFAULT 0.6000;

ALTER TABLE call_logs
  ALTER COLUMN billed_minutes TYPE NUMERIC(10,4)
  USING billed_minutes::numeric;
```

Alembic revision **`011_bot_fixed_start_credits`**, `down_revision = "010_early_disconnect_outcome"`. Follow the pattern in `005_credit_ledger.py` (read the SQL file). CI runs `alembic upgrade head` before pytest — this migration must apply cleanly on empty Postgres 16.

Existing bots get setup ₹0.60 via `DEFAULT`. No backfill script needed.

### 5.2 Comments to update in `db/schema/001_initial.sql`

Replace every “ceiling minutes / `ceil(duration_seconds / 60)`” comment on `bot_configs`, `campaigns.budget_used_credits`, and `call_logs.billed_minutes`. Fresh installs should not teach the old model. Do **not** change `credits_per_minute NUMERIC(6,2)` or wallet `NUMERIC(12,2)`.

`billed_minutes` meaning becomes “exact minutes as `duration_seconds / 60`”, e.g. 15s → `0.2500`. Integer `2` inserts in tests still work.

---

## 6. Backend API

`POST /internal/bot-configs` and `PATCH /internal/bot-configs/{id}` already exist. Add `fixed_start_credits`.

Create body:

```json
{
  "client_id": "…",
  "name": "Custom Pricing Bot",
  "route": "sts",
  "script_id": "script_456",
  "script_config_id": "…",
  "telephony_number": "+1234567890",
  "credits_per_minute": 5.50,
  "fixed_start_credits": 0.60
}
```

Patch body (either field optional):

```json
{
  "credits_per_minute": 6.00,
  "fixed_start_credits": 0.50
}
```

Pydantic: `Field(ge=0, le=9999.99)` / `Field(ge=0, le=999999.9999)`. Omit `fixed_start_credits` on create → DB default 0.60.

`create_bot_config(...)` in `db/postgres.py` takes `fixed_start_credits: Decimal | float | None = None`. Existing positional test callers stay valid.

GET list/detail already `SELECT *`, so the new column appears without extra queries. `record_to_dict` must serialize `Decimal` as `float` (it already does for other numerics — verify, don’t regress).

No new routes. Client `/api/credits` stays wallet-only.

---

## 7. Frontend — make it obvious, not clever

### 7.1 Bug to kill

`AdminBotConfigs.jsx` labels `credits_per_minute` as **“RATE (INR/HR)”** and **“Hourly Rate (INR)”**. It is per **minute**. That label would make a ₹4.00/min bot look like ₹4/hour. Fix every string.

### 7.2 Admin bot cards (`/admin/bot-configs`)

Show two figures:

- **₹4.00 / min**
- **Setup ₹0.60 / call**

Edit modal: two number inputs (`step="0.01"`, `min="0"`), helper text:

> Talk time is billed per second. A 15-second call at ₹4.00/min + ₹0.60 setup costs ₹1.60. Changes apply to **new dials only**; calls already ringing keep the old rate.

Live preview under the inputs (15s / 1 min / 2 min) using the same formula as the backend (or a tiny shared comment in the spec — JS may round to 2 dp for preview; backend remains source of truth).

Create modal: same two fields. Setup defaults to `0.60` so admins are not forced to remember it. Validate ≥ 0 in the form; show API 422 text if the server rejects.

### 7.3 Deploy-bot modal (`AdminScriptConfigs.jsx`)

Same two fields. Today it only posts `credits_per_minute`. If this form is skipped, every bot deployed from a template gets setup ₹0.60 silently — easy to miss.

### 7.4 Admin call drawer (`AdminCalls.jsx`)

`billed_minutes` will be fractional (`0.25`). Show duration as `mm:ss` (already) and charge as `₹1.48`. Optional second line: `Setup ₹0.60 + 15s talk`. Do not render `0.2500` as a raw integer `0` (`{callData.billed_minutes || 0}` is fine; `{parseInt(...)}` is not).

### 7.5 Client surfaces

Clients already see wallet and campaign used as ₹. Keep that.

Add **Credits** on the client call metadata panel (currently duration/outcome only). Format `₹1.48`. People should be able to match a short call to a small charge without opening a ticket.

Campaign detail already shows `{bot_config.credits_per_minute} credits/min`. Change copy to **₹4.00 per minute** plus **₹0.60 to connect**. Fallback `|| 1` is wrong once rates vary — use the real number or “—”.

### 7.6 Copy rules

- Always ₹, two decimals, `en-IN` grouping where we already use it.
- “Credits” and “rupees” are the same number; don’t mix “credits/min” on one screen and “₹/min” on another. Prefer **₹**.
- Empty/unbilled: **₹0.00** or “—” (test calls), never `null` crashing `.toFixed`.

---

## 8. File change map

CI is `ruff check .` then `alembic upgrade head` then `pytest -x` (`.github/workflows/deploy.yml`). Frontend is not linted in that job, but **VPS deploy runs `npm run build`** — JS must compile.

### 8.1 New files

| File | Why |
| --- | --- |
| `billing.py` | Single home for `BILLING_RESERVE_MINUTES`, `reservation_credits(setup, rate)`, `compute_call_charge(duration_seconds, rate, setup) → {billed_minutes, credits_charged, budget_amount}`. Import from processor, dialer, postgres, tests. |
| `db/schema/011_bot_fixed_start_credits.sql` | Column + `billed_minutes` type change. |
| `alembic/versions/011_bot_fixed_start_credits.py` | `down_revision = "010_early_disconnect_outcome"`. |
| `tests/test_billing.py` | Pure unit tests, no DB: formula examples, setup-only, zero duration, rounding 1.475 → budget 1.48, reservation math, reject negatives via helper clamps if any. |

### 8.2 Backend (must change)

| File | What |
| --- | --- |
| `db/schema/001_initial.sql` | Comments; `fixed_start_credits` on `bot_configs`; `billed_minutes NUMERIC(10,4)`. |
| `db/postgres.py` | Drop `RESERVE_CREDITS_PER_LEAD = 2.0`. `create_bot_config` writes `fixed_start_credits`. `reserve_campaign_budget` / `release_campaign_budget_reservation` take `amount: Decimal` (or `per_lead` from billing), not `2.0 * count`. `claim_leads_for_dialer` reads bot rates in the transaction. `insert_call_log_start` snapshots rate + setup. `settle_unanswered_call` charges setup from snapshot. `settle_call_budget` after delta: if used > budget, deduct overflow from wallet (floor 0), insert `credit_transactions`, return a flag so the dialer/processor can `pause_campaign`. `finalize_call_log` type hint `billed_minutes: Decimal \| float`. |
| `dialer/cost_guard.py` | `MIN_REMAINING_CREDITS` cannot stay a module constant. `check_campaign_budget(pool, campaign_id, client_id, reserve_amount)` or look up the bot inside. |
| `dialer/concurrent_dialer.py` | Pass **claim-time** `budget_reserved_credits` into `fire_call`, not `MIN_REMAINING_CREDITS`. Test-call path stays 0. |
| `post_call_processor.py` | Remove `math.ceil`. Use snapshots + `billing.compute_call_charge`. `_finalize_call_log_and_settle_budget` billed_minutes type. After settle, pause on overspend. |
| `api/routes/internal.py` | `CreateBotConfigBody` / `BotConfigPatchBody` fields + `Field(ge=0, …)`. Pass through to `create_bot_config` / PATCH SQL. |
| `n8n_webhook.py` | `billed_minutes: int` → `float` (or `Decimal` serialized). Payload already JSON. |
| `db/seed/dev_tenant.sql` | Optional explicit `fixed_start_credits` on seed bots (default is enough; set it so seeds document the model). |

### 8.3 Frontend (must change)

| File | What |
| --- | --- |
| `frontend/src/admin/pages/AdminBotConfigs.jsx` | Map `fixed_start_credits`. Fix INR/HR labels. Edit + create inputs. Preview. `step="0.01"` `min="0"`. |
| `frontend/src/admin/pages/AdminBotConfigs.css` | Only if the two-rate layout needs it. Prefer existing utility classes. |
| `frontend/src/admin/pages/AdminScriptConfigs.jsx` | Deploy modal: setup fee field; POST both prices. |
| `frontend/src/admin/pages/AdminCalls.jsx` | Fractional billed minutes; ₹ two decimals; don’t treat `0.25` as falsy in a bad way (`credits_charged ?` already hides ₹0.00 — show ₹0.00 for billed unanswered). |
| `frontend/src/client/pages/CampaignDetail.jsx` | ₹/min + setup; drop `\|\| 1`. |
| `frontend/src/pages/client/CallLogs/components/MetadataPanel.jsx` | Credits row. |
| `frontend/src/admin/pages/AdminCampaigns.jsx` | No formula change. Creating a campaign still takes a ₹ budget. Optional helper: “At ₹4.00/min + ₹0.60 setup, ₹100 covers about N connected minutes.” Nice-to-have, not required for CI. |
| `frontend/src/admin/pages/AdminClientDetail.jsx` | Same as campaigns if it embeds bot price later; today it does not. No change required unless it displays bot rates. |

Client dashboard totals (`budget_used_credits`) keep working. Short calls will show **smaller** used amounts than ceiling billing — that is intended.

### 8.4 Tests (CI will fail if skipped)

`pytest -x --tb=short` stops on first failure. Touch every assertion that assumes 2-credit reserve or ceiling minutes.

| File | What breaks / what to do |
| --- | --- |
| `tests/test_billing.py` | **Add.** Formula + reservation. No `DATABASE_URL` needed. |
| `tests/test_cost_guard_budget.py` | `credits_per_minute=2.5` + default setup 0.60 → `R = 5.60`, not `2.0`. `test_claim_leads_caps_by_remaining_budget` currently: remaining 2.0, expects 1 lead. After change remaining 2.0 < 5.60 → **0 leads**. Rewrite remaining/budget so `remaining // R == 1` and assert `used == previous + R`. Replace every `RESERVE_CREDITS_PER_LEAD` with `billing.reservation_credits(...)`. |
| `tests/test_settle_unanswered_call.py` | After unanswered settle, assert `credits_charged == setup` when `call_data` has a snapshot; assert `0` when there was no Plivo snapshot / zero reserved (today’s empty `call_data`). Add a third test: snapshot setup 0.60, reserved 5.60, budget_used ends at 0.60. Raw `INSERT INTO bot_configs` still works (new column has DEFAULT). |
| `tests/test_phase2.py` | `budget_reserved_credits=2.0` fixtures: keep as explicit snapshots (old shape) **and** add one with rate+setup snapshots. `finalize_call_log(..., billed_minutes=1)` still valid (`1` → `1.0000`). |
| `tests/test_e2e.py` | Many `create_bot_config(..., 2.0)` positional — **keep working**. Fixture `billed_minutes=2` / `credits_charged=2.5` are inserted values, not computed — still pass. Add one admin test: POST bot with `fixed_start_credits`, PATCH it, GET it back. |
| `tests/test_pg_context_recovery.py` | `create_bot_config` kwargs only — no change unless signature becomes required. Keep `fixed_start_credits` optional. |
| `tests/test_migrate_script_configs.py` | Same as e2e positional create. |
| `tests/test_early_disconnect_post_call.py` | Uses `duration_seconds=12`. If it ever asserts `credits_charged`, update to pro-rata (12/60 × rate + setup). Check assertions when implementing. |
| `tests/test_list_call_logs_projection.py` | Unlikely to break. If `billed_minutes` is selected, type is still numeric. |
| `tests/conftest.py` | Only if tests need a billing helper fixture. Prefer importing `billing`. |

Do **not** leave `RESERVE_CREDITS_PER_LEAD` as an alias for `2.0` — tests would pass while production reserved the wrong amount.

### 8.5 Docs & CLI (drift if skipped; not in pytest)

| File | What |
| --- | --- |
| `guides/aakash_arch.md` | Ceiling-minute examples and `calculate_billing`. |
| `docs/system/09_CALL_LIFECYCLE.md` | `credits_charged = billed_minutes * rate`, reservation(2). |
| `docs/system/10_AI_PIPELINE.md` | “ceiling minutes × credits_per_minute”. |
| `docs/system/05_API_REFERENCE.md` | POST body fields. |
| `docs/system/13_ADMIN_GUIDE.md` | Rate fields. |
| `guides/CLI_GUIDE.md` | “ceil minutes”. |
| `guides/TESTING.md` | What to inspect after a call. |
| `guides/fdesign.md` | Edit Bot Price modal. |
| `scripts/cli.py` | Print setup fee; billed minutes may be `0.25`. |

Out of scope for this change (do not “fix” while touching billing): `guides/aakashvani_v2.md` historical notes, `handoff/*`.

---

## 9. Implementation order (so CI stays green)

1. Add `billing.py` + `tests/test_billing.py` (pure, cannot fail on schema).
2. Alembic `011` + schema SQL. Local: `alembic upgrade head`.
3. `create_bot_config` optional column (tests that only INSERT still pass).
4. Switch processor + unanswered settle + claim/reserve/cost_guard together in one commit-worth of work — **do not land ceil removal without reservation change**, or a 15s call charges ~₹1.48 while only ₹2 was reserved (often OK) but a ₹6/min bot reserves ₹2 and charges ₹9+ (budget lies).
5. Rewrite `test_cost_guard_budget.py` in the same change as (4).
6. API + both admin forms + label bug.
7. Client metadata + campaign rate copy.
8. Docs/CLI.
9. `ruff check .` and `pytest -x`. Watch unused imports (`F401` is **not** ignored; `F841` is).

---

## 10. User-facing behaviour cheat sheet

| Event | Client sees | Admin sees |
| --- | --- | --- |
| Connected 15s @ ₹3.50 + ₹0.60 | Call ₹1.48, campaign used ticks ₹1.48 | Same, plus 0.25 billed minutes |
| Busy / no-answer | Call ₹0.60 | Setup only |
| Dial aborted before Plivo | Nothing | ₹0, reservation returned |
| Test call from script editor | Nothing | Marked test, ₹0 |
| Campaign budget cannot cover next `R_reserve` | Campaign goes paused | Pause reason budget_exhausted |
| One long call overruns campaign budget | Used can exceed allocated; extra ₹ taken from wallet (not below 0); campaign pauses | Ledger note “Campaign overspend” |
| Admin edits rate during a live call | Live call still old rate | Banner: applies to new dials |

---

## 11. Phase 2 (not this work)

When prompts are smaller and cascaded STT+LLM+TTS is measured:

1. Keep token counters as telemetry (already ignored for billing).
2. Add optional ₹/1M input-output fields on `bot_configs`.
3. Wallet and `credits_charged` stay the same shape — only the `compute_call_charge` implementation grows.

Do not mix token fees into this phase.

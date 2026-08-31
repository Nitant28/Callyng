# 11 — Statistics Engine (CRITICAL)

> This is the most safety-critical document. The guiding rule, verified from the
> schema comments and `db/postgres.py`:
>
> **Business statistics live as denormalized counters on the `campaigns` row and
> as explicit billing columns on `call_logs`. The frontend MUST display these
> verbatim and MUST NOT recompute them from raw lead/call lists.**

---

## 1. The single source of truth: campaign counters

`campaigns` carries six integer counters, updated transactionally with every
lead status change:

```176:189:aakashvani/db/schema/001_initial.sql
    -- ── DENORM COUNTERS ───────────────────────────────────────
    -- Updated in same transaction as lead status change. Never COUNT(*).
    total_leads          INTEGER DEFAULT 0,
    pending_leads        INTEGER DEFAULT 0,
    calling_leads        INTEGER DEFAULT 0,
    callback_leads       INTEGER DEFAULT 0,
    completed_leads      INTEGER DEFAULT 0,
    failed_leads         INTEGER DEFAULT 0,
```

Meaning (verified from `reconcile_campaign_counters`, which is the authoritative
definition of each counter):

| Counter | Exact definition |
|---------|------------------|
| `total_leads` | `COUNT(*)` of leads in campaign |
| `pending_leads` | `COUNT(*) FILTER (WHERE status='pending')` |
| `calling_leads` | `COUNT(*) FILTER (WHERE status='calling')` |
| `callback_leads` | `COUNT(*) FILTER (WHERE status='callback_scheduled')` |
| `completed_leads` | `COUNT(*) FILTER (WHERE status='completed')` |
| `failed_leads` | `COUNT(*) FILTER (WHERE status='failed')` |

`status='completed'` means a **terminal outcome** (`Interested` or
`Not_Interested`) was reached. It does **not** mean "Interested only".

### How counters are maintained

Two mechanisms, both in `db/postgres.py`:

1. **Incremental (hot path)** — `increment_campaign_counters(conn, campaign_id,
   from_status, to_status, count)`. Called inside the same transaction as the
   lead update in `process_post_call`. It applies `_COUNTER_DELTAS[(from,to)]`
   (a static delta map of which counters to ±). A special case
   `("__upload__","pending")` bumps `total_leads` and `pending_leads` on insert.
   Dial-claim and release also adjust counters via this path.

2. **Authoritative recompute** — `reconcile_campaign_counters(pool, campaign_id,
   client_id)` runs the full `COUNT(*) FILTER` query and overwrites all six
   counters. Called on:
   - campaign start (`/api/campaigns/{id}/start`, admin start),
   - lead delete, manual status change,
   - release-stuck-calling,
   - admin `/internal/campaigns/{id}/reconcile`.

   This is the self-healing safety net: if incremental drift ever occurs, any of
   those operations snaps the counters back to ground truth.

**Exact SQL** (`reconcile_campaign_counters`):
```1981:1990:aakashvani/db/postgres.py
        SELECT
            COUNT(*)::int AS total_leads,
            COUNT(*) FILTER (WHERE status = 'pending')::int AS pending_leads,
            COUNT(*) FILTER (WHERE status = 'calling')::int AS calling_leads,
            COUNT(*) FILTER (WHERE status = 'callback_scheduled')::int AS callback_leads,
            COUNT(*) FILTER (WHERE status = 'completed')::int AS completed_leads,
            COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_leads
        FROM leads
        WHERE campaign_id = $1 AND client_id = $2
```

> **Frontend rule:** read `pending_leads`, `calling_leads`, `callback_leads`,
> `completed_leads`, `failed_leads`, `total_leads` directly off the campaign
> object returned by `GET /api/campaigns` and `GET /api/campaigns/{id}/stats`.
> Never `COUNT()` the leads list — the leads list is **paginated** (default
> 50/page) and would give wrong totals.

---

## 2. Budget / credit statistics

On the `campaigns` row:
- `budget_credits` — total pre-allocated budget (deducted from
  `clients.balance_credits` at allocation).
- `budget_used_credits` — running accumulator. **Not** purely "spent": it holds
  a mix of *reservations* and *settled charges* during a live campaign.

### Reservation + settlement model (verified)

At dial claim (`claim_leads_for_dialer`): `reserve_campaign_budget` adds
`R = setup + rate × 2 minutes` × lead_count to `budget_used_credits`, and the
reserved amount plus rate/setup snapshots are stored on call_log `call_data`.

At call end (`post_call_processor._finalize_call_log_and_settle_budget` →
`settle_call_budget`):
```1316:1318:aakashvani/db/postgres.py
    reserved = Decimal(str(budget_reserved_credits or 0))
    delta = Decimal(str(credits_charged)) - reserved
    await adjust_budget_used(conn, campaign_id, client_id, delta)
```
i.e. `budget_used_credits += (actual_charge − reservation)`. So after settlement
the net effect on `budget_used_credits` is exactly `credits_charged`.

**Billing math** (`billing.compute_call_charge`):
```python
billed_minutes = duration_seconds / 60
credits_charged = setup + billed_minutes * rate   # 4 dp on the call log
budget_amount = round_half_up(credits_charged, 2) # campaign / wallet
```
- Unanswered calls (busy / no-answer / never picked up) settle at **0 credits**; reservation is fully refunded.
- Never-Plivo / test calls settle at **0 credits** and the reservation is released.

### Remaining budget
`remaining = budget_credits − budget_used_credits`. The dialer cost guard
(`dialer/cost_guard.check_campaign_budget`) pauses when `remaining < R`
for this campaign's bot (`setup + rate × 2 minutes`).

> **Frontend rule:** show `budget_credits`, `budget_used_credits`, and derive
> `remaining = budget_credits − budget_used_credits` (safe arithmetic on
> backend-provided values). Do NOT recompute spend from call logs. Client credit
> **balance** comes only from `GET /api/credits` (`clients.balance_credits`).

---

## 3. Per-call statistics (`call_logs`)

Stored explicitly (never recompute on frontend):
- `duration_seconds`, `billed_minutes`, `credits_charged`, `qualified`
  (`outcome=='Interested'`), `outcome`, `usage_*` tokens.

`billed_minutes = duration_seconds / 60` is computed **once** at finalize and
stored (fractional, e.g. 15s → 0.25). The frontend may *format* duration (e.g. `mm:ss`) but must display
`credits_charged` from the row as ₹ with 2 decimals.

---

## 4. Admin dashboard statistics (`GET /internal/stats`)

Exact SQL (`api/routes/internal.py`):
```626:632:aakashvani/api/routes/internal.py
    total_calls_today = await pool.fetchval("SELECT COUNT(*) FROM call_logs WHERE started_at >= CURRENT_DATE")
    active_campaigns = await pool.fetchval("SELECT COUNT(*) FROM campaigns WHERE status = 'running'")
    total_credits_used_today = await pool.fetchval("SELECT SUM(credits_charged) FROM call_logs WHERE started_at >= CURRENT_DATE")
```

| Stat | Calculation | Edge cases |
|------|-------------|-----------|
| `total_calls_today` | `COUNT(*) call_logs WHERE started_at >= CURRENT_DATE` | Counts ALL call_logs incl. test calls and unanswered. NULL→0. |
| `active_campaigns` | `COUNT(*) campaigns WHERE status='running'` | excludes `pausing`. |
| `total_credits_used_today` | `SUM(credits_charged) WHERE started_at >= CURRENT_DATE` | NULL→0.0 (rows still in_progress have NULL credits_charged → ignored by SUM). |

> **Timezone caveat (IMPORTANT):** `CURRENT_DATE` is evaluated in the **Postgres
> session timezone**, not necessarily IST. `started_at` is `TIMESTAMPTZ`. If the
> DB session TZ is UTC, "today" boundaries are UTC midnight, which is 05:30 IST.
> The compliance/business logic uses IST (9am–9pm) but **this stat does not**.
> Verify the DB `timezone` setting before presenting these as "IST today".
> **Not verified from source:** the DB session timezone.

`GET /internal/health` returns live operational stats: `active_calls`
(`COUNT(*) WHERE in_progress=TRUE`), pool size/idle, `plivo_balance`
(USD from Plivo API, may be `null` on error), `dialer_tasks` (in-process task count).

---

## 5. Statistics shown in the existing frontend (audit)

| Screen | Stat | Source field | Must come from backend? |
|--------|------|--------------|--------------------------|
| Client Dashboard | credit balance | `/api/credits.balance_credits` | YES |
| Client Dashboard | per-campaign progress | campaign counters | YES |
| CampaignDetail | pending/calling/callback/completed/failed | campaign counters | YES |
| CampaignDetail | total leads | `total_leads` | YES |
| CampaignDetail | budget used / remaining | `budget_used_credits`, `budget_credits` | YES (derive remaining by subtraction) |
| CampaignDetail | "live calling" count | `calling_leads` | YES |
| CallLogs | call duration | `duration_seconds` | Backend value; frontend may format mm:ss |
| CallLogs | billed minutes / credits | `billed_minutes`, `credits_charged` | YES |
| CallLogs | outcome / qualified | `outcome`, `qualified` | YES |
| CallLogs | total_count (pagination) | `/api/calls.total_count` | YES |
| Admin Overview | calls today / active campaigns / credits today | `/internal/stats` | YES |
| Admin Diagnostics | active_calls / plivo_balance | `/internal/health` | YES |

---

## 6. MUST come from backend (never compute on frontend)

1. All six campaign counters (`*_leads`).
2. `total_count` for any paginated list (`/api/calls`, leads list).
3. `budget_used_credits`, `budget_credits`, `balance_credits`.
4. `billed_minutes`, `credits_charged`, `qualified`, `outcome`.
5. Admin `/internal/stats` aggregates.
6. `in_progress` (drives polling) — boolean from backend, never inferred.

**Reason:** lists are paginated and filtered; recomputing from a page yields
wrong values. Billing rounds with `ceil` server-side and is stored for audit.

---

## 7. SAFE for frontend to derive (pure formatting/arithmetic on backend values)

- `remaining_budget = budget_credits − budget_used_credits`.
- `progress_pct = (completed_leads + failed_leads) / total_leads` (display only;
  guard division by zero).
- Duration formatting `seconds → mm:ss`.
- Percentage/labels derived from already-correct counters.
- Sorting/grouping of an already-fetched page (cosmetic only).

Anything that requires counting rows the frontend hasn't fully loaded is **not**
safe.

---

## 8. Null / edge-case handling (verified)

- New campaign: all counters default `0`; `budget_used_credits=0`.
- `credits_charged` is NULL while `in_progress=TRUE` (set at finalize). The
  client call list returns it as-is — render NULL as "—" not 0.
- `SUM(credits_charged)` ignores NULLs (Postgres) → `/internal/stats` only sums
  finalized calls.
- Unanswered call: `duration_seconds=0`, `billed_minutes=0`, `credits_charged=0`,
  outcome from Plivo status mapping (`No_Answer`/`Busy`/`Rejected`/`Carrier_Failed`).
- `qualified` strictly equals `outcome=='Interested'` (NOT any engagement).
- Counter drift is corrected on next reconcile (start/reconcile/manual change/delete).

---

## 9. Filtering semantics

- **Client filtering:** every client stats query filters `client_id` (from the
  Bearer token). A client can never see another client's numbers.
- **Campaign filtering:** counters are per-campaign rows; call lists filter by
  `campaign_id`/`client_id`. Admin call list with `client_id=None` returns
  cross-client (and includes test calls).
- **Status mapping for "completed":** terminal outcomes only. Callbacks and
  retries are NOT counted as completed until they reach a terminal state or
  exhaust attempts (→ failed).
- **Test calls:** excluded from client `list_call_logs`/`get_call_log` via
  `call_data->>'is_test_call' != 'true'`; included for admin.

# Aakashvani — Call-Outcome & Lead-State Optimization Spec

**Audience:** the engineer/agent implementing the changes.
**Status:** All workstreams (A–H) complete.
**Author intent:** automate cold/warm calling end-to-end with (1) correct assessment of every call, (2) one authoritative lead state machine, (3) normalized status cards, (4) per-bot post-call analysis, (5) no production bottlenecks, (6) **complete removal of DNC**, and (7) real code cleanup.

> This document is the single source of truth for this work. Each workstream lists **exact files, line anchors, the change, and acceptance criteria.** Line numbers are anchors at time of writing — if they drift, match on the quoted code instead.

---

## 0. How to use this document

Implement in the order given in **§10 Sequencing**. Each workstream (A–G) is independently reviewable but some depend on others (noted inline). After every workstream, run the verification in **§11** before moving on.

**Hard rules:**
- Do **not** introduce new lead statuses beyond the canonical five (§1).
- Do **not** touch any of the false positives listed in **§12** (e.g. "Do not call `end_call`" in bot scripts — that is unrelated to DNC).
- Every lead-status mutation must go through the single resolver (Workstream A). No new ad-hoc `UPDATE leads SET status=...` outside the sanctioned functions.
- Keep multi-tenant safety: every `leads`/`call_logs` query filters by `client_id`.

---

## 1. Canonical model (the contract everything conforms to)

### 1.1 Lead statuses (exactly five — DNC removed)

| Status | Meaning | Card color |
|---|---|---|
| `pending` | Awaiting **first dial only** (`attempts = 0`, or manually reset while paused). | 🟡 Yellow |
| `calling` | Claimed by dialer or in a live call. | 🔵 Blue |
| `callback_scheduled` | **Tried, inconclusive** — shows outcome + when we call back (`next_attempt_at` / `scheduled_callback_at`). | 🟣 Purple |
| `completed` | Reached a terminal resolution (see terminal outcomes). | 🟢 Green |
| `failed` | Exhausted/abandoned with no resolution (see failure outcomes). | 🔴 Red |

There is **no `dnc` status** after this work. A caller opt-out ("remove my number") is treated as a **terminal `completed`** lead with outcome `Not_Interested` (see §3.4 for rationale and the compliance note).

### 1.2 Canonical outcome vocabulary (closed set)

Outcomes are grouped into three buckets that drive the state machine. Buckets are configurable per bot via `script_configs.outcome_terminal/outcome_retry/outcome_callback` (already exists); the defaults live in `script_runtime.py:68-70`.

**Terminal → `completed`:**
- `Interested`
- `Not_Interested` (includes former opt-out/DNC signal)

**Callback → `callback_scheduled`:**
- `Callback_Requested`
- `Early_Disconnect` (short callee hangup, no intent — see post-call policy)

**Retry-bucket outcomes → `callback_scheduled` status** (outcome label preserved on card; not `pending`):
- `Busy`
- `No_Answer`
- `Rejected`
- `Carrier_Failed`
- `Wrong_Requirement`
- `Unknown`

**Failure (terminal `failed`, set by system, never by LLM):**
- `Max_Attempts_Reached` — attempts ≥ max_attempts with no resolution.
- `Campaign_Cancelled` — campaign was cancelled.

> Today the code collapses all non-answers into the literal string `'Unanswered'` (`db/postgres.py:63, 1856, 2717, 2763, 2804`, etc.) and uses `'Campaign cancelled'` (`db/postgres.py:2123, 2133`). Workstream B replaces these with the vocabulary above. **No code may write an outcome string outside this set.**

### 1.3 Status × outcome matrix (what the UI shows)

| Status | Allowed outcomes |
|---|---|
| `pending` | `NULL` only (never called yet, or manual reset with `attempts = 0`) |
| `calling` | `NULL` / previous attempt's outcome |
| `callback_scheduled` | `Callback_Requested`, `Early_Disconnect`, `Busy`, `No_Answer`, `Rejected`, `Carrier_Failed`, `Wrong_Requirement`, `Unknown` |
| `completed` | `Interested`, `Not_Interested` |
| `failed` | `Max_Attempts_Reached`, `Campaign_Cancelled` |

**Manual → `pending` while paused:** resets `attempts = 0`, clears `outcome` and `extraction` (fresh lead).

---

## 2. Workstream A — Unify the post-call state machine (highest priority)

### 2.1 Problem

Lead status is currently mutated post-call in **five** places with **divergent retry/outcome logic**:

| # | Path | Entry point | Retry delay it uses | Outcome it writes |
|---|---|---|---|---|
| A | Normal pipeline end | `call_transcript.py:631` → `process_post_call` (`post_call_processor.py:297`) | `campaign.retry_delay_minutes`, **but capped to NOW()+1min if call <90s** (`post_call_processor.py:402-410`) | LLM outcome |
| B | Abnormal WS disconnect | `plivo_hangup.py:105-116` → `recover_abandoned_session` (`post_call_processor.py:190`) → `process_post_call` | same as A | LLM / `Unknown` |
| C | Unanswered (busy/no-answer/reject/cancel/failed) | `plivo_hangup.py:90` → `settle_unanswered_call` (`db/postgres.py:2733`) | **hardcoded 120** — campaign value never passed | `'Unanswered'` |
| D | Orphaned dial (no `call_sid`) | `finalize_orphaned_in_progress_call_logs` (`db/postgres.py:1922`) → `settle_unanswered_call(retry_delay_minutes=0)` | **0 (immediate)** | `'Unanswered'` |
| E | Stuck/exhausted housekeeping | `release_stuck_calling_leads` (`db/postgres.py:1844-1886`), `terminalize_exhausted_leads` (`db/postgres.py:2691`) | `NOW()` | `'Unanswered'` / raw |

Resulting defects:
- **Campaign `retry_delay_minutes` is ignored for every unanswered call** (path C uses the function default `120`).
- The same logical event (a non-answer) reschedules at **0, 1, or 120 minutes** depending on which path fires.
- Outcomes are not normalized (everything becomes `'Unanswered'`).

### 2.2 Target design

There is exactly **one** pure decision function and **one** pure retry helper. Every path calls them.

1. **`resolve_post_call_transition`** (`post_call_processor.py:95-140`) stays the authority for **answered** calls (LLM outcome present). It is already pure — keep it pure.
2. **`resolve_lead_retry_or_failed`** (`db/postgres.py:23-38`) is the authority for **non-answered/abandoned** calls. It is already pure. Extend it to also return the normalized outcome string:

   ```python
   def resolve_lead_retry_or_failed(
       attempts, max_attempts, retry_delay_minutes, *,
       base_outcome="Unknown", now=None,
   ) -> tuple[str, datetime | None, str]:
       """Return (status, next_attempt_at, outcome) after an inconclusive attempt."""
       ts = now or datetime.now(timezone.utc)
       if attempts >= max_attempts:
           return "failed", None, "Max_Attempts_Reached"
       return "callback_scheduled", ts + timedelta(minutes=retry_delay_minutes), base_outcome
   ```

3. **Fix the retry-delay plumbing** so the campaign value flows to every path:
   - `plivo_hangup.py:90`: load the campaign's `retry_delay_minutes` (the `call_log` has `campaign_id`+`client_id`; fetch via `pg_db.get_campaign`) and pass it: `settle_unanswered_call(pool, call_log, retry_delay_minutes=<campaign value>, base_outcome=<from CallStatus, see Workstream B>)`.
   - `settle_unanswered_call` (`db/postgres.py:2733`): change signature to require `retry_delay_minutes` (no `=120` default) and add `base_outcome: str`. Internally call the extended `resolve_lead_retry_or_failed(...)` instead of the inline logic at lines 2792-2818, and write the returned outcome instead of the hardcoded `'Unanswered'`.
   - `finalize_orphaned_in_progress_call_logs` (`db/postgres.py:1922`): keep `retry_delay_minutes=0` **only** here (orphaned dials never reached the callee, immediate retry is correct), but pass `base_outcome="Carrier_Failed"`.
   - `release_stuck_calling_leads` (`db/postgres.py:1844-1886`) and `terminalize_exhausted_leads` (`db/postgres.py:2691`): replace the literal `'Unanswered'` / inline failed-vs-pending logic with `resolve_lead_retry_or_failed(...)`. For exhausted leads the result is `("failed", None, "Max_Attempts_Reached")`.

4. **The `<90s → 1-min cap` heuristic** (`post_call_processor.py:402-410`): keep it (it prevents a long retry delay after a near-instant drop) but extract the magic numbers `90` and `1` into module-level constants `_SHORT_CALL_SECONDS = 90` and `_SHORT_CALL_RETRY_CAP_MIN = 1` with a one-line comment explaining intent. No behavior change.

### 2.3 Acceptance criteria
- Grep for the literal `'Unanswered'` returns **zero** matches in `db/postgres.py`.
- A busy call on a campaign with `retry_delay_minutes=10` reschedules at ~10 min, not 120.
- All five paths produce outcomes only from §1.2.
- `tests/test_post_call_engine.py` still passes; add cases for `resolve_lead_retry_or_failed` returning `Max_Attempts_Reached`.

---

## 3. Workstream B — Outcome normalization & Plivo CallStatus mapping

### 3.1 Problem
`plivo_hangup.py:86-87` already has the Plivo `CallStatus` in hand but discards the distinction, sending everything to `settle_unanswered_call` which writes `'Unanswered'`. We lose busy vs no-answer vs rejected vs carrier-failure.

### 3.2 Add a mapping helper
Create a small pure function (put it in `db/postgres.py` near `_normalize_hangup_source`, or a new `call_outcomes.py` module — prefer a new module `call_outcomes.py` to keep `postgres.py` from growing):

```python
# call_outcomes.py
"""Canonical call-outcome vocabulary and Plivo CallStatus mapping."""

TERMINAL = frozenset({"Interested", "Not_Interested"})
CALLBACK = frozenset({"Callback_Requested"})
RETRY = frozenset({"Busy", "No_Answer", "Rejected", "Carrier_Failed",
                   "Wrong_Requirement", "Unknown"})
FAILURE = frozenset({"Max_Attempts_Reached", "Campaign_Cancelled"})

_PLIVO_STATUS_TO_OUTCOME = {
    "busy": "Busy",
    "no-answer": "No_Answer",
    "cancel": "No_Answer",
    "reject": "Rejected",
    "failed": "Carrier_Failed",
}

def outcome_from_plivo_status(call_status: str) -> str:
    return _PLIVO_STATUS_TO_OUTCOME.get((call_status or "").strip().lower(), "Unknown")
```

### 3.3 Wire it
- `plivo_hangup.py:86-92`: compute `base_outcome = outcome_from_plivo_status(call_status)` and pass it into `settle_unanswered_call` (per Workstream A.3).
- `db/postgres.py` `_COUNTER_DELTAS`, `finalize_stale_in_progress_call_logs` default outcome (`db/postgres.py:165, 198`): replace `'Unknown'` default is fine (it is in the retry set). Replace any `'Unanswered'` with the helper or `Unknown`.

### 3.4 Opt-out (former DNC) handling — explicit decision
Caller opt-out is **terminal**. Since DNC is being removed entirely (Workstream C), an opt-out maps to outcome `Not_Interested` → status `completed`. Rationale: it is a definitive negative resolution; folding it into `Not_Interested` keeps the closed vocabulary and avoids a back-door "dnc-by-another-name."

**Compliance note for the author/owner:** removing DNC means the system no longer maintains a do-not-call signal at the data layer. If a regulator later requires suppression lists, that becomes an upstream (CRM/n8n) responsibility. This is an accepted trade-off per the explicit instruction to remove DNC completely. The bot's extraction prompt/schema should emit `Not_Interested` (not `dnc`) for opt-outs — see Workstream C.7.

### 3.5 Acceptance criteria
- A busy hangup yields lead outcome `Busy`; no-answer yields `No_Answer`; carrier failure yields `Carrier_Failed`.
- No code writes an outcome outside §1.2.

---

## 4. Workstream C — Complete removal of DNC (no mention anywhere in the repo)

DNC must be **fully removed**: status value, counter column, counter deltas, state-machine branch, routes, frontend, tests, schema, env, and docs. Below is the complete inventory. **Do every item.**

### 4.1 Database schema — source SQL
File: `db/schema/001_initial.sql`
- **Line 189-190:** delete the `dnc_leads INTEGER DEFAULT 0,` column and its comment from `campaigns`.
- **Lines 210-218 (status-machine comment block):** delete the `→ dnc` line(s).
- **Lines 253-254:** change the `leads.status` CHECK to:
  ```sql
  status VARCHAR(50) DEFAULT 'pending'
      CHECK (status IN ('pending', 'calling', 'completed', 'failed', 'callback_scheduled')),
  ```
- Search the file for any other `dnc` comment and remove.

### 4.2 Database — new Alembic migration (destructive; order matters)
Create `alembic/versions/007_remove_dnc.py` (follow the pattern of existing versioned files). The current head is `006_script_configs`, so set `revision = "007_remove_dnc"` and `down_revision = "006_script_configs"`.

Migration `upgrade()` must, **in this order**:
1. Re-home existing data:
   ```sql
   UPDATE leads SET status = 'completed', outcome = 'Not_Interested'
   WHERE status = 'dnc';
   ```
2. Recompute campaign counters so `completed_leads` absorbs the migrated rows and `dnc_leads` is zeroed (or rely on a follow-up `reconcile_campaign_counters` run — but since that function is changing in §4.3, do it inline in SQL here):
   ```sql
   UPDATE campaigns c SET
     completed_leads = sub.completed,
     dnc_leads = 0
   FROM (
     SELECT campaign_id, COUNT(*) FILTER (WHERE status='completed')::int AS completed
     FROM leads GROUP BY campaign_id
   ) sub
   WHERE sub.campaign_id = c.id;
   ```
3. Drop the old CHECK constraint and add the new one. The inline constraint is auto-named `leads_status_check`:
   ```sql
   ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
   ALTER TABLE leads ADD CONSTRAINT leads_status_check
     CHECK (status IN ('pending','calling','completed','failed','callback_scheduled'));
   ```
4. Drop the counter column:
   ```sql
   ALTER TABLE campaigns DROP COLUMN IF EXISTS dnc_leads;
   ```

`downgrade()` may be a no-op (consistent with `001_initial.py:23-24`), or re-add the column/constraint if you want symmetry. No-op is acceptable here.

> **Safety:** this migration is destructive (drops a column). Confirm a DB backup/snapshot exists before running in any shared environment. See §11.4.

### 4.3 `db/postgres.py`
- **Lines 269, 274:** delete the two `_COUNTER_DELTAS` entries whose target is `dnc` (`("calling","dnc")` and `("callback_scheduled","dnc")`).
- **Line 286:** remove `"dnc_leads"` from `_ALLOWED_COUNTER_COLS`.
- **`bulk_insert_leads` (lines 1568-1577):** remove the `if lead_status == "dnc": ... else:` branch; always take the `increment_campaign_counters(..., to_status="pending")` path. (No uploader produces `status='dnc'` anymore after §4.6/§4.7.)
- **`reconcile_campaign_counters` (lines 1978, 1992, 2003, 2012):** remove the `dnc_leads` SELECT filter, the dict key, and the UPDATE assignment + bound arg. Re-number the `$n` placeholders after removing `dnc_leads = $7` (shift `campaign_id`/`client_id` accordingly).
- **`insert_single_lead` (lines 2335-2344):** remove the `if lead_status == "dnc": ...` branch; always take the pending counter path.
- Verify no remaining `dnc` substring in the file.

### 4.4 `post_call_processor.py`
- **Lines 64-65:** delete the `if outcome.casefold() == "dnc": return "dnc", ...` branch in `_lead_transition`.
- **Line 110:** change `terminal_outcome = _matches_bucket(outcome, terminal_set) or outcome.casefold() == "dnc"` to `terminal_outcome = _matches_bucket(outcome, terminal_set)`.

### 4.5 `api/routes/leads.py`
- **`_MANUAL_TRANSITIONS` (lines 21-27):** remove `"dnc"` from every value set and delete the `"dnc": {...}` key entirely. Result:
  ```python
  _MANUAL_TRANSITIONS: dict[str, set[str]] = {
      "pending": {"failed", "callback_scheduled", "completed"},
      "callback_scheduled": {"pending", "failed", "completed"},
      "failed": {"pending", "completed"},
      "completed": {"pending"},
  }
  ```

### 4.6 `scripts/cli.py`
- **Line 80:** remove the `"dnc": _RED,` entry from the status color map.
- **Line 405:** remove the `_kv("DNC", camp.get("dnc_leads"), ...)` line.
- **Line 971:** remove `"dnc"` from the outcome/status validation set.

### 4.7 `fix_leads.py`
This is a root-level ad-hoc script slated for deletion in Workstream G. **Delete the file** (covers lines 25-26 references). If for some reason it must stay, remove `"DNC"` and `"dnc"` from the terminal set there.

### 4.8 Frontend
- `frontend/src/pages/client/CampaignDetail.jsx`
  - **Lines 1008-1014:** delete the `else if (lead.status === 'dnc') { ... 'Do Not Call' ... }` badge branch.
  - **Lines 1359-1364 (`_MANUAL_TRANSITIONS` mirror):** remove `'dnc'` from every array and delete the `dnc: [...]` key.
  - **Line ~1370:** remove the `{ value: 'dnc', label: 'DNC' }` option from the status `<select>`.
  - Search the file for any `dnc_leads` counter card and remove it (and re-balance the grid layout if needed).
- `frontend/src/pages/admin/AdminClientDetail.jsx` **line 829:** remove the `DNC: {selectedCampaign.dnc_leads}` row.
- `frontend/src/pages/admin/AdminCampaigns.jsx` **line 384:** remove the `DNC: {selectedCampaign.dnc_leads}` row.
- Grep `frontend/src` for `dnc` / `DNC` / `dnc_leads` and remove any stragglers (none expected beyond the above).

### 4.9 Tests
- `tests/test_client_api_edge.py` **lines 107-108 and 153-154:** these assert `status: "dnc"` transitions. Rewrite them to use a still-valid transition (e.g. `pending → failed` or `pending → completed`) so coverage of the manual-transition endpoint is preserved without DNC. Do **not** simply delete the assertions — keep equivalent coverage.

### 4.10 Env & config
- `env.example` **lines 79-80:** remove the `INTERNAL_DND_NUMBERS` comment lines.

### 4.11 Documentation (repo-wide "no mention" requirement)
Remove or rewrite every DNC/DND reference in docs. Files and anchors:
- `ROADMAP.md`: 396, 401, 410, 461, 583.
- `guides/intro.md`: 243, 256, 324, 344, 505, 767, 776, 1098, 1207.
- `guides/aakash_arch.md`: 255-256, 281, 320, 978, 988, 999, 1004-1012, 1052-1053, 1431, 1710.
- `guides/plan.md`: 171.
- `guides/CLI_GUIDE.md`: 218-219, 237-240.
- `guides/TESTING.md`: 162.
- `guides/aakashvani_v2.md`: 96, 119.
- `guides/tasks.md`: 140, 145, 286, 293-296.
- `guides/bugs2.md`: 42, 103-113, 209, 235, 242, 276 (these are historical bug notes; rewrite to drop DNC mentions, or annotate the file as historical — owner's call, but the instruction is "no mention," so prefer scrubbing).
- `handoff/context_2026-06-07.md`: 32, 38, 244.
When scrubbing docs: where a status list appears (e.g. `total/pending/calling/callback/completed/failed/dnc`), drop `dnc`. Where a state-machine diagram shows a `dnc` node/edge, delete that node/edge. Where the doc explains the DNC feature (e.g. `aakash_arch.md:1004-1012`), delete the section.

### 4.12 Acceptance criteria
- `rg -i '\bdnc\b|dnc_leads|INTERNAL_DND|do not call list|do-not-call' .` returns **only** the §12 false positives (bot-script `end_call` instructions, the package-lock hash). Nothing functional.
- App boots, migrations run clean, campaign detail renders with five status cards, manual-status endpoint rejects `dnc` with a 409 (since it's no longer in the transition map / CHECK).

---

## 5. Workstream D — Move domain heuristics out of the shared extractor into per-bot config [NEXT]

> **Status (2026-06-27):** Completed. Domain heuristics are now declarative rules. See §15.10.

### 5.1 Problem
`post_call_extract.py` hardcodes **real-estate, Pune-specific** logic into the generic extractor, contradicting the per-bot analysis goal:
- BHK regex `_BHK_RE` (line 28), location markers Baner/Kondhwa/Katraj (lines 33-44, 190-205), Hindi callback regexes (lines 49-58), and the whole `reconcile_extraction_with_assistant_turns` (lines 218-299) and the legacy branch of `normalize_post_call_extraction` (lines 414-453).

### 5.2 Target
The mechanism to do this per-bot **already exists**: `script_configs.normalization_rules` (declarative rules consumed by `apply_normalization_rules`, `post_call_extract.py:339-401`) and the frozen `post_call_snapshot` (`script_runtime.py:236-259`). 

- Express the real-estate reconciliation as declarative `normalization_rules` on the relevant `script_config` rows (the Pyramid bots). Use `script_module_export.py` / existing config tooling as the migration vehicle.
- Make `normalize_post_call_extraction` (`post_call_extract.py:404-453`) **config-driven only**: when `normalization_rules` are present, apply them; when absent, do the minimal generic normalization (the `site_visit_agreed`/`callback_time` inference at lines 414-448 is generic enough to keep as a fallback, but the BHK/location/Hindi-specific bits must move out).
- `reconcile_extraction_with_assistant_turns` (lines 218-299) is entirely real-estate/Hindi specific. Move its behavior into rules, then delete the function and its call site (`post_call_extract.py:453` and the import in `post_call_processor.py:252,265-269`).

> This workstream is **lower priority** than A/B/C and can ship separately. It is included because it is the real "bot-wise analysis" gap (the infra exists; the hardcoding defeats it). If time-boxed, do at least: stop calling `reconcile_extraction_with_assistant_turns` for bots that define `normalization_rules`, so configured bots are not silently overridden by Pune logic.

### 5.3 Acceptance (§5.3): non-real-estate extraction never touched by BHK/Baner/Hindi logic; Pyramid bots pass existing reconcile tests via rules.

---

## 6. Workstream E — Performance / bottleneck elimination [DONE]

### 6.1 The real hot-path cost
`claim_leads_for_dialer` (`db/postgres.py:1639-1668`) and `diagnose_claim_blockers` (`db/postgres.py:82-142`) run correlated `NOT EXISTS` subqueries against `call_logs` keyed on `lead_id` with time predicates on `in_progress` and `ended_at`. These are served only by `idx_call_logs_lead (lead_id)` (`db/schema/001_initial.sql:510-511`). The leads side is already well covered by the partial `idx_leads_dialer` (`001_initial.sql:494-496`).

### 6.2 Add indexes (in the same migration as §4.2 or a sibling `008_calllog_indexes.py`)
```sql
-- Serves the "is there a live call for this lead?" NOT EXISTS
CREATE INDEX IF NOT EXISTS idx_call_logs_lead_live
    ON call_logs (lead_id)
    WHERE in_progress = TRUE;

-- Serves the "did a call for this lead end recently?" NOT EXISTS (wrap-up grace)
CREATE INDEX IF NOT EXISTS idx_call_logs_lead_ended
    ON call_logs (lead_id, ended_at DESC)
    WHERE ended_at IS NOT NULL;
```
Also add these to `db/schema/001_initial.sql` (after line 526) so a fresh DB matches.

### 6.3 Reduce per-tick churn in the dialer loop
- `concurrent_dialer.py:499` calls `release_stuck_calling_leads` (a heavy multi-CTE transaction in `db/postgres.py:1691-1891`) **inside the claim-failure branch on every tick**. Gate it behind a cooldown (e.g. run at most once per 30s per campaign, tracked in a module dict keyed by `_campaign_key`), since the start-of-loop reconcile (`concurrent_dialer.py:386-409`) already handles the cold-start case.
- `finalize_stale_in_progress_call_logs` / `finalize_orphaned_in_progress_call_logs` invoked from the same branch (`db/postgres.py:1702-1703` via `release_stuck...`) inherit the same cooldown.

### 6.4 Acceptance criteria
- `EXPLAIN ANALYZE` on the `claim_leads_for_dialer` inner SELECT uses the new partial indexes (no seq scan on `call_logs`).
- Dialer idle CPU/DB load drops measurably when a campaign is waiting on future retries (no per-5s heavy CTE).

---

## 7. Workstream F — Frontend status cards (five-card model) [COMPLETED]

### 7.1 Target
Cards/counters reflect exactly the five statuses (§1.1). DNC card/counter removed in Workstream C.8.

- `frontend/src/pages/client/CampaignDetail.jsx`: the badge `if/else` chain (around lines 953-1033) already branches on `completed/failed/calling/callback_scheduled/pending` — keep those, and ensure the **outcome sub-labels** use the new vocabulary (§1.2): map `Max_Attempts_Reached`, `No_Answer`, `Busy`, `Rejected`, `Carrier_Failed`, `Campaign_Cancelled`, `Wrong_Requirement`, `Unknown` to friendly labels. The current code keys off `'Unanswered'` (lines 983-1031) — update those string comparisons to the new outcomes.
- Counter cards: there are `completed`/`failed` progress bars (lines 663-684). Add **Pending**, **Calling**, **Callback Scheduled** counters if not already shown so all five are visible and sum to `total_leads`.
- Admin views (`AdminCampaigns.jsx`, `AdminClientDetail.jsx`): after removing the DNC row (§4.8), verify the counters still sum correctly in the displayed breakdown.

### 7.2 Acceptance criteria
- Five cards render; counts sum to `total_leads`.
- Friendly outcome labels show for each new outcome string; no UI references `'Unanswered'` or DNC.

---

## 8. Workstream G — Repo cleanup

### 8.1 Delete root-level ad-hoc scripts (dev scratch — not part of the app)
Verify each is not imported anywhere (`rg "import <name>"`) before deleting:
`fix_db.py`, `fix_leads.py`, `fix_modal_final.py`, `fix_modal_ui.py`, `patch.py`, `patch_modal.py`, `patch_modal_ui.py`, `insert_bugs.py`, `append_bugs.py`, `query.py`, `query_db.py`, `query_json.py`, `get_recent_test_calls.py`, `clear_db.py`, `plivo_record_test.py`, `diff.txt`.

Root-level loose tests (`test_api.py`, `test_api2.py`, `test_api3.py`, `test_db.py`, `test_db_2.py`, `test_db_3.py`, `test_leads.py`, `test_logs.py`, `test_stats.py`, `test_bug.py`): either move valuable ones into `tests/` (rename to avoid pytest collisions) or delete the throwaways. **Do not** delete anything under `tests/`.

### 8.2 Acceptance criteria
- `git status` shows only intended deletions; `just test` / `pytest` still green.
- No application module imports a deleted file.

---

## 9. (Reference) Post-call data flow after this work

```
Plivo hangup ──► plivo_hangup.handle_plivo_hangup  (returns 200 immediately)
                   │
   CallStatus answered? ──no──► settle_unanswered_call(retry_delay=campaign, base_outcome=outcome_from_plivo_status)
                   │                         └─► resolve_lead_retry_or_failed ──► pending|failed + normalized outcome
                   │
                  yes (callee hung up, still in_progress)
                   └─► spawn_background_task(_hangup_recover) ──► recover_abandoned_session ──► process_post_call

Normal WS end ──► call_transcript.attach_pipeline_finalize
                   └─► spawn_background_task(_extract_patch_and_webhook)  (Groq off the hot path)
                         └─► process_post_call
                               └─► resolve_post_call_transition (answered, LLM outcome)
                               └─► resolve_lead_retry_or_failed (retry/exhaust)

Dialer housekeeping ──► terminalize_exhausted_leads / release_stuck_calling_leads
                          └─► resolve_lead_retry_or_failed (single shared helper)
```
One resolver for answered calls, one shared helper for non-answers; every path normalized.

---

## 10. Sequencing

1. **Workstream C (DNC removal)** first — it changes the schema, status set, counters, and tests that everything else builds on. Land the migration + code + frontend + tests together.
2. **Workstream A (unify state machine)** — depends on the DNC-free status set.
3. **Workstream B (outcome vocabulary + CallStatus)** — co-develop with A (B supplies the `base_outcome` values A consumes). Can be one PR with A.
4. **Workstream E (indexes + dialer cooldown)** — independent; can land any time after C's migration exists (add indexes in the same or sibling migration).
5. **Workstream F (frontend cards/labels)** — after A/B define the final outcome strings.
6. **Workstream D (extractor de-hardcoding)** — last; lower risk to defer; gate behind config so configured bots aren't overridden.
7. **Workstream G (cleanup)** — any time; keep it a separate PR so deletions don't obscure logic diffs.
8. **Workstream H (admin guide + bucket editors)** — after A/B/C settle the canonical outcome vocabulary, since the guide copy quotes it. Independent of D.

---

## 11. Verification checklist (run after each workstream)

### 11.1 Static
- `rg -i '\bdnc\b|dnc_leads|INTERNAL_DND'` → only §12 false positives.
- `rg "'Unanswered'|\"Unanswered\""` → zero in `db/postgres.py` and `frontend/src`.
- `ReadLints` / linter clean on every edited file.

### 11.2 Unit/integration tests
- `pytest tests/test_post_call_engine.py tests/test_post_call_snapshot.py tests/test_client_api_edge.py` green.
- Add: a test that `settle_unanswered_call` honors a passed `retry_delay_minutes` and writes the `base_outcome`.
- Add: `resolve_lead_retry_or_failed` returns `Max_Attempts_Reached` at the boundary.

### 11.3 Manual smoke (dev DB)
- Upload leads, run a campaign, force a busy + a no-answer + an answered Interested + an answered opt-out; confirm statuses land as pending(Busy/No_Answer) → eventually failed(Max_Attempts_Reached), completed(Interested), completed(Not_Interested).
- Confirm campaign counters sum to `total_leads` with no `dnc_leads`.

### 11.4 Migration safety
- Take a DB snapshot/backup before running `007_remove_dnc`.
- Run `alembic upgrade head` on a copy first; verify `leads_status_check` updated and `campaigns.dnc_leads` dropped, and that previously-`dnc` leads are now `completed`/`Not_Interested`.

---

## 12. Do NOT touch (false positives)

These match `dnc`/`DND`/"do not call" textually but are **unrelated** to the DNC feature:
- **Bot script instructions** that say *"Do not call `end_call` mid-conversation"* / *"Do NOT call `end_call`..."* in `sts_scripts/pyramid_bilingual.py`, `sts_scripts/bot_template.py`, `frontend/src/components/shared/ScriptingGuideModal.jsx`, `call_limits.py:51`. These are LLM tool-use instructions about the `end_call` function — leave them exactly as-is.
- **Dependency hashes** containing the substring `DND`/`cDNd` in `package-lock.json` and `frontend/package-lock.json`. Never edit lockfile integrity hashes.
- `compliance.py` and `n8n_webhook.py` — already DND-free; no code changes needed there for DNC removal (verify, then leave).

---

## 13. Out of scope (explicitly not part of this work)
- Re-architecting the dialer concurrency/locking model.
- Changing billing/credit settlement logic.
- Adding a suppression/consent system to replace DNC (owner decision; see §3.4 compliance note).
- **Per-bot post-call LLM model selection** — explicitly NOT wanted. All bots share the global `POST_CALL_MODEL`. Bot-wise customization is done purely through schema + rules + outcome buckets (Workstream D and H). Do not add model-choice fields to `script_configs` or the admin UI.

---

## 14. Workstream H — Admin frontend guide for script / post-call input [COMPLETED]

> **Goal:** make the admin **Script Configs** screen self-documenting so a non-author admin can write a *good* `extraction_schema`, `normalization_rules`, and outcome buckets for a bot — and understand how those drive the lead status cards. This is the user-facing half of "bot-wise post-call analysis." No model choice is involved.

### 14.1 Two gaps to fix in the UI

1. **Missing editors.** The post-call tab (`frontend/src/pages/admin/AdminScriptConfigs.jsx:608-623`) exposes only three JSON editors: **Extraction Schema**, **Normalization Rules**, **Outcome Event Map**. It does **not** expose `outcome_terminal`, `outcome_retry`, `outcome_callback`, even though the backend validates them (`api/script_config_validation.py:219-275`) and they decide whether a lead becomes `completed` / `pending` / `callback_scheduled`. They are held in form state (`AdminScriptConfigs.jsx:116-118, 143-145, 162-164`) but never rendered, so admins silently fall back to defaults and cannot tune outcomes per bot.
   - **Build a Visual Drag-and-Drop Outcome Mapping UI.** This single partition widget replaces the need for three separate text editors. It dynamically pulls tags from the `intent_status` schema array as draggable pills and provides three target drop-zones (Terminal, Callback, Retry).
   - **JSON Escape Hatch.** Keep a "view/edit raw JSON" toggle (collapsed by default) for power users who want to copy/paste configs across bots. Drag-and-drop should be the default, but raw JSON is the advanced alternative.
   - **Move, Not Copy Semantics.** A pill must leave its old zone when dropped into a new one. This makes overlapping/duplicate placement physically impossible.
   - **Schema Desync Reconciliation.** If the Extraction Schema is edited *after* mapping, the drag board must reconcile on every change. It must surface "orphaned" pills (pills sitting in a zone but no longer in the schema) visibly as "stale — remove me", and surface newly-added schema tags back into the unmapped source panel. Do not silently drop them.
   - **Empty / Summary Mode Handling.** If `intent_status` is missing/empty, show an empty state ("Define an intent_status enum in the Extraction Schema first"). If the schema `mode` is `"summary"`, hide or disable the buckets entirely, as summary mode doesn't use buckets.
   - **Explicit Empty vs Defaults.** The UI must make it explicit whether an untouched mapping saves as `null` (falling back to backend defaults in `script_runtime.py`) or explicitly saves as an empty array `[]`.
2. **No guidance.** None of the post-call editors have help text. Add the inline guidance from §14.3 and a dedicated "Post-Call Analysis" section in the existing in-app guide modal (`frontend/src/components/shared/ScriptingGuideModal.jsx`), which today only documents conversation scripting.

### 14.2 Where the guidance lives (implementation targets)

- **Inline help (primary):** a short helper line + an expandable "How to write this" panel under each editor in the post-call tab of `AdminScriptConfigs.jsx`. Use the copy in §14.3 verbatim (trim as needed for layout).
- **Full reference (secondary):** add a **"Post-Call Analysis"** tab/section to `ScriptingGuideModal.jsx` containing §14.3 + §14.4 + §14.5 in full, plus the worked example in §14.6.
- **Validation feedback:** surface backend validation errors (from `validate_outcome_mapping` / `validate_extraction_schema`) inline near the relevant editor instead of a generic toast, so the admin sees *which* `intent_status` value is unmapped. The error strings are already specific (e.g. `intent_status values not mapped to any outcome bucket: [...]`).

### 14.3 Guidance copy — Extraction Schema

> Render this as the help content for the **Extraction Schema** editor.

**What it is:** the instruction set the post-call AI uses to read each call transcript and produce one JSON object. It defines *what facts you want extracted* and *the list of possible call outcomes*.

**Required shape:**
```json
{
  "mode": "fields",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": ["Interested", "Not_Interested", "Callback_Requested", "Busy", "Wrong_Requirement", "Unknown"],
      "required": true,
      "description": "The single outcome that best describes this call."
    },
    {
      "key": "callback_time",
      "type": "datetime",
      "required": false,
      "description": "If the caller asked to be called back at a specific time, the ISO 8601 time, else NULL."
    },
    {
      "key": "caller_notes",
      "type": "string",
      "required": false,
      "description": "Any other useful fact in one short sentence, or NULL."
    }
  ],
  "extraction_rules": "Infer only what the transcript supports. Reply with ONE JSON object matching the field keys."
}
```

**Rules the system enforces (you will get an error otherwise):**
- `mode` must be `"fields"`, `"summary"`, or `"both"`.
- For `fields`/`both`, there must be a non-empty `fields` list, and **one field must have `key: "intent_status"` with a `type: "enum"` and a non-empty `values` list.** This `intent_status` list is the master list of outcomes for the bot.
- Every field needs a unique string `key`. Allowed `type` values: `string`, `enum`, `boolean`, `datetime`. `enum` fields need non-empty `values`.
- `summary` mode requires a `summary_prompt` instead of fields.

**Good-input tips:**
- Keep `intent_status` values short, capitalized, snake-style tokens (e.g. `Not_Interested`) — they appear on status cards and in webhooks.
- Write a clear `description` per field; it is fed to the AI as the rule for that field.
- Add only fields you will actually use downstream (CRM/webhook). Every extra field is more for the AI to get wrong.
- If you only need a sentence summary, use `mode: "summary"` with a `summary_prompt`; you then don't need outcome buckets.

### 14.4 Guidance copy — Outcome buckets (terminal / retry / callback)

> Render this as the help content for the **Outcome Terminal / Retry / Callback** editors.

**What they are:** they map each `intent_status` value to what the dialer should *do* with the lead after the call. This is what turns an AI outcome into a status card (see §1.1–1.3).

- **`outcome_terminal`** → lead becomes **🟢 Completed**. Use for final resolutions. Default: `["Interested", "Not_Interested"]`.
- **`outcome_callback`** → lead becomes **🟣 Callback Scheduled** (uses `callback_time` if present, else +4h). Default: `["Callback_Requested"]`.
- **`outcome_retry`** → lead goes back to **🟡 Pending** for another attempt; once `max_attempts` is hit it becomes **🔴 Failed** (`Max_Attempts_Reached`). Default: `["Busy", "Unknown", "Wrong_Requirement"]`.

**The golden rule (enforced by validation):** every value in `intent_status.values` must appear in **exactly one** of the three buckets — no value missing, no extra value, no overlaps, no duplicates. If you add an outcome to the schema, you must put it in a bucket, or saving fails with a precise error telling you which value is unmapped.

**Example (matches the schema in §14.3):**
```
outcome_terminal:  ["Interested", "Not_Interested"]
outcome_callback:  ["Callback_Requested"]
outcome_retry:     ["Busy", "Wrong_Requirement", "Unknown"]
```

**Good-input tips:**
- Decide the bucket per outcome by asking: *is this final (terminal), worth re-calling (retry), or a scheduled return (callback)?*
- An opt-out / "remove my number" is **terminal** → keep it as `Not_Interested` in `outcome_terminal`. Do not invent a separate "dnc" value (DNC has been removed — see §1.1 / §4).
- Don't over-use retry: only outcomes that genuinely merit another dial. Everything else should be terminal so leads resolve cleanly.

### 14.5 Guidance copy — Normalization Rules & Outcome Event Map

> Render this as the help content for the **Normalization Rules** and **Outcome Event Map** editors.

**Normalization Rules** (`normalization_rules`, a JSON list) — deterministic corrections applied *after* the AI extracts, before the outcome is bucketed. Use them to encode reliable domain logic so you don't depend on the AI getting a nuance right every time.

Rule shape (consumed by `apply_normalization_rules`, `post_call_extract.py:339-401`):
```json
[
  {
    "when": {"field": "site_visit_agreed", "truthy": true},
    "and_intent_in": ["", "Unknown"],
    "set": {"intent_status": "Interested"}
  }
]
```
- `when` matches a field by `truthy` (boolean-ish) or `eq` (exact value).
- Optional `and_intent_in` only applies the rule when the current `intent_status` is in that list (use it to avoid overriding a confident outcome).
- `set` writes one or more fields (typically `intent_status`).
- **This is the correct home for domain-specific logic** (the kind currently hardcoded in `post_call_extract.py` — see Workstream D). Per-bot rules here are how you "optimize output per client" without touching shared code or changing models.

**Outcome Event Map** (`outcome_event_map`, a JSON object) — maps an `intent_status` value to the webhook event name fired to the client's automation (n8n). Example:
```json
{
  "Interested": "lead_qualified",
  "Not_Interested": "lead_not_interested",
  "Callback_Requested": "lead_callback"
}
```
If omitted, built-in defaults apply (`n8n_webhook.py:32-42`). Only add entries for outcomes that should trigger downstream automation.

### 14.6 Worked end-to-end example (put in the guide modal)

> A healthcare appointment-reminder bot. Shows the four inputs working as one unit.

```jsonc
// Extraction Schema
{
  "mode": "fields",
  "fields": [
    { "key": "intent_status", "type": "enum",
      "values": ["Confirmed", "Reschedule_Requested", "Not_Coming", "No_Answer_Followup", "Unknown"],
      "required": true, "description": "Outcome of the reminder call." },
    { "key": "callback_time", "type": "datetime", "required": false,
      "description": "Requested reschedule time in ISO 8601, else NULL." }
  ],
  "extraction_rules": "Infer only from the transcript. Reply with ONE JSON object."
}
```
```
outcome_terminal:  ["Confirmed", "Not_Coming"]
outcome_callback:  ["Reschedule_Requested"]
outcome_retry:     ["No_Answer_Followup", "Unknown"]
```
```json
// Normalization Rules: a patient who explicitly says yes but AI left it Unknown
[
  { "when": {"field": "patient_said_yes", "truthy": true},
    "and_intent_in": ["", "Unknown"],
    "set": {"intent_status": "Confirmed"} }
]
```
```json
// Outcome Event Map
{ "Confirmed": "appointment_confirmed", "Reschedule_Requested": "appointment_reschedule" }
```
Result: `Confirmed`/`Not_Coming` → 🟢 Completed; `Reschedule_Requested` → 🟣 Callback Scheduled (at `callback_time`); `No_Answer_Followup`/`Unknown` → 🟡 Pending → 🔴 Failed after `max_attempts`. Every `intent_status` value is covered exactly once, so it saves cleanly.

### 14.7 Acceptance criteria
- The post-call tab renders editors for **all six** post-call fields. The three outcome buckets are represented by a visual drag-and-drop partition widget with a JSON escape hatch.
- Each editor has inline help drawn from §14.3–14.5; the guide modal has a full "Post-Call Analysis" section with the §14.6 example.
- Saving a config whose `intent_status` values are not covered exactly once by the buckets shows the specific backend error **next to the bucket editors**, not a generic toast.
- The drag-and-drop UI enforces "move not copy" semantics and correctly reconciles orphaned/unmapped pills when the underlying extraction schema changes.
- A new admin can create a working bot config for a non-real-estate domain using only the on-screen guidance, with no code reference.

---

## 15. Implementation log (2026-06-27)

> **Purpose:** record what was actually shipped for Workstreams A/B, post-call extraction reconciliation, verification results, and follow-up fixes applied during code review. Use this as the audit trail; §2–§14 remain the spec targets.

### 15.1 Workstream A — Post-call state machine unification ✅

**Goal:** funnel all five divergent lead-status mutation paths through two pure helpers (`resolve_post_call_transition` for answered calls; `resolve_lead_retry_or_failed` for non-answers/abandoned/housekeeping).

| Path | Before | After |
|---|---|---|
| Normal pipeline end | `resolve_post_call_transition` | unchanged (already correct) |
| Abnormal WS disconnect | `recover_abandoned_session` → `process_post_call` | unchanged (already correct) |
| Unanswered Plivo hangup | `settle_unanswered_call` with `retry_delay_minutes=120` default, outcome `'Unanswered'` | campaign `retry_delay_minutes` + `outcome_from_plivo_status`; normalized outcome on `call_logs` + `leads` |
| Orphaned dials | `settle_unanswered_call(retry_delay_minutes=0)` | same delay; `base_outcome="Carrier_Failed"` |
| Stuck/exhausted housekeeping | inline SQL, `'Unanswered'`, `next_attempt_at = NOW()` | `resolve_lead_retry_or_failed` with campaign delay / `Max_Attempts_Reached` |

**Files changed:**
- `db/postgres.py` — extended `resolve_lead_retry_or_failed` to return `(status, next_attempt_at, outcome)`; rewrote `settle_unanswered_call`, `release_stuck_calling_leads`, `terminalize_exhausted_leads`; updated `fetch_premature_recover_lead_for_post_call` outcome filter
- `plivo_hangup.py` — loads campaign retry delay, maps Plivo `CallStatus` via `call_outcomes.outcome_from_plivo_status`
- `post_call_processor.py` — extracted `_SHORT_CALL_SECONDS = 90` and `_SHORT_CALL_RETRY_CAP_MIN = 1` with intent comment
- `dialer/concurrent_dialer.py` — compliance-block exhausted path writes `Max_Attempts_Reached` instead of `'Unanswered'`

**Review fix (sync order):** `settle_unanswered_call` originally wrote `base_outcome` to `call_logs.outcome` before resolving max-attempts, causing `call_logs.outcome='Busy'` while `leads.outcome='Max_Attempts_Reached'` on exhaustion. Fixed by locking the lead first, calling `resolve_lead_retry_or_failed`, then writing the **same resolved outcome** to both tables.

### 15.2 Workstream B — Outcome normalization (Plivo path) ✅

**Files added/changed:**
- `call_outcomes.py` (new) — canonical sets (`TERMINAL`, `RETRY`, `FAILURE`, etc.) and `outcome_from_plivo_status()`

**Plivo mapping (canonical vocabulary per §1.2):**

| Plivo `CallStatus` | Normalized outcome |
|---|---|
| `busy` | `Busy` |
| `no-answer`, `cancel` | `No_Answer` |
| `reject` | `Rejected` |
| `failed` | `Carrier_Failed` |
| (other/empty) | `Unknown` |

**Review fix:** initial implementation used `"Call_Rejected"` for `reject`; corrected to `"Rejected"` to match §1.2 closed vocabulary.

**Still open for Workstream B:** none — Plivo path and frontend outcome labels complete (Workstream F).

### 15.3 Post-call extraction — `reconcile_extraction_with_assistant_turns` fix ✅

**Symptom:** `tests/test_post_call_engine.py` failed with `AssertionError: assert 'Callback_Requested' == 'Interested'` on `HINDI_STT_CONFLICT_TRANSCRIPT`.

**Root cause (pre-existing):** in `post_call_extract.py`, the assistant sign-off phrase *"कॉल करेंगे"* matched `_CALLBACK_CONFIRM_RE` and the old logic **returned early** with `intent_status = "Callback_Requested"`, skipping `_assistant_confirms_property_interest`. That blocked extraction of `3BHK`, Baner/Kondhwa/Katraj locations, and the correct `Interested` intent.

**Fix (`post_call_extract.py:218-296`):** removed early return; property-interest branch always runs; priority rule — property confirmed + no `callback_time` → `Interested`, explicit time → `Callback_Requested`.

> **Note:** slated for migration to per-bot `normalization_rules` in Workstream D.

### 15.4 Tests added / updated

| Test file | Change |
|---|---|
| `tests/test_post_call_engine.py` | `test_resolve_lead_retry_or_failed` updated for 3-tuple + `Max_Attempts_Reached` |
| `tests/test_call_outcomes.py` | new — Plivo status → outcome mapping |
| `tests/test_post_call_engine.py` | reconcile tests pass after extraction fix (16 total in file) |

### 15.5 Verification results (2026-06-27)

| Command | Result |
|---|---|
| `uv run pytest tests/test_post_call_engine.py -q` | **16 passed** (0.58s) |
| `uv run pytest tests/test_call_outcomes.py -q` | **5 passed** |
| `uv run pytest tests/ -q` (no Postgres) | **146 errors** — session `setup_globals` requires live DB on `127.0.0.1:5432` |
| Pure logic smoke (`call_outcomes` + `resolve_lead_retry_or_failed`) | **OK** |

**§2.3 acceptance spot-checks:**
- `rg "'Unanswered'|\"Unanswered\"" db/postgres.py` → **zero matches** ✅
- Campaign retry delay flows to unanswered path via `plivo_hangup.py` ✅
- All five mutation paths use shared helpers or `process_post_call` ✅

**Remaining §11 gaps:**
- No DB integration test for `settle_unanswered_call` honoring passed `retry_delay_minutes` (spec §11.2)

### 15.6 Workstream C — DNC removal ✅

**Goal:** remove the `dnc` lead status, `campaigns.dnc_leads` counter, and all functional DNC branches. Opt-outs map to `Not_Interested` → `completed` (§3.4).

**Database:**
- `db/schema/001_initial.sql` — dropped `dnc_leads` column; five-status `leads_status_check`; scrubbed `→ dnc` from status-machine comment block
- `alembic/versions/007_remove_dnc.py` — re-homed `dnc` leads to `completed` / `Not_Interested`; realigned `completed_leads`; dropped CHECK + column

**Backend:**
- `post_call_processor.py` — removed `dnc` shortcuts from `_lead_transition` and `resolve_post_call_transition`
- `db/postgres.py` — removed `_COUNTER_DELTAS` / `_ALLOWED_COUNTER_COLS` / upload / `reconcile_campaign_counters` DNC paths
- `api/routes/leads.py` — `_MANUAL_TRANSITIONS` without `dnc`
- `scripts/cli.py` — removed DNC color map, counter print, validation enum entry
- `fix_leads.py` — deleted

**Frontend:**
- `CampaignDetail.jsx` — removed DNC badge, manual-transition mirror, `<select>` option
- `AdminClientDetail.jsx`, `AdminCampaigns.jsx` — removed `dnc_leads` stat rows

**Tests:**
- `test_client_api_edge.py` — lifecycle flows use `completed`; explicit `PATCH status=dnc` → **409**

**Sanitation:**
- `env.example` — removed `INTERNAL_DND_NUMBERS`
- Narrative docs scrubbed (`ROADMAP.md`, `guides/*`, `handoff/*`); `optimization.md` retains historical §4 spec only
- `guides/intro.md` compliance snippet updated to match `compliance.py` (IST window only)

**Verification (2026-06-27):**
- `rg -i '\bdnc\b|dnc_leads|INTERNAL_DND' .` on functional code → migration SQL + 409 test only ✅
- `uv run pytest tests/` → **151 passed** (local, Postgres up)

### 15.7 Sequencing status

| Workstream | Status |
|---|---|
| **A** — unify post-call state machine | ✅ Complete |
| **B** — Plivo outcome normalization + vocabulary module | ✅ Complete |
| **C** — DNC removal | ✅ Complete (see §15.6) |
| **D** — move domain heuristics to per-bot config | ✅ Complete (see §15.10) |
| **E** — performance / indexes | ✅ Complete |
| **F** — frontend status cards + outcome labels | ✅ Complete (see §15.8) |
| **G** — repo cleanup | ✅ Complete |
| **H** — admin guide + bucket editors | ✅ Complete (see §15.9) |

### 15.8 Workstream F — Frontend status cards & outcome labels ✅

**Goal:** five mutually exclusive status metric cards; canonical outcome vocabulary in lead badges (no `Unanswered` / DNC).

**Changes:**
- `frontend/src/pages/client/CampaignDetail.jsx` — five-card grid (Pending, Calling, Callback Scheduled, Completed, Failed) with percentage bars; `OUTCOME_LABELS` / `friendlyOutcome()` for all §1.2 outcomes.
- Budget metrics remain on Overview tab (Resource Allocation) — separate from the five lead-state cards.

**Review fixes (2026-06-27):** expanded outcome label map; Calling card percent + amber bar; Callback card title aligned to spec.

**Verification (2026-06-27):**
- `npm run build` — clean ✅
- `npm run lint` — `CampaignDetail.jsx` `statusElement` refactored to `let` + branch assignments (fixes `no-useless-assignment`) ✅
- No `Unanswered` / DNC references in `frontend/src` ✅

### 15.9 Workstream H — Admin outcome drag-and-drop editor ✅

**Goal:** visual partition UI for `outcome_terminal` / `outcome_callback` / `outcome_retry` tied to `intent_status` enum.

**Changes:**
- `frontend/src/pages/admin/AdminScriptConfigs.jsx` — `OutcomeDragDropEditor` with move-not-copy drag, unmapped/stale warnings, summary-mode hide, empty-schema state, raw JSON escape hatch, save blocked when mapping incomplete.

**Review fixes (2026-06-27):** drop-to-unmapped removes pill from bucket; stale orphan pills highlighted; `getOutcomeMappingState()` validates before save.

**Verification (2026-06-27):**
- `npm run build` — clean ✅
- `getOutcomeMappingState()` blocks save when unmapped/stale intents remain ✅
- `uv run pytest tests/` — **151 passed** (Postgres up); script-config payload schemas unchanged ✅

### 15.10 Workstream D — Extractor de-hardcoding ✅ Completed

**Audit (2026-06-27):** Workstream D is **completed**. The generic extractor (`post_call_extract.py`) no longer contains domain-specific heuristics.

**Completed implementation:**
1. Defined `PYRAMID_NORMALIZATION_RULES` in `sts_scripts/pyramid_extraction.py` reproducing the exact behavior of `reconcile_extraction_with_assistant_turns` using the declarative rules engine.
2. Updated `script_module_export.py` to use these rules as defaults for pyramid configs.
3. Created an Alembic migration (`008_pyramid_normalization_rules`) to inject these rules into existing database rows for the `pyramid_bilingual`, `pyramid_hi`, `pyramid_mr`, and `prowave` scripts.
4. Stripped the domain-specific preamble, regexes, and `reconcile_extraction_with_assistant_turns` from `post_call_extract.py`.
5. Updated `normalize_post_call_extraction` to rely purely on `normalization_rules` when provided, otherwise defaulting to a safe, generic fallback.
6. Cleaned up function signatures (`transcript` argument removed from `normalize_post_call_extraction` across the repository).

**Important behavior change (fallback logic):** When a bot defines any `normalization_rules` (i.e. rules are non-empty), the generic `site_visit_agreed` / `callback_time` fallback in `normalize_post_call_extraction` **no longer runs**. A future bot that sets its own custom rules but omits a site-visit or callback-time rule will lose that inference. This is correct-by-design (explicit config wins), but must be kept in mind when writing new bot configurations.

**Verification (2026-06-27):**
- Extractor rules correctly map string values into fields like `callback_time`, `bhk_preference` and patch `intent_status`.
- `grep -i` for `bhk`, `baner`, `katraj`, `kondhwa` in `post_call_extract.py` returns nothing.
- `uv run pytest tests/` — **151 passed** (no breakages).

### 15.11 Workstream E — Performance / bottleneck elimination ✅ Completed

**Audit (2026-06-27):** Workstream E is **completed**. The dialer hot-path and bottleneck issues have been addressed.

**Completed implementation:**
1. Created `alembic/versions/009_calllog_indexes.py` adding two new partial indexes: `idx_call_logs_lead_live` and `idx_call_logs_lead_ended` to serve `NOT EXISTS` subqueries.
2. Appended both index definitions to `db/schema/001_initial.sql` to maintain fresh-DB parity.
3. Added a per-campaign cooldown gate (`_RELEASE_STUCK_COOLDOWN_S = 30.0`) inside the `claim-failure` branch of `concurrent_dialer.py` to drastically reduce DB load.
4. Created `guides/admin_script_guide.md` as an exhaustive reference for script configuration, extraction, outcome routing, normalization, and live tools.

**Verification (2026-06-27):**
- Schema modifications applied properly.
- All tests passed.

### 15.12 Workstream G — Repo cleanup & Verification ✅ Completed

**Audit (2026-06-27):** Workstream G is **completed**.

**Completed implementation:**
1. Deleted 14 root-level ad-hoc scripts (e.g., `fix_db.py`, `query.py`, `patch.py`, `diff.txt`).
2. Deleted unimported root-level `async def main()` scratchpads named `test_*.py`.
3. Moved active CMS E2E dial script `test_call.py` to `scripts/test_call.py` and updated `justfile` and `tests/test_test_call.py`.
4. Updated `pyproject.toml` to explicitly restrict `testpaths = ["tests"]`.
5. Created integration test `tests/test_settle_unanswered_call.py` to cover both retry and exhaustion paths using ephemeral records.

**Verification (2026-06-27):**
- DB `EXPLAIN ANALYZE` confirms `idx_call_logs_lead_live` and `idx_call_logs_lead` index scans for dialer queries.
- `release_stuck_calling_leads` loop correctly honors the 30s rate-limit.
- All 153 tests pass.

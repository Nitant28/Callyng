# Final Cleanup and Wrap-Up Plan (Revised v2)

This plan details the finalized strategy for Workstream G (Repo Cleanup), the §11.2 Integration Test, Workstream E `EXPLAIN ANALYZE` validation, frontend UI polish, seed data repointing, and comprehensive documentation updates.

## 1. Workstream G (Repo Cleanup & Organization)

### A. Delete Ad-hoc Files
Delete the following 14 unimported scratch files:
- `fix_db.py`, `patch.py`, `patch_modal.py`, `patch_modal_ui.py`, `fix_modal_ui.py`, `fix_modal_final.py`
- `insert_bugs.py`, `append_bugs.py`
- `query.py`, `query_db.py`, `query_json.py`
- `get_recent_test_calls.py`, `clear_db.py`, `plivo_record_test.py`
- `diff.txt`
- `test_api.py`, `test_api2.py`, `test_api3.py`
- `test_db.py`, `test_db_2.py`, `test_db_3.py`
- `test_leads.py`, `test_logs.py`, `test_stats.py`, `test_bug.py`, `test_pool.py`

*(Note: `check_r2.py` does not exist and is skipped).*

### B. Relocate & Update Active Tooling (`test_call.py`)
Move `test_call.py` (the active CMS E2E dial script) to `scripts/test_call.py`.
Update references:
- **`justfile`**: Update `cms-call` target to `uv run python scripts/test_call.py ...`
- **`tests/test_test_call.py`**: Update imports from `import test_call` to `from scripts import test_call`.
- **Docs**: Update references in `guides/plan.md` and `handoff/log.md`.

### C. Pytest Configuration Safety
Update `pyproject.toml` to explicitly restrict test collection to the `tests/` directory:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## 2. Integration Test (§11.2: `settle_unanswered_call`)

Create a new dedicated integration test file: **`tests/test_settle_unanswered_call.py`**.
Leverage the standard DB pool fixture (`setup_globals`). Insert ephemeral records via `uuid4()` to test:

1. **Retry Path**: A lead at `attempts=1`, `max_attempts=3`, `retry_delay_minutes=10`, `base_outcome="Busy"`.
   - *Assert*: Lead status becomes `'pending'`, outcome `'Busy'`, `next_attempt_at` ≈ `now + 10m`, and `call_logs.in_progress = FALSE`.
2. **Exhaustion Path**: A lead at `attempts=3`, `max_attempts=3`.
   - *Assert*: Lead status becomes `'failed'`, outcome `'Max_Attempts_Reached'`, and the call log mirrors this outcome (preventing the async sync-order bug).

---

## 3. Workstream E Validations (`EXPLAIN ANALYZE`)

Execute two DB queries targeting a real seed lead to validate the new indexes (`idx_call_logs_lead_live` and `idx_call_logs_lead_ended`):

```sql
-- 1. Live-call NOT EXISTS (15 min grace)
EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM call_logs c WHERE c.lead_id = '<real-lead-uuid>' AND c.in_progress = TRUE AND c.started_at > NOW() - (15 * INTERVAL '1 minute');

-- 2. Wrap-up NOT EXISTS (5 min grace)
EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM call_logs c WHERE c.lead_id = '<real-lead-uuid>' AND c.ended_at IS NOT NULL AND c.ended_at > NOW() - (5 * INTERVAL '1 minute');
```

Document the verified `Index Scan` usage in `optimization.md §15.11`.
Create an optional `scripts/dev/explain_dialer_indexes.sql` script to make this check repeatable. Verify the 30s cooldown in standard application logs.

---

## 4. Frontend Polish (Workstream H UX)

Modify **`frontend/src/pages/admin/AdminScriptConfigs.jsx`**:
1. **Inline Validation Errors**: Remove `saveError` from the truncated modal footer and place it inline at full-width below the `OutcomeDragDropEditor`.
2. **Explicit Empty vs Defaults**: Update the helper copy:
   *"Untouched bucket fields save as null and fall back to system defaults. Once you drag a pill or edit raw JSON, the field is saved explicitly — use [] only if you intend an empty bucket."*
3. **Auto-Tab Switch on Validation Failure**: Detect backend validation errors regarding unmapped intents, automatically switch the modal view to the `post-call` tab, and scroll to the mapper.

---

## 5. Seed Data Integrity

### A. Repoint Seeded Sandboxes
Modify **`db/seed/dev_tenant.sql`**:
- Do not delete sandbox bot/campaign UUIDs (they are wired in tests).
- Update bot `...004` (`CLI Sandbox (STS)`) to use `script_id = 'pyramid_hi'`.
- Update bot `...005` (`CLI Sandbox (Cascaded)`) to use `script_id = 'prowave'`.

### B. Cleanup API Routes
Modify **`api/routes/internal_script_configs.py`**:
  - [x] Deleted the `[r for r in rows if not r.get("script_id", "").startswith("cli_sandbox")]` filter since sandbox bot logic uses standard UUID bot configs now.

---

## 6. Documentation Enhancements

### A. Scripting Guide Modal
Modify **`frontend/src/components/shared/ScriptingGuideModal.jsx`**:
- Add a new "Post-Call Flow Architecture" subsection outlining the pipeline: `Transcript -> LLM Extraction -> Normalization Rules -> Outcome Routing -> State Update`.
- Add cross-link to `guides/admin_script_guide.md`.
- Fix the stale example ID: `pyramid_hindi` -> `pyramid_hi`.

### B. Repo Meta Documentation
- **`guides/optimization.md`**: Update the header status (Lines 1-5) and the §15.7 status table to reflect Workstreams A,B,C,D,E,F,H are complete. Mark G complete at the end of execution.
- **`guides/cleanup.md`**: Reconcile with the actions taken here (test_call relocation vs deletion) and mark sections completed.

---

## 7. Execution Order & Verification Gate

**Execution Sequence:**
1. Workstream G deletions and `test_call.py` relocation.
2. Update `pyproject.toml` and documentation cross-references.
3. Update `dev_tenant.sql` to repoint sandboxes, then remove API filters.
4. Implement `test_settle_unanswered_call.py` integration test.
5. Apply UX polish to `AdminScriptConfigs.jsx` and `ScriptingGuideModal.jsx`.
6. Run `EXPLAIN ANALYZE` validations and add repeatable SQL script.
7. Perform final documentation updates in `optimization.md` and `cleanup.md`.

**Final Verification Gate:**
```bash
# 1. Tests must pass cleanly
uv run pytest tests/ -q

# 2. Frontend builds cleanly
cd frontend && npm run lint && npm run build

# 3. Legacy terms removed
rg -i '\bdnc\b|dnc_leads' .
rg "'Unanswered'" db/postgres.py frontend/src/

# 4. Imports properly tracked
rg "from test_call|import test_call"

# 5. DB Seed pipeline functional
just db-seed && uv run python scripts/migrate_script_configs.py
just cms-call 00000000-0000-4000-8000-000000000004 +919999999999 sts
```

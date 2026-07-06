# Repository Cleanup Guide

This document outlines the planned cleanup for various loose test scripts and ad-hoc developer files currently scattered in the repository root. These files are not automated `pytest` suites (they lack `def test_...` functions) and are instead manual scratchpads or CLI utilities.

**Note:** This cleanup should only be executed *after* the changes in `guides/optimization.md` are completed.

## 1. CLI Utilities
These are robust scripts meant to be used by developers or operators. They should be moved to the `scripts/` directory to keep the root clean.

- **`test_call.py`**
  - **Type:** Full CMS end-to-end test call script (with argparse, DB seeding requirements, etc.)
  - **Action:** Move to `scripts/test_call.py` (or `scripts/dev/test_call.py`).
  - **Note:** Ensure any `justfile` commands referencing it are updated to point to the new path.

## 2. Ad-hoc API & DB Scratchpads
These are small (<1KB), manual throwaway scripts used for quick local testing (e.g., hitting localhost endpoints with `requests` or quick `asyncpg` queries). 

**Recommended Action:** Move these to a new `scripts/dev/` or `tests/scratch/` directory so they are preserved but out of the way. Alternatively, if they are no longer useful, they can be safely deleted.

- **API Tests:**
  - `test_api.py`
  - `test_api2.py`
  - `test_api3.py` (Simple `requests.get` script)
- **Database & Bug Tests:**
  - `test_bug.py` (Incomplete scratchpad for a specific UUID issue)
  - `test_db.py`, `test_db_2.py`, `test_db_3.py`
  - `test_leads.py`
  - `test_logs.py`
  - `test_pool.py`
  - `test_stats.py`

## 3. Other Dev/Throwaway Scripts (From optimization.md)
The optimization guide also identifies the following files as "dev scratch" that are slated for cleanup. They should either be deleted entirely (if their purpose is served) or moved to `scripts/dev/` alongside the scratchpads above.

- `fix_db.py`, `fix_leads.py`
- `fix_modal_final.py`, `fix_modal_ui.py`
- `patch.py`, `patch_modal.py`, `patch_modal_ui.py`
- `insert_bugs.py`, `append_bugs.py`
- `query.py`, `query_db.py`, `query_json.py`
- `get_recent_test_calls.py`
- `clear_db.py`
- `plivo_record_test.py`
- `diff.txt`

> **Status (2026-06-27):** Executed. All 14 listed scratch files and `test_*.py` main files were completely deleted as part of Workstream G. `test_call.py` was moved to `scripts/test_call.py`.

## Execution Plan
Once `optimization.md` is complete:
1. Create `scripts/dev/` (or `tests/scratch/`).
2. Move the listed files into their respective target folders.
3. Verify that no application modules import these files (e.g., run `rg "import fix_db"` to ensure safety).
4. Run `pytest` and `just test` to confirm nothing was broken by the move.

## 4. Core Application Modules in Root
Files like `script_module_export.py`, `script_prefetch.py`, `script_runtime.py`, `post_call_extract.py`, etc., are **core production code**, not scratchpads.

Currently, the architecture has most of the FastAPI application logic sitting directly in the root directory. While moving them to a dedicated module folder (e.g., `core/` or `app/`) would make the root much cleaner, **it is a much larger architectural refactor.**

**Recommended Action for Core Files:**
If you want to organize these, you must:
1. Move them into a dedicated backend directory (e.g., `backend/core/`).
2. Update all `import` statements across the entire codebase (e.g., `from core.script_prefetch import ...` instead of `from script_prefetch import ...`).
3. If you decide to do this, do it as a separate standalone refactoring PR *after* the current optimization tasks and the script cleanup are completely finished, to minimize merge conflicts.

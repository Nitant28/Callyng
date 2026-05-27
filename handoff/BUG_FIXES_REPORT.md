# Bug Fixes Report

This document outlines the bugs that were addressed and the specific changes made to resolve them.

## 1. `cancel_campaign` Tuple Unpacking Bug
**Issue**: `try_settle_campaign_budget` was changed to return `tuple[Decimal, bool]`, but `cancel_campaign` was treating the entire tuple as a float, causing a `TypeError`.
**Fix**: In `db/postgres.py`, updated `cancel_campaign` to correctly unpack the tuple:
```python
credits_returned, _ = await try_settle_campaign_budget(...)
```

## 2. `return_unused_budget` Annotation Mismatch
**Issue**: The inner `_run` function in `return_unused_budget` was annotated as returning `Decimal`, but it returned `tuple[Decimal, bool]` from `try_settle_campaign_budget`.
**Fix**: In `db/postgres.py`, corrected the return annotation of the `_run` function to `tuple[Decimal, bool]`.

## 3. Uninitialized `just_completed` Variable
**Issue**: In `post_call_processor.py`, `just_completed` was only assigned inside the `else` block of the active lead check. If a call lacked an active lead, the later `if applied and just_completed:` condition would raise a `NameError`.
**Fix**: In `post_call_processor.py`, initialized `just_completed = False` at the top of the `process_post_call` function alongside `applied = False`.

## 4. Timeout on Post-Call Transaction
**Issue**: `_extract_patch_and_webhook` in `call_transcript.py` was wrapping `process_post_call` in `_pg_write(...)`, which applies a strict 5-second `asyncio.wait_for` timeout intended for single-row writes. This was causing multi-step database transactions to silently fail under load.
**Fix**: In `call_transcript.py`, removed the `_pg_write()` wrapper around the `process_post_call` invocation. It now runs directly with its internal transaction and logging.

## 5. Dead Row Fetch in `cancel_campaign`
**Issue**: In `db/postgres.py`, a `fetchrow` query for `calling_leads, status, budget_returned_at` was executed inside the transaction of `cancel_campaign`, but the `row` variable was never used.
**Fix**: Removed the dead `fetchrow` entirely, eliminating the unnecessary database round-trip.

## 6. Unenforced Draft-Only Transition in `start_campaign`
**Issue**: The `/start` endpoint did not check the campaign's current status before attempting to start it, meaning completed or cancelled campaigns could theoretically be resumed.
**Fix**: In `api/routes/campaigns.py`, added a validation check to `start_campaign` ensuring that only campaigns in the `draft` or `paused` state can be started:
```python
if camp["status"] not in ("draft", "paused"):
    raise HTTPException(409, f"Cannot start a {camp['status']} campaign")
```

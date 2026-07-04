# 16 — Testing Guide

---

## Framework

- **pytest** + **pytest-asyncio** (`tests/conftest.py`)
- HTTP tests via **httpx** `AsyncClient` + `ASGITransport(app=server.app)`
- Real **Postgres + Redis** required (session fixture initializes pools)

---

## Test layout (`tests/` — 23 files verified)

| File | Focus |
|------|-------|
| `conftest.py` | pool/redis init; autouse `mock_is_call_allowed` (bypass TRAI time gate); session cleanup deletes non-seed rows |
| `test_phase2.py` | core multi-tenant API flows |
| `test_client_api_edge.py` | client API edge cases |
| `test_e2e.py` | end-to-end flows |
| `test_post_call_engine.py` | post-call state machine |
| `test_early_disconnect_policy.py` / `test_early_disconnect_post_call.py` | Early_Disconnect |
| `test_settle_unanswered_call.py` | unanswered billing |
| `test_call_outcomes.py` | outcome vocabulary |
| `test_call_transcript_norm_rules.py` | normalization |
| `test_post_call_snapshot.py` | snapshot parsing |
| `test_script_runtime.py` | 3-tier resolution |
| `test_script_prefetch.py` | Redis prefetch |
| `test_script_config_api.py` | admin script-config routes |
| `test_script_config_validation.py` | payload validation |
| `test_script_module_export.py` | script module contracts |
| `test_concurrent_dialer_unit.py` | dialer logic (mocked) |
| `test_cost_guard_budget.py` | budget guard |
| `test_redis_state.py` | warmup/redis |
| `test_pg_context_recovery.py` | abandoned session recovery |
| `test_background_tasks.py` | task registry |
| `test_test_call.py` | dial-test path |
| `test_migrate_script_configs.py` | migration backfill |

---

## Running tests

```powershell
cd aakashvani
docker compose up -d postgres redis
uv run alembic upgrade head
uv run pytest tests/ -v
# Single file:
uv run pytest tests/test_post_call_engine.py -v
```

---

## Coverage

**Not verified from source:** no coverage report is configured in the repo by default.
To add:
```powershell
uv run pytest tests/ --cov=. --cov-report=term-missing
```
(requires `pytest-cov` in dev deps — check `pyproject.toml` before relying).

---

## Seed data (tests)

`conftest.py` preserves seed UUIDs:
- Client: `00000000-0000-4000-8000-000000000001`
- Campaigns, bot_configs as listed in conftest cleanup exclusions.

Tests create ephemeral data; session teardown deletes non-seed rows.

---

## How to add tests

1. **API test:** use `client` fixture (`AsyncClient`), set headers:
   - Client: `Authorization: Bearer <seed_key>`
   - Admin: `X-Admin-Key: <ADMIN_API_KEY from .env>`
2. **DB assertion:** acquire `app.state.pool` or call via API and check response.
3. **Time-dependent:** `mock_is_call_allowed` is autouse-patched to always allow;
   override per-test if testing compliance.
4. **Dialer:** prefer `test_concurrent_dialer_unit.py` patterns (mock Plivo).
5. **Post-call:** build minimal transcript + extraction dict; call
   `process_post_call` directly with test pool.

---

## CI

**Not verified from source:** no `.github/workflows` found in this pass. Check repo
for CI config before assuming automated runs.

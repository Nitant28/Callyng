with open("guides/bugs2.md", "a") as f:
    f.write("""
| BUG-30 | P1 | call_transcript.py:159,544 | Bare `except Exception:` swallows DB/logic errors |
| BUG-31 | P2 | n8n_webhook.py:64 | Webhook swallows HTTP exceptions without retry |
| BUG-32 | P2 | api/routes/campaigns.py:175 | upload_leads crashes 500 on pd.errors.ParserError |
| BUG-33 | P2 | server.py:389 | /answer endpoint swallows JSON decode error |
| BUG-34 | P1 | server.py:462 | WS bot exception skips pgctx cleanup & budget settlement |
| BUG-35 | P2 | dialer/cost_guard.py:19 | check_campaign_budget ignores `pool` arg |

---

## BUG-30 [P1] — `call_transcript.py`: Bare `except Exception:` swallows DB and extraction errors
- **Files:** `call_transcript.py`, lines 159 & 544.
- **Issue:** Uses `except Exception:` without `logger.exception` or re-raising. Line 159 swallows DB pool initialization errors, making the whole module silently fail to write call logs. Line 544 swallows `call_log` extraction update failures.
- **Impact:** Critical failures are completely hidden, leaving incomplete `call_logs` rows without any trace in the application logs.
- **Fix:** Use `logger.exception("...")` instead of `except Exception:` to capture the stack trace.

---

## BUG-31 [P2] — `n8n_webhook.py`: Webhook swallows HTTP errors without retry mechanism
- **File:** `n8n_webhook.py`, line 64.
- **Issue:** The webhook client catches `except Exception as exc:` and just logs it. If n8n or the target CRM is temporarily down or hits a timeout, the webhook fails silently and the post-call payload is lost forever.
- **Impact:** Failed webhooks cause data loss for the client CRM since Aakashvani does not retry failed event deliveries.
- **Fix:** Implement a background retry queue with exponential backoff for failed webhook deliveries.

---

## BUG-32 [P2] — `api/routes/campaigns.py`: `upload_leads` crashes with HTTP 500 on malformed CSV files
- **File:** `api/routes/campaigns.py`, lines 174-176.
- **Issue:** The endpoint catches `pd.errors.EmptyDataError` but ignores `pd.errors.ParserError`, `UnicodeDecodeError`, and other Pandas parsing exceptions. 
- **Impact:** Uploading a malformed CSV file causes a raw HTTP 500 crash rather than a graceful HTTP 400 bad request error.
- **Fix:** Broaden the exception handler or add separate catches for `pd.errors.ParserError` and `ValueError` to return a 400 error.

---

## BUG-33 [P2] — `server.py`: `/answer` endpoint swallows JSON decode error and passes malformed `body_data`
- **File:** `server.py`, lines 388-393.
- **Issue:** 
  ```python
  try:
      parsed = json.loads(body_data)
      # ... base64 encode ...
  except Exception:
      pass
  ```
  If `json.loads` fails, it does nothing. But `body_data` was appended to the `ws_url` query params earlier or is passed to the frontend improperly encoded, leading to a downstream failure in `ws_endpoint`.
- **Impact:** Silent failure that propagates malformed data to the Pipecat websocket.
- **Fix:** Handle the exception and log a warning, or return HTTP 400 if `body_data` is strictly required to be JSON.

---

## BUG-34 [P1] — `server.py`: WebSocket bot exception skips `pgctx` cleanup and budget settlement
- **File:** `server.py`, line 462.
- **Issue:** In `ws_endpoint`, if `await bot_fn(runner_args)` raises an exception, the handler logs the error and does `await websocket.close()`. It never runs the pipeline finalized logic in `call_transcript.py`.
- **Impact:** Confirms EDGE-04 from `bugs2.md`. The budget reservation is permanently stranded and the `call_logs.in_progress` stays TRUE until the stale sweep cleans it up.
- **Fix:** Add a `finally` block or a fallback cleanup handler that calls `pg_db.mark_call_log_not_in_progress` and `settle_call_budget` if the pipeline crashed before finishing.

---

## BUG-35 [P2] — `dialer/cost_guard.py`: `check_campaign_budget` ignores `pool` argument
- **File:** `dialer/cost_guard.py`, lines 14-20.
- **Issue:** The function signature accepts `pool: asyncpg.Pool` but never passes it to `pg_db.campaign_budget_remaining`. The downstream function relies on `get_pool()` which accesses the global variable.
- **Impact:** Poor software design that tightly couples the dialer to the global DB pool and could fail in test environments where `get_pool()` is not populated.
- **Fix:** Pass `pool` down to `campaign_budget_remaining` and use it explicitly.
""")

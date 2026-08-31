# 09 — Call Lifecycle

---

## Outbound flow (campaign dialer — production path)

```
1. CLAIM     claim_leads_for_dialer: pending|callback_scheduled → calling, attempts+1
2. RESERVE   budget_used += R (setup + rate × 2 min), stored on call_log.call_data
3. LOG START insert_call_log_start: in_progress=TRUE, session_call_id=UUID
4. DIAL      Plivo REST POST /Call/ → answer_url, hangup_url
5. PREWARM   (STS only) Redis warmup signal; /answer waits ≤3s
6. ANSWER    Plivo GET /answer → Stream XML → WebSocket /ws
7. RECORD    start_plivo_recording (background)
8. CONVERSE  Pipecat bot; transcript appended per turn
9. END       end_call tool | max_call_minutes watchdog | goodbye fallback | callee hangup | WS close
10. EXTRACT  Groq post-call extraction (background)
11. SETTLE   process_post_call: billing, lead FSM, counters, budget, webhooks
12. HANGUP   /plivo-hangup records metadata; may trigger callee callback policy
```

---

## Inbound / manual flow (`POST /start`)

Same steps 3–11 but triggered manually (dev/test). No lead claim; no campaign
billing unless `_pg` context is injected in `body`. Used by admin dial-test and
`just call`. **Not used by client frontend.**

---

## Concurrent dialer (`dialer/concurrent_dialer.py`)

- One asyncio task per running campaign (`app.state.dialer_tasks`).
- Claims up to `slots = min(campaign.max_concurrent_calls - calling_leads,
  client.max_concurrent_calls - global_calling, batch_size)` leads per tick.
- Rate: sleeps `60 / calls_per_minute` between launch batches.
- **Redis lock** `dialer_lock:{campaign_id}` — only one worker dials a campaign.
- Stops when: campaign not `running`, budget exhausted, Plivo balance low,
  outside TRAI window (waits), or `stop_dialer` called.
- On stop: status → `pausing` if `calling_leads>0` else `paused` (client) or
  `paused` (admin).

---

## Call limits (`call_limits.py`)

- `max_call_minutes`: campaign override → env `MAX_CALL_MINUTES` (default 10).
- `schedule_max_call_duration`: asyncio watchdog cancels pipeline after N minutes.
- `end_call` LLM tool: graceful hangup after bot finishes speaking (`CallEndCoordinator`).
- `register_goodbye_hangup_fallback`: detects goodbye markers from script config.

---

## Warmup (`db/warmup_state.py`, `server._prewarm_gemini`)

- `/start` sets `warmup:{call_id}=pending`, fires background Gemini Live session.
- `/answer` waits up to **3s** for `ready`.
- Skipped for `cascaded` route (immediately ready).
- Failure is non-fatal.

---

## Credits (per call)

```
billed_minutes = duration_seconds / 60
credits_charged = setup + billed_minutes * rate   (snapshot on call_data)
budget_used adjustment = round_half_up(credits_charged, 2) - reservation
```

Unanswered (busy / no-answer / reject / failed): **₹0**, reservation refunded. Charge only after the callee picks up (post-call). Never-Plivo / test call: ₹0.

---

## Recording (`recording.py`)

- Started at `/answer` when `CallUUID` known.
- Webhook `/plivo-recording` stores `recording_url` as `plivo:<url>` or `local:<file>`.
- Client plays via `/api/calls/{id}/recording/play` (proxied stream).

---

## Transcript (`call_transcript.py`)

- `TranscriptBuffer` collects user/assistant turns during pipeline.
- `append_transcript_turn` writes to Postgres `call_logs.transcript` JSONB (live polling).
- Also written to SQLite `call_log_db` (parallel, not exposed to frontend API).
- On finalize: full transcript + usage metrics persisted.

---

## Post processing

See `08_DATA_FLOW.md` §5. Key outcomes drive lead FSM via `outcome_buckets` from
script config or defaults in `call_outcomes.py`.

---

## Settlement (campaign level)

- `maybe_auto_settle_campaign`: when `pending+callback+calling==0` → status
  `completed`, `try_settle_campaign_budget` returns unused credits to client balance.
- `cancel_campaign`: terminalize leads, return budget when no in-flight calls.
- Idempotent via `budget_returned_at`.

---

## Failure handling

| Failure | Behavior |
|---------|----------|
| Plivo dial fails | lead released from calling; reservation released (verified in dialer error path — inspect `concurrent_dialer.fire_call` for exact) |
| WS abnormal close | `/ws` finally: mark call_log not in_progress, `recover_abandoned_session` |
| Extraction fails | `extraction_error` set; lead still processed with `Unknown` outcome |
| Stale in_progress | `stale_call_log_loop` finalizes after grace (`STALE_CALL_LOG_SWEEP_SECONDS`) |
| Stuck calling lead | `release_stuck_calling_leads` (manual or on start) |

---

## Retry handling

- Retry outcomes (`Busy`, `Unknown`, `Wrong_Requirement`, etc. per `outcome_retry`):
  if `attempts < max_attempts` → `callback_scheduled` with `next_attempt_at = now + retry_delay_minutes`.
- Short calls (<90s) with retry outcomes: cap retry to **1 minute** (`_SHORT_CALL_RETRY_CAP_MIN`).
- `Early_Disconnect` (callee hangup <30s, weak intent): outcome forced; retry via callback bucket.
- Callee hangup mid-call (non-terminal): often → `callback_scheduled` with retry delay (`resolve_post_call_transition`).
- Exhausted attempts → `failed` + `lead_failed` webhook.

---

## Plivo status → outcome mapping

`call_outcomes.outcome_from_plivo_status` maps busy/no-answer/reject/failed to
internal outcomes. Used in `settle_unanswered_call`.

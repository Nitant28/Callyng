# 08 — Data Flow

End-to-end traces for every major feature. Arrows are sequential; parallel steps
noted.

---

## 1. Lead upload (CSV)

```
Client POST /api/campaigns/{id}/leads/upload (multipart file)
  → campaigns.get_campaign (404/409 if not draft|paused)
  → get_bot_config → _get_lead_schema (script_config.lead_schema OR sts_scripts.LEAD_SCHEMA)
  → parse_upload (pandas CSV/XLSX)
  → validate_dataframe (400 {errors} if invalid)
  → per row: normalise_phone → skip invalid
  → is_call_allowed() → if outside TRAI window: next_attempt_at = next_compliant_time()
  → build metadata from schema fields
  → bulk_insert_leads (ON CONFLICT DO NOTHING on campaign_id+phone)
  → increment_campaign_counters (__upload__ → pending)
  → response {leads_uploaded, invalid_phones, duplicates_skipped}
```

**DB writes:** `leads` (insert), `campaigns` (total_leads, pending_leads +N).

---

## 2. Campaign start

```
Client PATCH /api/campaigns/{id}/start
  → get_campaign (409 if wrong status; 400 if budget remaining < 2)
  → release_stuck_calling_leads
  → bump_pending_retry_to_now (next_attempt_at <= now for pending/callback)
  → reconcile_campaign_counters (COUNT FILTER → overwrite counters)
  → update_campaign_status → 'running'
  → start_dialer(app, campaign_id, client_id, host)
       → asyncio.create_task(run_campaign_dialer)
       → Redis dialer_lock acquire
```

**DB writes:** `leads` (status fixes), `campaigns` (status, counters).

---

## 3. Dialer claim → outbound call

```
run_campaign_dialer loop (every ~batch):
  → check_campaign_budget (remaining >= MIN_REMAINING)
  → check plivo_balance (cached USD)
  → is_call_allowed() (TRAI) — sleep until compliant if not
  → claim_leads_for_dialer (FOR UPDATE SKIP LOCKED, status pending|callback, next_attempt_at<=now)
       → status pending/callback → calling, attempts+1
       → reserve_campaign_budget (+2 credits to budget_used)
       → increment_campaign_counters
  → script_prefetch.render + Redis SET prefetch:{call_id}
  → insert_call_log_start (in_progress=TRUE, session_call_id=uuid)
  → telephony.make_plivo_call(answer_url=/answer?call_id&body_data, hangup_url)
```

**DB writes:** `leads`, `campaigns` (counters, budget_used reservation), `call_logs` (start row).
**Redis:** prefetch, pg context registered later at /ws.

---

## 4. Answer → live conversation

```
Plivo GET /answer
  → wait_for_warmup(call_id) [Redis]
  → link_call_log_plivo_sid (async)
  → start_plivo_recording (async)
  → return <Stream> XML → wss://host/ws?call_id&body=base64

/ws WebSocket
  → pop_prefetched_config → _prefetched_config
  → register_pg_context(call_id, _pg)
  → bot_sts|bot_cascade Pipecat pipeline
       → TranscriptBuffer appends turns → append_transcript_turn (Postgres transcript JSONB)
       → on pipeline end → finalize transcript → Groq extract_post_call
       → process_post_call (transaction)
```

---

## 5. Post-call processing

```
process_post_call(session_call_id, lead_id, campaign_id, ...)
  → load campaign, bot_config, lead, call_log
  → billed_minutes = ceil(duration/60); credits_charged = billed_minutes * cpm
  → outcome = extraction.intent_status (+ Early_Disconnect policy if callee hung up <30s)
  → TRANSACTION:
       → lock lead (calling|callback_scheduled)
       → resolve_post_call_transition → new_status, next_attempt_at
       → update_lead_post_call
       → finalize_call_log (in_progress=FALSE, billing, extraction)
       → settle_call_budget (actual - reserved)
       → increment_campaign_counters(from→to)
       → maybe_auto_settle_campaign (if all terminal → completed + return budget)
       → maybe_transition_pausing (pausing→paused when calling_leads=0)
  → fire_event_webhook (outside txn) if terminal/callback/failed event mapped
  → fire_campaign_completed_webhook if just completed
```

**DB writes:** `leads`, `call_logs`, `campaigns` (counters, budget_used, maybe status completed), `clients` (budget return on completion).

---

## 6. Unanswered call (no connect)

```
Plivo /plivo-hangup (no answer / busy / reject)
  → record_plivo_hangup (plivo_hangup_json)
  → settle_unanswered_call
       → finalize call_log (0 credits, outcome from Plivo status map)
       → release budget reservation
       → lead: calling → callback_scheduled or failed (by attempts)
       → increment_campaign_counters
```

---

## 7. Client dashboard view

```
GET /api/credits → clients.balance_credits
GET /api/campaigns → campaigns.* (all counters)
[poll 5s if active]
Frontend renders counters verbatim — NO recount from leads
```

---

## 8. Call logs / transcript view

```
GET /api/calls (paginated list)
User opens row → GET /api/calls/{session_call_id}
  → if in_progress: poll 2s until FALSE
GET /api/calls/{id}/recording/play → audio blob
```

---

## 9. Admin credit top-up

```
PATCH /internal/clients/{id}/credits {amount, note}
  → add_credits: clients.balance_credits += amount (FOR UPDATE)
  → INSERT credit_transactions
```

Budget allocation on campaign create is separate (`allocate_campaign_budget`).

---

## 10. Webhook to CRM (n8n)

```
post_call_processor (fire_webhook) OR campaign_completed
  → get_webhook_config_for_event(client_id, event)
  → sign_payload HMAC → POST url
  → n8n routes to Sheets/WhatsApp/CRM (external)
```

Payload includes lead, extraction, duration, credits_charged, recording_url.
Exact payload shape: see `n8n_webhook.fire_event_webhook` (Not fully transcribed here).

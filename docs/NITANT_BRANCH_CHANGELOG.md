# Nitant branch — change documentation (push checklist)

**Branch:** `Nitant` (tracking `origin/Nitant`, currently **ahead by 23 commits** + large **uncommitted** working tree)  
**Purpose:** Document what changed so you can review, commit, and push safely.

---

## How to read this

| Layer | What it is |
|--------|------------|
| **A. Already committed (ahead of origin)** | Merges + commits already on local `Nitant` but not pushed |
| **B. Uncommitted product work** | Follow-up / WhatsApp / n8n / frontend / migrations still in the working tree |
| **C. Ops-only / do not commit** | Live scripts, temp outputs, credentials, Excel dumps |

Push = push **A** after you commit what you want from **B**. Skip **C**.

---

## A. Already on local `Nitant` (not yet pushed)

Local is **23 commits ahead** of `origin/Nitant`. Notable themes in that history:

- Credit system upgrades / unanswered-call billing fixes
- JSONB / Postgres string-vs-array fixes
- Cascade post-call writing to Postgres (not SQLite)
- Event architecture + cascade routes
- Merge `origin/main` into `Nitant` + n8n admin config consolidation
- Remove obsolete AdminWhatsApp page; harden follow-up tests

These are already commits. Review with:

```bash
git log origin/Nitant..HEAD --oneline
git diff origin/Nitant...HEAD --stat
```

---

## B. Uncommitted product changes (main work to commit before push)

### 1. WhatsApp follow-up delivery (core)

**Goal:** Interested + **manual** follow-ups send a Meta-approved branded template to **any** number (not Nitant-only, not `hello_world`).

| File | Change |
|------|--------|
| `followups/service.py` | Delivery decision owned by backend; n8n HTTP 200 ≠ WhatsApp sent; campaign webhook routing; eligibility; `force_whatsapp` + interested flags for **manual**; user-facing error messages |
| `followups/eligibility.py` | **New.** Channel eligibility; **manual** bypasses missing `whatsapp_opt_in` (auto path stays fail-closed) |
| `followups/delivery.py` | **New.** Prefer backend Meta send (wamid); else defer to n8n with approved non-sample template |
| `followups/enrichment.py` | First-contact plan + template params on payload |
| `followups/templates.py` | First-contact template config (`first_contact_template` on integration) |
| `followups/template_ref.py` | **New.** Normalize Meta template name/language/components |
| `followups/template_registry.py` | **New.** Purpose registry; reject sample/`hello_world` |
| `followups/idempotency.py` | **New.** Follow-up event idempotency helpers |
| `followups/repository.py` | Event insert / recent / retries support |
| `followups/interested.py` | Qualification / interested outcome helpers |

**Behaviour:**

- Auto post-call: interested + opt-in + approved template → WhatsApp (+ email if present)
- Manual UI (`POST /api/leads/{id}/follow-up`): `require_interested=False`; treats operator click as consent; always attempts WA when phone + template OK
- Success for Meta path requires **wamid**; n8n 200 alone is “queued / deferred”

### 2. Messages / Meta provider

| File | Change |
|------|--------|
| `messages/repository.py` | Integrations CRUD; `set_client_first_contact_template`; n8n-bridge defaults (`bhuvisx_interested_lead_followup` / `en_US`); variables `first_name` + `client_name` |
| `messages/service.py` | Send path uses decrypted secrets / provider factory |
| `messages/providers/meta.py` | Official Graph template/text send; no fake success without credentials |
| `messages/eligibility.py` | Opt-in fail-closed; conversation window rules |
| `messages/inbound.py` | **New.** Inbound tenant resolution (`InboundTenantResult`) for multi-tenant inbox |

### 3. n8n integration / campaign webhooks

| File | Change |
|------|--------|
| `integrations/n8n/payload.py` | Mega_Workflow-compatible `lead_qualified` payload (client/lead/first_contact/template fields) |
| `integrations/n8n/service.py` | POST to resolved webhook; logging |
| `integrations/n8n/routing.py` | **New.** `resolve_campaign_webhook` (campaign-scoped URL/secret) |
| `integrations/n8n/repository.py` | **New.** Workflow registry helpers |
| `integrations/n8n/workflows.py` | **New.** Workflow contract helpers |
| `n8n_webhook.py` | Fire event webhook / outcome→event alignment |
| `api/routes/internal.py` | Webhook configs list/create/update/**delete**/**test** |
| `api/routes/internal_n8n.py` | Expanded n8n admin/internal APIs |
| `api/routes/internal_followups.py` | **New.** Internal follow-up trigger |
| `api/routes/internal_messages.py` | Admin set first-contact template |
| `api/routes/client_leads.py` | Manual follow-up endpoint (`require_interested=False`) |
| `api/routes/campaigns.py` / `leads.py` / `messages.py` | Supporting campaign/lead/message routes |
| `db/postgres.py` | Webhook config CRUD, campaign fields, follow-up helpers |
| `post_call_processor.py` | Hook into follow-up after interested calls |
| `server.py` | Router registration for new routes |

**Admin UI:** `frontend/src/admin/pages/AdminWebhooks.jsx` — CRUD + test for campaign webhooks.

### 4. Frontend (client)

| File | Change |
|------|--------|
| `frontend/src/client/pages/CampaignDetail.jsx` | Manual follow-up button; hooks order fix (no “Rendered more hooks”); follow-up status columns |
| `frontend/src/client/pages/Messages.jsx` | Messages inbox UX |
| `frontend/src/client/client.css` | Layout/style for client pages |
| `frontend/src/App.jsx` / `main.jsx` | Suspense / ErrorBoundary so blank pages fail visibly |
| `frontend/src/utils/leadFieldConfig.js` | **New.** Campaign lead field config helpers |
| `frontend/src/utils/leadSheetColumns.js` | **New.** Lead sheet column defs (incl. follow-up columns) |
| Dashboard / campaigns hooks | Small KPI / filter / data wiring fixes |

### 5. Campaign lead field config

| File | Change |
|------|--------|
| `campaigns/__init__.py` | Package |
| `campaigns/lead_field_config.py` | Per-campaign lead field schema |

### 6. Alembic migrations (untracked — include if DB not yet migrated)

| Migration | Intent |
|-----------|--------|
| `016_merge_whatsapp_and_events.py` | Merge WhatsApp + events heads |
| `017_n8n_workflows.py` | n8n workflow registry |
| `018_campaign_n8n_routing.py` | Campaign→workflow routing |
| `019_campaign_follow_up_target.py` | `follow_up_target` on campaigns |
| `020_campaign_webhook_configs.py` | Campaign webhook configs |
| `021_webhook_legacy_backup_table.py` | Legacy webhook backup |
| `022_campaign_lead_field_config.py` | Lead field config |
| `023_follow_up_event_retries.py` | Follow-up event retries |

Run after deploy: `alembic upgrade head` (verify heads first).

### 7. Docs (product)

| File | Notes |
|------|--------|
| `docs/N8N_WORKFLOW_CONTRACT.md` | Payload / Mega contract |
| `docs/PHASE_0_IMPLEMENTATION_PROMPT.md` | Phase 0 prompt (optional to commit) |

### 8. Tests (commit with product code)

New / updated under `tests/`:

- `test_campaign_webhook_api.py`, `test_campaign_webhook_routing.py`
- `test_channel_eligibility.py`, `test_followup_idempotency.py`
- `test_inbound_tenant_isolation.py`, `test_lead_field_config.py`
- `test_message_delivery_status.py`, `test_meta_webhook_inbound.py`
- `test_n8n_workflow_registry.py`, `test_n8n_workflow_routing.py`
- `test_template_ref.py`, `test_template_registry.py`, `test_whatsapp_delivery.py`
- Updates to `test_followup_api.py`, `test_n8n_integration.py`
- Some older follow-up tests trimmed/replaced (`test_followup_fallback.py`, `test_whatsapp_followup.py`, etc.)

---

## C. Do **not** commit (ops / noise)

- One-off `scripts/_*.py` live patch/send helpers were **deleted** from the tree; only essential scripts remain (see § Scripts kept)
- `*.txt` acceptance/out logs (`full_acceptance_*.txt`, `live_*.txt`, `heal_*.txt`, …)
- `.tmp_active_wa_template`, `.tmp_patched_wa_workflows`
- `Prowave Actual Data.xlsx`
- `__pycache__`, `frontend/dist`, `frontend/node_modules`
- Any `.env` / tokens / passwords

### Scripts kept (essential)

| Script | Role |
|--------|------|
| `cli.py` | Project CLI |
| `db_check.py` / `sqlite_calls.py` / `diag_calls.py` | DB / call diagnostics |
| `e2e_full_pipeline.py` / `e2e_campaign_webhook_acceptance.py` / `run_call_e2e_test.py` / `test_call.py` | Core e2e / call tests |
| `test_n8n_followup_webhook.py` / `smoke_api_pages.py` | Follow-up webhook + API smoke |
| `migrate_script_configs.py` / `reconcile_campaign.py` / `release_stuck_leads.py` / `set_max_concurrent.py` | Ops utilities |
| `plivo_balance.py` / `verify_pg_budget.py` / `import_prowave_campaign.py` | Billing / import helpers |
| `start-local.ps1` / `call.ps1` / `call.sh` | Local run helpers |
| `dev/explain_dialer_indexes.sql` | Dialer index notes |

### External (not in git) — already applied on n8n host

These are **Mega_Workflow11** (`eaiNw08OYt6Y7cJD`) ops changes, not repo files:

- `Send template` node switched to **Meta Graph HTTP** (`POST …/{phone_number_id}/messages`) to avoid n8n WhatsApp node “Bad request”
- Template: `bhuvisx_interested_lead_followup` / `en_US` with **2 body vars** (first name, client name)
- `hello_world` removed as production first-contact default
- If-gates intended to allow **manual** as well as interested (verify on n8n UI before prod traffic)

Campaign webhook URL in use:  
`https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792`

---

## Behaviour summary (what you are shipping)

1. **Branded Meta template** for first WhatsApp touch (not sample `hello_world`).
2. **Any phone** (E.164 / India normalize) can get template messages once opted-in (auto) or via **manual** follow-up.
3. **Manual follow-up** does not require “Interested” outcome; does not fail closed solely on missing opt-in.
4. **Campaign-scoped webhooks** with admin delete/test.
5. **Backend** prefers Meta wamid; otherwise queues to n8n Mega with approved template payload.
6. Frontend Campaign Detail + Messages + Admin Webhooks support the above.

---

## Suggested commit / push flow

```bash
# 1) See what you will include
git status
git diff --stat HEAD

# 2) Stage product paths only (example)
git add \
  api/ followups/ messages/ integrations/n8n/ \
  campaigns/ db/postgres.py n8n_webhook.py post_call_processor.py server.py \
  alembic/versions/016_*.py alembic/versions/017_*.py alembic/versions/018_*.py \
  alembic/versions/019_*.py alembic/versions/020_*.py alembic/versions/021_*.py \
  alembic/versions/022_*.py alembic/versions/023_*.py \
  frontend/src/ docs/N8N_WORKFLOW_CONTRACT.md \
  tests/test_campaign_webhook_*.py tests/test_channel_eligibility.py \
  tests/test_followup_*.py tests/test_inbound_*.py tests/test_lead_field_config.py \
  tests/test_message_delivery_status.py tests/test_meta_webhook_inbound.py \
  tests/test_n8n_workflow_*.py tests/test_template_*.py tests/test_whatsapp_delivery.py \
  tests/test_followup_api.py tests/test_n8n_integration.py

# 3) Commit (when you are ready — do not commit secrets)
git commit -m "$(cat <<'EOF'
Ship campaign WhatsApp follow-ups with branded Meta templates and manual send.

Route interested and manual follow-ups through campaign webhooks, prefer Meta wamid delivery, and keep hello_world out of first contact.
EOF
)"

# 4) Push Nitant
git push -u origin Nitant
```

If you only want to push the **already-committed** 23 commits first:

```bash
git push origin Nitant
```

Then commit **B** in a second push.

---

## Quick file checklist (product)

**Must review before push**

- [ ] `followups/*` (service, eligibility, delivery, templates, registry)
- [ ] `messages/*` (repository first_contact, meta provider, inbound)
- [ ] `integrations/n8n/*` + `n8n_webhook.py`
- [ ] `api/routes/internal.py` (webhook delete/test)
- [ ] `api/routes/client_leads.py` (manual follow-up)
- [ ] `db/postgres.py` + alembic `016`–`023`
- [ ] Frontend CampaignDetail / Messages / AdminWebhooks
- [ ] New tests listed above

**Skip**

- [ ] `scripts/_*.py` live ops
- [ ] `*.txt` / `.tmp_*` / xlsx / dist / node_modules / `.env`

---

## Note

Product behaviour lives in `followups/`, `messages/`, `integrations/n8n/`, and API routes. One-off Mega/Meta live scripts were removed from `scripts/`; pytest coverage remains under `tests/`.

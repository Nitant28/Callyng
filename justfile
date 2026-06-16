# Aakashvani dev commands.
# Run `just`           -> the default recipe (dev server).
# Run `just <name>`    -> any of the named recipes below.
# Run `just --list`    -> show all recipes with their docstrings.

set dotenv-load := true

# Default recipe when you just type `just`
default: dev

# Run the FastAPI server using whatever BOT_ROUTE is set in .env (default: sts)
dev:
    uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload

# Force STS route for this run (overrides .env)
dev-sts:
    BOT_ROUTE=sts uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload

# Force cascaded route for this run (overrides .env)
dev-cascade:
    BOT_ROUTE=cascade uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload

# STS with Hindi script (pyramid_hi under sts_scripts/)
dev-sts-hi:
    STS_SCRIPT=pyramid_hi BOT_ROUTE=sts uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload

# Open the ngrok tunnel using your reserved domain from .env (NGROK_URL)
tunnel:
    ngrok http --domain=$(echo "$NGROK_URL" | sed 's|https://||') 7860

# Trigger an outbound call. Usage: just call +919123866924 Satyam Pune
call phone name="Sir/Madam" city="":
    @curl -sS -X POST "$NGROK_URL/start" \
      -H "Content-Type: application/json" \
      -d '{"phone_number":"{{phone}}","body":{"lead_name":"{{name}}","city":"{{city}}"}}' \
      | (command -v jq >/dev/null && jq . || cat)

# Hit /health on the public URL
health:
    @curl -sS "$NGROK_URL/health" | (command -v jq >/dev/null && jq . || cat)

# Print which route the env is currently set to
route:
    @echo "BOT_ROUTE=${BOT_ROUTE:-sts (default)}"

# Resync the uv environment (useful after the folder rename)
sync:
    uv sync

# ── PostgreSQL (Docker Compose) ─────────────────────────────────────────────

# Start Postgres 16 container (requires Docker Desktop WSL integration or Engine)
db-up:
    docker compose up -d postgres

db-down:
    docker compose down

db-logs:
    docker compose logs -f postgres

# Wait until Postgres accepts connections
db-wait:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Waiting for Postgres..."
    for i in $(seq 1 60); do
      if docker compose exec -T postgres pg_isready -U aakashvani -d aakashvani >/dev/null 2>&1; then
        echo "Postgres ready."
        exit 0
      fi
      sleep 1
    done
    echo "Postgres did not become ready in time." >&2
    exit 1

db-migrate: db-wait
    uv run alembic upgrade head


db-seed: db-wait
    docker compose exec -T postgres psql -U aakashvani -d aakashvani -v ON_ERROR_STOP=1 < db/seed/dev_tenant.sql

db-reset:
    docker compose down -v
    just db-up
    just db-wait
    just db-migrate
    just db-seed

db-psql:
    docker compose exec postgres psql -U aakashvani -d aakashvani

# Verify seed + budget allocation helpers (needs db-up + migrate + seed)
db-verify:
    PYTHONPATH=. uv run python scripts/verify_pg_budget.py

db-check: db-wait
    PYTHONPATH=. uv run python scripts/db_check.py

# ── ADMIN API ─────────────────────────────────────────────────────────────────

create-client name email industry:
    curl -s -X POST http://localhost:7860/internal/clients \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" \
      -H "Content-Type: application/json" \
      -d '{"name":"{{name}}","contact_email":"{{email}}","industry":"{{industry}}"}' | (command -v jq >/dev/null && jq . || cat)

add-credits client_id amount:
    curl -s -X PATCH http://localhost:7860/internal/clients/{{client_id}}/credits \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" \
      -H "Content-Type: application/json" \
      -d '{"amount":{{amount}},"note":"Manual top-up"}' | (command -v jq >/dev/null && jq . || cat)

create-bot client_id name route script_id number credits_per_min:
    curl -s -X POST http://localhost:7860/internal/bot-configs \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" \
      -H "Content-Type: application/json" \
      -d '{"client_id":"{{client_id}}","name":"{{name}}","route":"{{route}}","script_id":"{{script_id}}","telephony_number":"{{number}}","credits_per_minute":{{credits_per_min}}}' | (command -v jq >/dev/null && jq . || cat)

create-campaign client_id bot_config_id name budget:
    curl -s -X POST http://localhost:7860/internal/campaigns \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" \
      -H "Content-Type: application/json" \
      -d '{"client_id":"{{client_id}}","bot_config_id":"{{bot_config_id}}","name":"{{name}}","budget_credits":{{budget}}}' | (command -v jq >/dev/null && jq . || cat)

list-clients:
    curl -s http://localhost:7860/internal/clients \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" | (command -v jq >/dev/null && jq . || cat)

list-calls:
    curl -s http://localhost:7860/internal/calls \
      -H "X-Admin-Key: $(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)" | (command -v jq >/dev/null && jq . || cat)

# ── CLIENT API ────────────────────────────────────────────────────────────────

client-campaigns api_key:
    curl -s http://localhost:7860/api/campaigns \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

upload-leads api_key campaign_id file:
    curl -s -X POST http://localhost:7860/api/campaigns/{{campaign_id}}/leads/upload \
      -H "Authorization: Bearer {{api_key}}" \
      -F "file=@{{file}}" | (command -v jq >/dev/null && jq . || cat)

start-campaign api_key campaign_id:
    curl -s -X PATCH http://localhost:7860/api/campaigns/{{campaign_id}}/start \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

stop-campaign api_key campaign_id:
    curl -s -X PATCH http://localhost:7860/api/campaigns/{{campaign_id}}/stop \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

cancel-campaign api_key campaign_id:
    curl -s -X PATCH http://localhost:7860/api/campaigns/{{campaign_id}}/cancel \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

credits api_key:
    curl -s http://localhost:7860/api/credits \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

watch-call api_key session_call_id:
    curl -s http://localhost:7860/api/calls/{{session_call_id}} \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

# Release leads stuck in ``calling`` (no active Plivo call). Usage: just release-stuck-leads <campaign-uuid>
release-stuck-leads campaign_id:
    PYTHONPATH=. uv run python scripts/release_stuck_leads.py {{campaign_id}}

# Fix denorm campaign counters from actual lead rows (recovery)
reconcile-campaign campaign_id:
    PYTHONPATH=. uv run python scripts/reconcile_campaign.py {{campaign_id}}

# Set Plivo-aligned concurrent dial limit for every client + campaign (default 2)
set-max-concurrent limit="2":
    PYTHONPATH=. uv run python scripts/set_max_concurrent.py {{limit}}

# Show Plivo prepaid cash_credits (USD)
plivo-balance:
    PYTHONPATH=. uv run python scripts/plivo_balance.py

# ── TESTING ───────────────────────────────────────────────────────────────────

test-call phone name="Test Lead" city="Pune":
    BOT_ROUTE={{env_var_or_default("BOT_ROUTE","sts")}} \
    bash scripts/call.sh {{phone}} "{{name}}" "{{city}}"

# CMS pipeline test (script_configs + prefetch + post-call). Usage: just cms-call <uuid> +91... sts
cms-call script_config_id phone route="sts":
    uv run python test_call.py --script-config-id {{script_config_id}} --phone {{phone}} --route {{route}}

# Migrate module scripts into script_configs rows for all clients
migrate-scripts:
    uv run python scripts/migrate_script_configs.py

sqlite-calls n="5":
    uv run python scripts/sqlite_calls.py {{n}}

test-phase2:
    uv run pytest tests/test_phase2.py -v

# ── INSPECTION (direct DB — no server needed) ─────────────────────────────────

# Show client details by name or UUID. Usage: just show-client "Pyramid"
show-client name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py show-client "{{name_or_id}}"

# List bot configs for a client. Usage: just client-bots "Pyramid"
client-bots name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py client-bots "{{name_or_id}}"

# List n8n webhooks for a client. Usage: just client-webhooks "Pyramid"
client-webhooks name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py client-webhooks "{{name_or_id}}"

# List all campaigns for a client with counters
client-campaigns-all name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py client-campaigns "{{name_or_id}}"

# Show full campaign detail (budget, counters, config)
show-campaign name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py show-campaign "{{name_or_id}}"

# List leads in a campaign. Usage: just campaign-leads "Pune Dec" --status pending --limit 10
campaign-leads name_or_id *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py campaign-leads "{{name_or_id}}" {{FLAGS}}

# Recent call logs for a campaign
campaign-calls name_or_id *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py campaign-calls "{{name_or_id}}" {{FLAGS}}

# Full call detail (transcript, extraction, billing). Usage: just show-call <session_call_id>
show-call session_call_id *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py show-call "{{session_call_id}}" {{FLAGS}}

# Show lead detail by UUID or phone number
show-lead id_or_phone:
    PYTHONPATH=. uv run python scripts/cli.py show-lead "{{id_or_phone}}"

# All call history for a phone number across all campaigns
lead-history phone:
    PYTHONPATH=. uv run python scripts/cli.py lead-history "{{phone}}"

# ── POST-CALL DEBUGGING ──────────────────────────────────────────────────────

# Show calls where extraction failed or outcome is null
failed-extractions *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py failed-extractions {{FLAGS}}

# Show calls stuck in_progress beyond grace period
stuck-calls *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py stuck-calls {{FLAGS}}

# Re-run Groq extraction on an existing call transcript
rerun-extraction session_call_id:
    PYTHONPATH=. uv run python scripts/cli.py rerun-extraction "{{session_call_id}}"

# ── OPERATOR ACTIONS ──────────────────────────────────────────────────────────

# Register an n8n webhook for a client. Usage: just register-webhook "Pyramid" "lead_qualified" "http://localhost:5678/webhook/xyz" "secret123"
register-webhook name_or_id event url secret:
    PYTHONPATH=. uv run python scripts/cli.py register-webhook "{{name_or_id}}" "{{event}}" "{{url}}" "{{secret}}"

# Reset a lead to pending with 0 attempts (for retesting)
reset-lead id_or_phone *FLAGS:
    PYTHONPATH=. uv run python scripts/cli.py reset-lead "{{id_or_phone}}" {{FLAGS}}

# Manually set outcome on a call_log + lead
force-outcome session_call_id outcome:
    PYTHONPATH=. uv run python scripts/cli.py force-outcome "{{session_call_id}}" "{{outcome}}"

# Force-settle a campaign and return unused budget to client
settle-campaign name_or_id:
    PYTHONPATH=. uv run python scripts/cli.py settle-campaign "{{name_or_id}}"

# ── LEAD MANAGEMENT (API — server must be running) ───────────────────────────

# Add a single lead to a campaign. Usage: just add-lead <api_key> <campaign_id> +919876543210 "Rahul Sharma"
add-lead api_key campaign_id phone name="" lead_type="cold" metadata="{}":
    curl -s -X POST http://localhost:7860/api/campaigns/{{campaign_id}}/leads \
      -H "Authorization: Bearer {{api_key}}" \
      -H "Content-Type: application/json" \
      -d '{"phone":"{{phone}}","name":"{{name}}","lead_type":"{{lead_type}}","metadata":{{metadata}}}' | (command -v jq >/dev/null && jq . || cat)

# Edit a lead's fields. Usage: just edit-lead <api_key> <campaign_id> <lead_id> --name "New Name"
edit-lead api_key campaign_id lead_id name="" lead_type="" metadata="":
    #!/usr/bin/env bash
    set -euo pipefail
    body="{"
    sep=""
    if [[ -n "{{name}}" ]]; then body+="${sep}\"name\":\"{{name}}\""; sep=","; fi
    if [[ -n "{{lead_type}}" ]]; then body+="${sep}\"lead_type\":\"{{lead_type}}\""; sep=","; fi
    if [[ -n "{{metadata}}" ]]; then body+="${sep}\"metadata\":{{metadata}}"; sep=","; fi
    body+="}"
    curl -s -X PATCH "http://localhost:7860/api/campaigns/{{campaign_id}}/leads/{{lead_id}}" \
      -H "Authorization: Bearer {{api_key}}" \
      -H "Content-Type: application/json" \
      -d "$body" | (command -v jq >/dev/null && jq . || cat)

# Delete a lead. Usage: just delete-lead <api_key> <campaign_id> <lead_id>
delete-lead api_key campaign_id lead_id:
    curl -s -X DELETE http://localhost:7860/api/campaigns/{{campaign_id}}/leads/{{lead_id}} \
      -H "Authorization: Bearer {{api_key}}" | (command -v jq >/dev/null && jq . || cat)

# Manually change a lead's status. Usage: just change-lead-status <api_key> <campaign_id> <lead_id> pending
change-lead-status api_key campaign_id lead_id status scheduled_at="":
    #!/usr/bin/env bash
    set -euo pipefail
    body="{\"status\":\"{{status}}\""
    if [[ -n "{{scheduled_at}}" ]]; then body+=",\"scheduled_at\":\"{{scheduled_at}}\""; fi
    body+="}"
    curl -s -X PATCH "http://localhost:7860/api/campaigns/{{campaign_id}}/leads/{{lead_id}}/status" \
      -H "Authorization: Bearer {{api_key}}" \
      -H "Content-Type: application/json" \
      -d "$body" | (command -v jq >/dev/null && jq . || cat)

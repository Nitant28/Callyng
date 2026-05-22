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
    docker compose exec -T postgres psql -U aakashvani -d aakashvani -v ON_ERROR_STOP=1 < db/schema/001_initial.sql

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

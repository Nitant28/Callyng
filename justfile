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

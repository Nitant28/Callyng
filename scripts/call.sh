#!/usr/bin/env bash
# Trigger an outbound call without requiring `just`.
#
# Usage:
#   scripts/call.sh +919123866924 Satyam Pune
#   scripts/call.sh +919123866924
#
# Reads NGROK_URL from .env in the current directory.

set -euo pipefail

PHONE=${1:?"phone number required (E.164), e.g. +919123866924"}
NAME=${2:-"Sir/Madam"}
CITY=${3:-""}

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

NGROK=${NGROK_URL:?"NGROK_URL not set in .env"}

RESPONSE=$(curl -sS -w "\n%{http_code}" -X POST "$NGROK/start" \
    -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"body\":{\"lead_name\":\"$NAME\",\"city\":\"$CITY\"}}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" -ne 200 && "$HTTP_CODE" -ne 201 ]]; then
    echo "Request failed with HTTP status $HTTP_CODE."
    echo "Check if your NGROK_URL in .env is correct and the server is running."
    echo ""
    echo "Raw Response:"
    echo "$BODY"
    exit 1
fi

if command -v jq >/dev/null; then
    echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
else
    echo "$BODY"
fi

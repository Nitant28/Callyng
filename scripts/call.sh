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

curl -sS -X POST "$NGROK/start" \
    -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"body\":{\"lead_name\":\"$NAME\",\"city\":\"$CITY\"}}" \
    | (command -v jq >/dev/null && jq . || cat)

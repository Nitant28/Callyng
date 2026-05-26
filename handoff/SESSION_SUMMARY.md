# Session Summary: n8n Infrastructure and CLI Enhancements

## Overview
This session focused on two major components:
1. Enhancing operator productivity by moving common database tasks into quick CLI recipes.
2. Building out the n8n internal infrastructure and backend hooks to support robust webhook delivery—most importantly fixing the `campaign_completed` webhook.

## 1. Operator CLI & Just Recipes (`scripts/cli.py` & `justfile`)
To streamline day-to-day operations and prevent manual SQL queries or repetitive copy-pasting of UUIDs, a rich CLI tool was developed.

*   **Fuzzy Search**: Implemented robust resolution logic. You can now pass fuzzy client names, campaign names, or partial phone numbers instead of full UUIDs.
*   **Inspection Commands**: Added commands to view clients, campaigns, bot configs, leads, and call logs with pretty-printed tabular outputs.
    *   `just show-client <name>`, `just client-campaigns <name>`, `just lead-history <phone>`
*   **Operational Commands**:
    *   `just force-outcome <session_id> <outcome>` (manually overrides outcome and fixes lead state).
    *   `just rerun-extraction <session_id>` (re-evaluates Groq transcription).
    *   `just reset-lead <phone>` (resets a lead to pending with 0 attempts).
*   **Webhook Management**:
    *   `just client-webhooks <name>` lists all registered webhooks for a client.
    *   `just register-webhook <client> <event> <url> <secret>` registers an HMAC-signed n8n webhook.

## 2. n8n Infrastructure Integration
*   **Docker Integration**: Added `n8nio/n8n:latest` to `docker-compose.yml`, mapped it to `127.0.0.1:5678` for secure local-only access, and attached an `n8n_data` volume for persistence.
*   **Sample Workflow Template**: Created `fixtures/sample_n8n_workflow.json`. This can be imported into n8n and contains the required Webhook receiver, HMAC-SHA256 crypto node (to calculate the signature of the raw body), and an IF node to verify it against the `X-Aakashvani-Signature` header.

## 3. Webhook Triggers (`campaign_completed`)
A major gap in the post-call settlement flow was that the `campaign_completed` webhook was never firing.

*   **Database Refactor (`db/postgres.py`)**: 
    Modified `try_settle_campaign_budget` and `maybe_auto_settle_campaign` to return a `tuple[Decimal, bool]`. The boolean `just_completed` flag indicates whether the campaign *just* transitioned to a completed state during that exact transaction.
*   **Webhook Firing (`n8n_webhook.py` & `post_call_processor.py`)**:
    Created `fire_campaign_completed_webhook` and wired it into `process_post_call`. Crucially, this webhook is triggered *outside* the active database transaction to ensure safety and prevent stalled transactions if the webhook takes time to dispatch.

## Current State
The backend will now correctly fire signed webhook payloads for lead qualification and campaign completion. These events can be managed easily through the new `just` commands and intercepted locally by the new n8n docker instance for downstream routing.

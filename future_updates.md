# Future Architecture Updates: Path to Enterprise Scale

This document outlines the major architectural upgrades required to take Aakashvani from a single-client pilot to a highly available, multi-tenant enterprise dialer. 

These updates are designed to resolve current single-server bottlenecks and ensure robustness when scaling horizontally.

## 1. Distributed Task Management (Redis / Celery)
**The Problem:** Currently, dialer loops (`asyncio.create_task`) are managed in the local memory of the python process (`_active_tasks` dict). If you run multiple server workers (e.g., Gunicorn with 4 workers) or multiple instances behind a load balancer, a "Start Campaign" request runs the dialer on one worker, but a "Pause Campaign" request might route to a different worker, failing to stop the active dialer.
**The Fix:** 
- Implement a distributed message broker (Redis/RabbitMQ) and a task queue (Celery, ARQ, or Temporal).
- Move the dialer loop out of the main API server and into dedicated dialer worker nodes.
- **Estimated Time to Implement:** 1-2 weeks.

## 2. Global Rate Limiting
**The Problem:** Outbound calls are paced using a localized `asyncio.sleep(60 / cpm)`. If the system is horizontally scaled across 3 servers, a 30 CPM limit effectively becomes 90 CPM.
**The Fix:**
- Implement a Redis-backed token bucket algorithm for global, cross-server rate limiting per client and per campaign.
- **Estimated Time to Implement:** 2-4 days.

## 3. Auto-Resume Campaigns on Server Restart (COMPLETED)
**The Problem:** If the server reboots, deploys an update, or crashes, the local memory is cleared. Campaigns with a `running` status in the database are left frozen because their dialer loops are not automatically restarted.
**The Fix (Applied):**
- Added a startup hook in the server's `lifespan` to query Postgres for all campaigns where `status = 'running'` and auto-launch their dialer tasks.

## 4. Database Connection Pool Scaling (COMPLETED)
**The Problem:** The `asyncpg` connection pool was hardcoded to a maximum of 20 connections, risking connection starvation (`TimeoutError`).
**The Fix (Applied):**
- Exposed the pool size to environment variables (`DB_POOL_MIN`, `DB_POOL_MAX`) defaulting to 5 and 50 respectively.
- Future consideration: Introduce PgBouncer as a connection multiplexer if active connections still exceed Postgres limits.

## 5. Audited Security Logging System
**The Problem:** The "Recent Activity / Security Logs" card on the admin dashboard currently displays mock logs. There is no active backend mechanism to track critical admin operations, API key lifecycle actions, or client credit adjustments, creating a security audit gap.
**The Fix:**
- **Database Schema:** Create a database table `audit_logs` to store UUID identifiers, timestamps, actor types (`admin`, `client`, `system`), event types (e.g., `login_success`, `api_key_regenerate`, `credits_adjusted`), IP addresses, user agents, and context metadata in a JSONB field.
- **Backend Logging Helper:** Implement a global `log_security_event` helper in the backend to capture API key rotations, credit adjustments, onboarding actions, and admin login attempts (including failed attempts for brute-force alerting).
- **Audit Logs API:** Build a new route `GET /internal/audit-logs` that exposes a paginated list of security logs.
- **Frontend Dashboard Integration:** Wire the "Security Logs" component in `AdminOverview.jsx` to fetch recent events from the backend, mapping them to icons (`verified_user`, `lock_reset`, `payments`), and implement a dedicated `/admin/security-logs` page for full administrative audits.
- **Estimated Time to Implement:** 3-5 days.

## 6. Pipecat Analytics & Cost Monitoring Integration
**The Problem:** Currently, the system lacks granular tracing of LLM token usage, execution times, and agent-specific conversational metrics, making cost attribution and performance tuning difficult.
**The Fix:**
- Integrate **OpenInference** (`openinference-instrumentation-pipecat`) for comprehensive LLM tracing, allowing exact cost calculation based on token consumption and execution latency.
- Integrate **Sentry** (`pipecat-ai[sentry]`) to track errors and performance bottlenecks in text-to-speech and LLM requests.
- Explore specialized voice agent platforms (like **Roark** or **Future AGI**) to monitor conversational metrics (e.g., user interruption rates, average conversation lengths) to optimize the AI's behavior and estimate aggregate infrastructure costs.
- **Estimated Time to Implement:** 3-5 days.

## 7. Granular Per-Call Financial Cost Accounting
**The Problem:** While the system deducts internal credits from a client's balance based on a fixed rate, it does not currently compute or store the exact real-world API costs incurred per call (e.g., Plivo SIP minutes, LLM tokens, STT seconds, TTS characters). This makes it impossible to track precise profit margins or identify runaway infrastructure costs per campaign.
**The Fix:**
- **Database Schema Expansion:** Add specific cost-tracking columns to the `call_logs` table: `llm_cost_usd`, `tts_cost_usd`, `stt_cost_usd`, `telephony_cost_usd`, and `total_api_cost_usd`.
- **Pipeline Metrics Interception:** Update the Pipecat agent (`bot.py`) to subscribe to usage metrics events. As the call progresses, intercept the exact number of STT audio seconds processed, LLM input/output tokens generated, and TTS characters synthesized.
- **Dynamic Cost Calculation:** At call termination (or inside the Plivo hangup webhook), calculate the precise costs:
  - Plivo telephony cost (often provided directly in the hangup webhook payload, or computed via exact duration × SIP trunk rate).
  - STT cost = seconds × Deepgram rate.
  - LLM cost = (Input Tokens × input rate) + (Output Tokens × output rate).
  - TTS cost = characters × Cartesia/ElevenLabs rate.
- **Dashboard Profitability Metrics:** Aggregate the `total_api_cost_usd` against the `billed_credits` on the admin dashboard, providing a live "Gross Margin" metric and alerting the admin if a specific campaign is operating at a loss.
- **Estimated Time to Implement:** 2-3 days.

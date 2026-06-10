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

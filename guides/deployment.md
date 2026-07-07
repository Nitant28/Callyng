# Deployment & Production Readiness Guide

This document outlines the comprehensive strategy for deploying the Aakashvani dialer system to a production environment. It covers infrastructure, CI/CD, security, monitoring, and disaster recovery to ensure high availability and stability.

## 1. Infrastructure & Deployment Architecture

### 1.1. Docker & Containerization
- **App Container:** The FastAPI backend runs via Uvicorn. The `Dockerfile` must be finalized to include the `CMD` entrypoint (`uv run uvicorn server:app --host 0.0.0.0 --port 7860 --workers 4`). 
- **Database (PostgreSQL):** Run as a managed service (e.g., AWS RDS, GCP Cloud SQL) in production rather than a Docker container, to ensure automated backups, high availability, and easy scaling.
- **Cache (Redis):** Run via a managed service (e.g., AWS ElastiCache) or an isolated Docker container with persistence enabled.
- **Automation (n8n):** Can run in a separate container, securely isolated from the public internet.

### 1.2. Server Requirements (Hetzner Bare Metal / Cloud)
Since deploying on Hetzner is preferred, here are the minimum and recommended system requirements for running the full stack (Postgres + Redis + App + N8n) on a single node:
- **Minimum (Testing/Small Scale):** 2 vCPUs, 4GB RAM (e.g., Hetzner CPX21 / CX22).
- **Recommended (Production - High Concurrency Dialer):** 4 to 8 vCPUs (Dedicated), 16GB RAM, and NVMe SSDs (e.g., Hetzner CCX33 or an entry-level Bare Metal server).
  - *Note:* The LLM component is highly dependent on Gemini APIs, so your server is mostly handling WebSocket I/O, Database transactions, and concurrent I/O loops. Fast CPU cores and good networking are more important than raw RAM once beyond 8GB.

### 1.3. CI/CD Pipeline (GitHub Actions)
- **Robust Test Suite:** The current test suite should be expanded to include load testing (simulating hundreds of concurrent websocket drops) and strict end-to-end (E2E) integration tests using mock Plivo responses.
- **Environment Independence:** The CI checks and the application code itself must be fully environment-independent. Do not hardcode localhost or ngrok URLs. All base URLs, database hosts, and API keys must explicitly fail-fast on startup if missing from the environment variables.
- **Automated Testing:** Run `uv run pytest` on every PR. Deployments should be blocked if tests fail.
- **Code Quality:** Enforce `uv run ruff check .` and formatters.
- **Container Registry:** On a merge to `main`, the CI pipeline builds the Docker image and pushes it to a private container registry (e.g., AWS ECR, GitHub GHCR).
- **Automated Deployment:** Use a tool like Watchtower, AWS ECS, or a simple webhook on the server to pull the new image and restart the `docker-compose` stack automatically.

## 2. Security & Network Exposure

### 2.1. Domains and Reverse Proxy (Replacing Ngrok)
- **Custom Domain:** You must purchase a domain (e.g., via Cloudflare, Route53, Namecheap) to replace the temporary `ngrok` URLs. Production Plivo webhooks and frontend clients need a permanent, branded host (e.g., `api.yourdomain.com`).
- **Nginx / Caddy:** Do not expose the Uvicorn port (`7860`) directly to the internet. Use a reverse proxy like Nginx or Caddy. Caddy is highly recommended for Hetzner deployments as it automatically provisions and rotates Let's Encrypt SSL certificates.
- **SSL/TLS (HTTPS):** Enforce strict HTTPS. Plivo webhooks and WebSocket audio streams **must** be encrypted.
- **WebSocket Handling:** Ensure the reverse proxy is configured to properly upgrade `Connection: Upgrade` headers for the Gemini/Plivo WebSocket audio streams.

### 2.2. Webhook & Endpoint Security
- **Plivo Webhook Authentication:** Plivo sends an `X-Plivo-Signature` header. The backend must validate this signature using the Auth Token to ensure the payload actually came from Plivo and wasn't spoofed by an attacker.
- **Admin/Internal Endpoints:** Endpoints like `/api/internal/*` or `/api/campaigns/*/release-stuck` must be protected by strict authentication (e.g., API keys, JWT) and ideally restricted by IP whitelisting or placed behind a VPN.
- **Rate Limiting:** Implement rate limiting on public-facing endpoints to prevent DDoS attacks and budget draining.

### 2.3. Secrets Management
- Use a robust secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) or inject `.env` files securely at deployment time via CI/CD. Never commit `.env` or production credentials.

## 3. Monitoring, Logging, & Alerting

### 3.1. Centralized Logging
- The application currently uses `loguru`. This should be configured to output JSON-formatted logs in production.
- Use an agent like Promtail, Filebeat, or AWS CloudWatch to ship these JSON logs to a centralized platform (e.g., Grafana Loki, ELK Stack, Datadog).
- Log critical dialer events clearly (e.g., `campaign_started`, `call_failed`, `budget_exhausted`).

### 3.2. Error Tracking (Sentry)
- Integrate **Sentry** (or a similar tool) into the FastAPI app to capture unhandled exceptions, database timeouts, and background task crashes automatically.

### 3.3. Performance Monitoring (APM)
- Expose a `/metrics` endpoint using Prometheus client libraries.
- Track metrics such as:
  - Active WebSocket connections.
  - Dialer loop iteration times.
  - Lead conversion rates.
  - Database connection pool utilization.

### 3.4. Alerting Rules
Configure alerts (via Slack, PagerDuty, or Email) for the following critical thresholds:
- **High Error Rate:** >5% of HTTP requests returning 5xx.
- **Database Load:** CPU > 80% or Connections > 90% capacity.
- **Dialer Stalls:** If `run_campaign_dialer` logs a failure or silently drops.
- **Plivo Balance:** Low credit warnings to prevent the campaign from stopping unexpectedly.
- **Unusual Hangup Rates:** Spike in immediate hangups (could indicate carrier blocking or invalid caller IDs).

## 4. Data Backup & Disaster Recovery

### 4.1. PostgreSQL Backups
- **Automated Snapshots:** Ensure daily automated snapshots of the Postgres database are enabled.
- **Point-in-Time Recovery (PITR):** Enable WAL (Write-Ahead Log) archiving so the database can be restored to any specific minute in the past 7 days (crucial for recovering from accidental data deletion).

### 4.2. State Recovery
- The Aakashvani backend is designed to be highly resilient (with background maintenance sweeps and atomic counter reconciliations). In the event of a catastrophic server crash, simply rebooting the server will resume paused campaigns, clean up stale calls, and recalculate budget correctly.

## 5. Post-Deployment Tests

After deploying a new version to production, run automated sanity tests:
1. **Health Check:** Ping `/api/health` to ensure the API and Database pool are alive.
2. **Plivo Signature Test:** Send a mock payload to the Plivo hangup webhook endpoint with a valid signature to ensure the webhook validator doesn't reject valid traffic.
3. **Test Call:** Trigger a 1-lead test campaign against an internal phone number to verify that WebSocket audio streaming, LLM latency, and call log database inserts are functioning smoothly.

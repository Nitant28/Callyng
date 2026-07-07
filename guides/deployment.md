# Aakashvani — Complete Deployment Roadmap

> **Audience:** First-time deployers. This guide assumes you know basic Linux terminal commands but have never deployed a production app on a cloud server before. Every step is in order — do not skip ahead.

---

## Table of Contents

1. [Phase 0 — Pre-Flight Checklist](#phase-0--pre-flight-checklist)
2. [Phase 1 — Provision the Server](#phase-1--provision-the-server)
3. [Phase 2 — OS Hardening & Initial Setup](#phase-2--os-hardening--initial-setup)
4. [Phase 3 — Install Docker & Docker Compose](#phase-3--install-docker--docker-compose)
5. [Phase 4 — Domain, DNS & SSL](#phase-4--domain-dns--ssl)
6. [Phase 5 — Secrets & Environment Variables](#phase-5--secrets--environment-variables)
7. [Phase 6 — Database Setup & Migrations](#phase-6--database-setup--migrations)
8. [Phase 7 — Build & Deploy the Backend](#phase-7--build--deploy-the-backend)
9. [Phase 8 — Build & Deploy the Frontend](#phase-8--build--deploy-the-frontend)
10. [Phase 9 — Reverse Proxy (Caddy)](#phase-9--reverse-proxy-caddy)
11. [Phase 10 — n8n Workflow Automation Setup](#phase-10--n8n-workflow-automation-setup)
12. [Phase 11 — Plivo Webhook Configuration](#phase-11--plivo-webhook-configuration)
13. [Phase 12 — Monitoring, Logging & Alerting](#phase-12--monitoring-logging--alerting)
14. [Phase 13 — Backups & Disaster Recovery](#phase-13--backups--disaster-recovery)
15. [Phase 14 — CI/CD Pipeline (GitHub Actions)](#phase-14--cicd-pipeline-github-actions)
16. [Phase 15 — Post-Deployment Verification](#phase-15--post-deployment-verification)
17. [Phase 16 — Rollback Procedure](#phase-16--rollback-procedure)
18. [Appendix A — Complete Environment Variable Reference](#appendix-a--complete-environment-variable-reference)
19. [Appendix B — Port Map](#appendix-b--port-map)
20. [Appendix C — External Service Dependencies](#appendix-c--external-service-dependencies)

---

## Phase 0 — Pre-Flight Checklist

Before you touch a server, make sure ALL of the following are ready. Missing any one of these will block you later.

### Accounts & API Keys You Must Have
| Service | What You Need | Where to Get It |
|---------|--------------|-----------------|
| **Hetzner** | Account + payment method | [hetzner.com](https://www.hetzner.com) |
| **Domain Registrar** | A purchased domain (e.g., `aakashvani.ai`) | Cloudflare / Namecheap / Route53 |
| **GitHub** | Repository access + a Personal Access Token (PAT) with `packages:write` | [github.com/settings/tokens](https://github.com/settings/tokens) |
| **Plivo** | `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, a purchased phone number | [plivo.com/console](https://console.plivo.com) |
| **Google Cloud** | `GOOGLE_API_KEY` with Gemini Live API enabled | [aistudio.google.com](https://aistudio.google.com) |
| **Groq** | `GROQ_API_KEY` (if using cascaded mode) | [console.groq.com](https://console.groq.com) |
| **Sarvam AI** | `SARVAM_API_KEY` (if using cascaded mode) | [sarvam.ai](https://www.sarvam.ai) |
| **Cartesia** | `CARTESIA_API_KEY` + `CARTESIA_VOICE_ID` | [cartesia.ai](https://cartesia.ai) |
| **Deepgram** | `DEEPGRAM_API_KEY` (optional, alternative STT) | [deepgram.com](https://deepgram.com) |

### Items to Decide Before Starting
- [ ] **Production domain name** — e.g., `api.aakashvani.ai` for the backend, `app.aakashvani.ai` for the client dashboard, `admin.aakashvani.ai` for the admin panel.
- [ ] **Hosting provider** — Hetzner (Europe/Singapore) or **Hostinger (Mumbai, India)** — see comparison below.
- [ ] **Bot mode** — `sts` (Gemini speech-to-speech) or `cascaded` (Groq + Sarvam + Cartesia). This decides which API keys are required.
- [ ] **Admin API key** — Generate one now: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Server Provider Comparison

#### Why Latency Matters
Aakashvani makes outbound calls to Indian phone numbers via Plivo. The call audio streams through WebSockets between your server and the AI provider (Gemini/Groq). Lower latency = faster bot responses = more natural conversations. An India-based server shaves **80-150ms** off every round trip compared to European servers.

#### Option A: Hostinger VPS (Mumbai, India) — ⭐ Recommended for India

| Tier | Spec | Hostinger Plan | Promo Price | Renewal Price |
|------|------|---------------|-------------|---------------|
| **Minimum** | 2 vCPU, 8 GB RAM, 100 GB NVMe | KVM 2 | ~₹519/mo (48-month term) | ~₹1,199/mo |
| **Recommended** | 4 vCPU, 16 GB RAM, 200 GB NVMe | KVM 4 | ~₹1,099/mo (24-month term) | ~₹2,399/mo |
| **Heavy** | 8 vCPU, 32 GB RAM, 400 GB NVMe | KVM 8 | ~₹2,099/mo (24-month term) | ~₹4,799/mo |

**Pros:**
- 🇮🇳 **Mumbai data center** — ~5-15ms to Indian telecom networks and Plivo's India PoPs
- AMD EPYC processors, NVMe SSDs, 1 Gbps network
- Built-in DDoS protection (Wanguard)
- Free weekly backups + snapshot support
- Browser-based terminal and Docker Compose manager in their panel

**Cons:**
- ⚠️ Promotional pricing requires **long-term commitment** (24-48 months upfront). Always check the renewal price before buying.
- KVM VPS is **unmanaged** — you handle all server admin (same as Hetzner)
- Smaller community/ecosystem compared to Hetzner

> **Important:** When purchasing, go to the final checkout page and look at the "Renewal Price" line before committing. The headline price is always the multi-year prepaid rate.

#### Option B: Hetzner Cloud (Singapore / Europe)

| Tier | Spec | Hetzner Plan | Monthly Cost |
|------|------|-------------|-------------|
| **Minimum** | 2 vCPU (shared), 4 GB RAM, 40 GB NVMe | CX22 | ~€4/mo |
| **Recommended** | 4 vCPU (dedicated), 16 GB RAM, 160 GB NVMe | CCX23 | ~€30/mo |
| **Heavy** | 8 vCPU (dedicated), 32 GB RAM, 240 GB NVMe | CCX33 | ~€60/mo |

**Pros:**
- No lock-in — pay monthly, cancel anytime
- Excellent price-to-performance ratio in Europe
- Singapore DC available (~60-80ms to India)
- Hetzner Storage Boxes for cheap off-site backups
- Large DevOps community, tons of guides/tutorials

**Cons:**
- ❌ **No India data center** — closest is Singapore (~60-80ms) or Europe (~120-200ms to India)
- Singapore DC has limited plan selection compared to Germany

#### Latency Comparison (to Indian callers)

| Provider & Location | Ping to India | Impact on Bot Response |
|--------------------|--------------|------------------------|
| **Hostinger Mumbai** | **5-15ms** | ✅ Near-instant, most natural |
| Hetzner Singapore | 60-80ms | ⚠️ Acceptable, slight delay |
| Hetzner Germany | 120-200ms | ❌ Noticeable lag in conversation |

> **Recommendation:** If your callers are in India, go with **Hostinger KVM 4 (Mumbai)**. The latency difference directly impacts how natural the AI sounds on the phone. If you need month-to-month flexibility or plan to scale to multi-region, go with Hetzner Singapore.

> **Why these specs?** The app is mostly I/O-bound (WebSocket audio streaming, Plivo REST calls, Gemini API). CPU matters more than RAM once you're past 8 GB. NVMe SSDs are critical for PostgreSQL performance.

---

## Phase 1 — Provision the Server

Follow the path for your chosen provider. Both result in the same thing: an Ubuntu server with a public IP that you can SSH into.

### Path A: Hostinger VPS (Mumbai — Recommended for India)

#### Step 1.1a — Purchase the VPS
1. Go to [hostinger.in/vps-hosting](https://www.hostinger.in/vps-hosting).
2. Select the **KVM 4** plan (4 vCPU, 16 GB RAM, 200 GB NVMe).
3. On the checkout page:
   - ⚠️ **Check the renewal price** before paying. Select the commitment term you're comfortable with.
   - Complete payment.
4. In the **hPanel dashboard**, click your new VPS.
5. Under **Operating System**, install **Ubuntu 24.04 LTS**.
6. Under **SSH Keys**, add your public SSH key (`ssh-keygen -t ed25519` if you don't have one).
7. Set the **Data Center** to **Mumbai, India**.
8. Note down the server's **public IPv4 address**.

#### Step 1.2a — Hostinger Firewall
Hostinger includes a built-in firewall manager in hPanel:
1. Go to **hPanel** → Your VPS → **Firewall**.
2. Add these rules:

| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 22 | Your IP only | SSH access |
| Inbound | TCP | 80 | Any | HTTP (Caddy redirect) |
| Inbound | TCP | 443 | Any | HTTPS (all traffic) |

3. Block everything else. PostgreSQL (5432), Redis (6379), n8n (5678) must NEVER be exposed.

### Path B: Hetzner Cloud (Singapore or Europe)

#### Step 1.1b — Create the Server
1. Log into [Hetzner Cloud Console](https://console.hetzner.cloud).
2. Create a new **Project** (e.g., `aakashvani-prod`).
3. Click **Add Server**:
   - **Location:** `Singapore` (lowest latency to India). Fall back to `Falkenstein` if Singapore plans are unavailable.
   - **Image:** `Ubuntu 24.04 LTS`
   - **Type:** `CCX23` (recommended) or higher.
   - **SSH Key:** Upload your public SSH key.
   - **Networking:** Enable IPv4 and IPv6.
   - **Firewall:** Create a firewall (see below).
   - **Name:** `aakashvani-prod-1`
4. Click **Create & Buy Now**.
5. Note down the server's **public IPv4 address**.

#### Step 1.2b — Hetzner Firewall Rules
Create a firewall in Hetzner Cloud and attach it to your server. Allow ONLY:

| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 22 | Your IP only | SSH access |
| Inbound | TCP | 80 | Any | HTTP (Caddy auto-redirect to HTTPS) |
| Inbound | TCP | 443 | Any | HTTPS (all traffic) |
| Outbound | All | All | Any | Allow all outbound (API calls, etc.) |

> **Everything else is blocked.** PostgreSQL (5432), Redis (6379), n8n (5678) are NEVER exposed to the internet.

---

## Phase 2 — OS Hardening & Initial Setup

SSH into your server for the first time:
```bash
ssh root@YOUR_SERVER_IP
```

### Step 2.1 — System Updates
```bash
apt update && apt upgrade -y
apt install -y curl wget git unzip fail2ban ufw htop
```

### Step 2.2 — Create a Non-Root User
Never run your app as root.
```bash
adduser deploy
usermod -aG sudo deploy

# Copy SSH key to the new user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### Step 2.3 — Disable Root SSH Login & Password Auth
```bash
nano /etc/ssh/sshd_config
```
Set these values:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```
Restart SSH:
```bash
systemctl restart sshd
```

> ⚠️ **Before you log out**, open a NEW terminal and test SSH as the `deploy` user:
> ```bash
> ssh deploy@YOUR_SERVER_IP
> ```
> If this fails, DO NOT log out of your root session.

### Step 2.4 — Configure UFW (Host Firewall)
This is a second layer of defense on top of the Hetzner cloud firewall.
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable
```

### Step 2.5 — Configure Fail2Ban
Protects against SSH brute-force attacks.
```bash
systemctl enable fail2ban
systemctl start fail2ban
```

### Step 2.6 — Set Timezone & Hostname
```bash
timedatectl set-timezone Asia/Kolkata
hostnamectl set-hostname aakashvani-prod
```

### Step 2.7 — Enable Automatic Security Updates
```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" when prompted
```

---

## Phase 3 — Install Docker & Docker Compose

All commands from here should be run as the `deploy` user (`ssh deploy@YOUR_SERVER_IP`).

### Step 3.1 — Install Docker Engine
```bash
# Official Docker install script
curl -fsSL https://get.docker.com | sudo sh

# Add deploy user to docker group (no sudo needed for docker commands)
sudo usermod -aG docker deploy

# Log out and back in for group change to take effect
exit
ssh deploy@YOUR_SERVER_IP

# Verify
docker --version
docker compose version
```

### Step 3.2 — Configure Docker Daemon
```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  },
  "storage-driver": "overlay2"
}
EOF
sudo systemctl restart docker
```
> This prevents Docker logs from filling up the disk.

---

## Phase 4 — Domain, DNS & SSL

### Step 4.1 — Purchase & Configure Your Domain
If you haven't already, buy a domain from Cloudflare, Namecheap, or any registrar.

### Step 4.2 — Set Up DNS Records
Go to your domain registrar's DNS management panel and add these **A records**:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `api` | `YOUR_SERVER_IP` | 300 |
| A | `app` | `YOUR_SERVER_IP` | 300 |
| A | `admin` | `YOUR_SERVER_IP` | 300 |
| A | `n8n` | `YOUR_SERVER_IP` | 300 |

This gives you:
- `api.yourdomain.com` → Backend API + Plivo webhooks
- `app.yourdomain.com` → Client dashboard (React SPA)
- `admin.yourdomain.com` → Admin panel (React SPA)
- `n8n.yourdomain.com` → n8n workflow automation UI (Caddy-proxied, not public)

> **If using Cloudflare:** Set the proxy status to **DNS Only** (grey cloud) initially, not "Proxied" (orange cloud). Caddy needs to reach the server directly for SSL certificate provisioning. You can enable the Cloudflare proxy later after SSL is confirmed working.

### Step 4.3 — Verify DNS Propagation
Wait a few minutes, then verify:
```bash
dig api.yourdomain.com +short
# Should return YOUR_SERVER_IP
```

> SSL certificates are handled automatically by Caddy in Phase 9. You don't need to manually set up Let's Encrypt.

---

## Phase 5 — Secrets & Environment Variables

### Step 5.1 — Create the Project Directory
```bash
sudo mkdir -p /opt/aakashvani
sudo chown deploy:deploy /opt/aakashvani
cd /opt/aakashvani
```

### Step 5.2 — Create the Production `.env` File
```bash
nano /opt/aakashvani/.env
```

Use this template — fill in every value marked `FILL_IN`:

```env
# ── SERVER ──────────────────────────────────────────────────────
# CRITICAL: Replace NGROK_URL with your production domain.
# This is used by Plivo to reach your webhooks.
NGROK_URL=https://api.yourdomain.com

# Override if different from NGROK_URL (usually not needed)
# DIALER_CALLBACK_HOST=https://api.yourdomain.com

PLIVO_HANGUP_CALLBACK_ENABLED=true

# ── DATABASE ────────────────────────────────────────────────────
DATABASE_URL=postgresql://aakashvani:FILL_IN_STRONG_PASSWORD@localhost:5432/aakashvani
REDIS_URL=redis://localhost:6379/0
DB_POOL_MIN=5
DB_POOL_MAX=50
CALL_LOG_DB_PATH=./data/call_logs.db

# ── ADMIN ───────────────────────────────────────────────────────
ADMIN_API_KEY=FILL_IN_GENERATED_KEY

# ── BOT ROUTING ─────────────────────────────────────────────────
BOT_ROUTE=sts
STS_SCRIPT=pyramid_mr
CASCADE_SCRIPT=prowave

# ── TELEPHONY (Plivo) ──────────────────────────────────────────
PLIVO_AUTH_ID=FILL_IN
PLIVO_AUTH_TOKEN=FILL_IN
PLIVO_PHONE_NUMBER=FILL_IN
PLIVO_MIN_BALANCE_USD=0.50
PLIVO_BALANCE_CACHE_SECONDS=30

# ── MAINTENANCE ─────────────────────────────────────────────────
STALE_CALL_LOG_SWEEP_ENABLED=true
STALE_CALL_LOG_SWEEP_SECONDS=300
MAX_CALL_MINUTES=10

# ── AI PROVIDERS ────────────────────────────────────────────────
GOOGLE_API_KEY=FILL_IN
GROQ_API_KEY=FILL_IN
SARVAM_API_KEY=FILL_IN
CARTESIA_API_KEY=FILL_IN
DEEPGRAM_API_KEY=
CARTESIA_VOICE_ID=FILL_IN
OPENAI_API_KEY=
POST_CALL_MODEL=llama-3.3-70b-versatile

# ── PIPELINE TUNING ────────────────────────────────────────────
GEMINI_CONTEXT_COMPRESSION=1
GEMINI_CWC_TRIGGER_TOKENS=20000
USD_INR=84.0

# ── WEBHOOKS (n8n) ──────────────────────────────────────────────
# N8N_WEBHOOK_URL=http://localhost:5678/webhook/your-path
# N8N_WEBHOOK_SECRET=
# N8N_WEBHOOK_TIMEOUT_S=30

# ── STORAGE (Cloudflare R2 — optional) ──────────────────────────
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=aakashvani-recordings

# ── PAYMENTS (future) ──────────────────────────────────────────
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
```

### Step 5.3 — Lock Down File Permissions
```bash
chmod 600 /opt/aakashvani/.env
```
> Only the `deploy` user can read this file. No other user or process on the system can see your secrets.

### Step 5.4 — Generate the Strong Postgres Password
```bash
# Generate a 32-character password
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste this into the DATABASE_URL in .env
```

### Step 5.5 — Generate the Admin API Key
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste this into ADMIN_API_KEY in .env
```

---

## Phase 6 — Database Setup & Migrations

### Step 6.1 — Create the Production `docker-compose.yml`
```bash
nano /opt/aakashvani/docker-compose.yml
```

```yaml
services:
  postgres:
    image: postgres:16
    container_name: aakashvani-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: aakashvani
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # Set in .env
      POSTGRES_DB: aakashvani
    ports:
      - "127.0.0.1:5432:5432"   # Bind to localhost ONLY
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aakashvani -d aakashvani"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    image: redis:7
    container_name: aakashvani-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "127.0.0.1:6379:6379"   # Bind to localhost ONLY
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  n8n:
    image: n8nio/n8n:latest
    container_name: aakashvani-n8n
    restart: unless-stopped
    ports:
      - "127.0.0.1:5678:5678"
    environment:
      - N8N_HOST=n8n.yourdomain.com
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - NODE_ENV=production
      - GENERIC_TIMEZONE=Asia/Kolkata
      - N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
      - WEBHOOK_URL=https://n8n.yourdomain.com/   # Critical: must match your public URL
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}   # Encrypt credentials at rest
    volumes:
      - n8n_data:/home/node/.n8n
    deploy:
      resources:
        limits:
          memory: 1G

volumes:
  pgdata:
  redisdata:
  n8n_data:
```

> **Key differences from the dev compose file:**
> - Postgres and Redis ports bind to `127.0.0.1` only (not exposed to the internet).
> - Redis has a password.
> - Postgres password is pulled from an env var (not hardcoded `devpassword`).
> - Resource limits prevent runaway memory usage.

### Step 6.2 — Add Postgres and Redis Passwords to `.env`
Add these two lines to your `/opt/aakashvani/.env`:
```env
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD_HERE
REDIS_PASSWORD=YOUR_REDIS_PASSWORD_HERE
```
And update `DATABASE_URL` and `REDIS_URL` accordingly:
```env
DATABASE_URL=postgresql://aakashvani:YOUR_STRONG_PASSWORD_HERE@localhost:5432/aakashvani
REDIS_URL=redis://:YOUR_REDIS_PASSWORD_HERE@localhost:6379/0
```

### Step 6.3 — Start the Database Services
```bash
cd /opt/aakashvani
docker compose --env-file .env up -d postgres redis
```

Verify they're healthy:
```bash
docker compose ps
# Both should show "healthy"
```

### Step 6.4 — Run Alembic Migrations
You'll need Python + uv on the server to run migrations. Two options:

**Option A — Run migrations from a local machine** (recommended for first deploy):
```bash
# On your local dev machine, with DATABASE_URL pointing to the production DB
# (requires SSH tunnel)
ssh -L 5432:localhost:5432 deploy@YOUR_SERVER_IP

# In another terminal, run migrations locally:
DATABASE_URL=postgresql://aakashvani:PASSWORD@localhost:5432/aakashvani \
  uv run alembic upgrade head
```

**Option B — Install uv on the server:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone the repo
cd /opt/aakashvani
git clone https://github.com/YOUR_ORG/aakashvani.git app
cd app

# Run migrations
uv run alembic upgrade head
```

### Step 6.5 — Verify the Database
```bash
docker exec -it aakashvani-postgres psql -U aakashvani -d aakashvani \
  -c "\dt"
```
You should see tables: `clients`, `campaigns`, `leads`, `call_logs`, `bot_configs`, `credit_transactions`, `script_configs`, `script_config_revisions`, `alembic_version`.

---

## Phase 7 — Build & Deploy the Backend

### Step 7.1 — Finalize the Dockerfile
The current Dockerfile is missing a `CMD` directive and health check. Create an updated production Dockerfile:

```bash
nano /opt/aakashvani/app/Dockerfile.prod
```

```dockerfile
FROM dailyco/pipecat-base:latest

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

WORKDIR /app
COPY . /app

# Create data directory for SQLite fallback
RUN mkdir -p /app/data

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
```

> **Why `--workers 1`?** The dialer uses in-memory `asyncio.Task` tracking. Multiple workers would break campaign start/stop routing. This is documented in `future_updates.md` (item #1) as a future upgrade to distributed task management.

### Step 7.2 — Build the Docker Image
```bash
cd /opt/aakashvani/app
docker build -f Dockerfile.prod -t aakashvani-backend:latest .
```

### Step 7.3 — Add the Backend to docker-compose
Add this to `/opt/aakashvani/docker-compose.yml` under `services:`:

```yaml
  backend:
    image: aakashvani-backend:latest
    container_name: aakashvani-backend
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "127.0.0.1:7860:7860"   # Bind to localhost ONLY — Caddy proxies this
    volumes:
      - backend_data:/app/data   # SQLite fallback + any local files
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7860/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits:
          memory: 4G
```

Add `backend_data:` to the `volumes:` section at the bottom.

### Step 7.4 — Start the Backend
```bash
cd /opt/aakashvani
docker compose --env-file .env up -d backend
```

Verify:
```bash
docker compose logs -f backend --tail=50
# Look for "Uvicorn running on http://0.0.0.0:7860"

curl http://localhost:7860/health
# Should return {"status": "ok", ...}
```

---

## Phase 8 — Build & Deploy the Frontend

### Step 8.1 — Build the React SPA
On your local machine (or in CI):
```bash
cd frontend

# Install dependencies
npm ci

# Build for production (no API base URL needed — same-origin via reverse proxy)
VITE_API_BASE_URL='' npm run build
```

This produces a `frontend/dist/` folder containing static HTML/CSS/JS files.

### Step 8.2 — Upload the Build to the Server
```bash
# From your local machine
rsync -avz --delete frontend/dist/ deploy@YOUR_SERVER_IP:/opt/aakashvani/frontend-dist/
```

> The frontend is served as static files by Caddy. No Node.js server needed in production.

---

## Phase 9 — Reverse Proxy (Caddy)

Caddy is the single public-facing entry point. It handles HTTPS certificates, routes traffic to the backend, and serves the frontend static files.

### Step 9.1 — Install Caddy
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### Step 9.2 — Create the Caddyfile
```bash
sudo nano /etc/caddy/Caddyfile
```

```caddyfile
# ── Backend API ──────────────────────────────────────────────────
api.yourdomain.com {
    # Plivo webhooks + API endpoints
    reverse_proxy localhost:7860

    # WebSocket support (critical for audio streaming)
    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websockets localhost:7860

    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    }

    # Request size limit (for CSV uploads)
    request_body {
        max_size 50MB
    }

    log {
        output file /var/log/caddy/api-access.log {
            roll_size 100mb
            roll_keep 10
        }
    }
}

# ── Client Dashboard (React SPA) ────────────────────────────────
app.yourdomain.com {
    root * /opt/aakashvani/frontend-dist

    # API calls proxied to backend
    reverse_proxy /api/* localhost:7860

    # Try files, fallback to index.html for SPA routing
    try_files {path} /index.html
    file_server

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options SAMEORIGIN
        Referrer-Policy strict-origin-when-cross-origin
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    }

    log {
        output file /var/log/caddy/app-access.log {
            roll_size 100mb
            roll_keep 10
        }
    }
}

# ── Admin Dashboard (React SPA) ─────────────────────────────────
admin.yourdomain.com {
    root * /opt/aakashvani/frontend-dist

    # Internal API calls proxied to backend
    reverse_proxy /api/* localhost:7860
    reverse_proxy /internal/* localhost:7860

    try_files {path} /index.html
    file_server

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options SAMEORIGIN
        Referrer-Policy strict-origin-when-cross-origin
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    }

    log {
        output file /var/log/caddy/admin-access.log {
            roll_size 100mb
            roll_keep 10
        }
    }
}
```

### Step 9.3 — Create Log Directory & Start Caddy
```bash
sudo mkdir -p /var/log/caddy
sudo systemctl restart caddy
sudo systemctl enable caddy
```

### Step 9.4 — Verify SSL
```bash
curl -I https://api.yourdomain.com/health
# Should return HTTP/2 200 with valid SSL
```

Caddy automatically provisions Let's Encrypt certificates. If it fails, check:
```bash
sudo journalctl -u caddy --no-pager -n 50
```

---

## Phase 10 — n8n Workflow Automation Setup

n8n is the workflow automation engine that receives post-call webhooks from Aakashvani and routes them to CRMs, Google Sheets, Slack, or any external service. It runs as a Docker container on the same server but is never exposed directly to the internet — Caddy proxies it.

### How n8n Integrates with Aakashvani

The backend fires webhooks to n8n at two levels:
1. **Phase 0 (Global fallback):** When `N8N_WEBHOOK_URL` is set in `.env`, ALL completed calls send a `call_completed` payload to that URL.
2. **Phase 2 (Per-client/per-event):** Each client can have their own webhook URLs configured in the database (via the admin CLI: `uv run python scripts/cli.py register-webhook`). Events like `lead_qualified`, `lead_callback`, `lead_failed`, and `campaign_completed` each fire to their own configured endpoint.

Payloads are signed with HMAC-SHA256 using the `X-Aakashvani-Signature` header (if `N8N_WEBHOOK_SECRET` or per-client secret is configured), so n8n can verify authenticity.

### Step 10.1 — Generate the n8n Encryption Key
n8n encrypts stored credentials (API keys, OAuth tokens) at rest. You MUST set a persistent encryption key, otherwise n8n generates a random one on first boot and all credentials are lost if the container is recreated.

```bash
# Generate and add to your .env
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 24)" >> /opt/aakashvani/.env
```

> ⚠️ **Back up this key.** If you lose it, all saved n8n credentials become unrecoverable.

### Step 10.2 — Start n8n
```bash
cd /opt/aakashvani
docker compose --env-file .env up -d n8n

# Verify it's running
docker compose logs n8n --tail=20
# Look for "n8n ready on 0.0.0.0, port 5678"
```

### Step 10.3 — Add n8n to Caddy (Reverse Proxy)
Add this block to your `/etc/caddy/Caddyfile`:

```caddyfile
# ── n8n Workflow Automation ──────────────────────────────────────
n8n.yourdomain.com {
    reverse_proxy localhost:5678

    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options SAMEORIGIN
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    }

    log {
        output file /var/log/caddy/n8n-access.log {
            roll_size 50mb
            roll_keep 5
        }
    }
}
```

Then reload Caddy:
```bash
sudo systemctl reload caddy
```

> **Don't forget** to add a DNS A record for `n8n.yourdomain.com` pointing to your server IP (same as Phase 4).

### Step 10.4 — Initial n8n Setup
1. Open `https://n8n.yourdomain.com` in your browser.
2. Create your **admin account** (first user becomes the owner).
3. Set a strong password — this UI has full access to all your workflows and credentials.

### Step 10.5 — Configure the Aakashvani → n8n Webhook
In n8n:
1. Create a new workflow.
2. Add a **Webhook** trigger node.
3. Set the HTTP Method to `POST`.
4. Copy the webhook URL (e.g., `https://n8n.yourdomain.com/webhook/abc123`).

In your server `.env`:
```env
N8N_WEBHOOK_URL=https://n8n.yourdomain.com/webhook/abc123
N8N_WEBHOOK_SECRET=your-hmac-secret-here
N8N_WEBHOOK_TIMEOUT_S=30
```

Then restart the backend:
```bash
docker compose --env-file .env restart backend
```

### Step 10.6 — Webhook Payload Reference

When a call completes, n8n receives a JSON payload like this:
```json
{
  "event": "lead_qualified",
  "call": {
    "session_call_id": "uuid",
    "duration_seconds": 120,
    "billed_minutes": 2,
    "credits_charged": 4.5,
    "route": "sts",
    "recording_url": "https://..."
  },
  "lead": {
    "phone": "+91XXXXXXXXXX",
    "name": "John Doe",
    "lead_type": "new",
    "metadata": { "company": "Acme Corp" }
  },
  "extraction": {
    "intent_status": "Interested",
    "summary": "Customer wants a demo next week...",
    "next_steps": "Schedule demo for Monday"
  },
  "campaign": {
    "id": "uuid",
    "name": "Q3 Outreach"
  }
}
```

Available events: `lead_qualified`, `lead_not_interested`, `lead_callback`, `lead_failed`, `campaign_completed`.

### Step 10.7 — n8n Security Hardening

- [ ] **Restrict access:** If n8n is only used by your team, add IP whitelisting in Caddy:
  ```caddyfile
  n8n.yourdomain.com {
      @blocked not remote_ip YOUR_OFFICE_IP
      respond @blocked 403
      reverse_proxy localhost:5678
  }
  ```
- [ ] **Webhook authentication:** Always set `N8N_WEBHOOK_SECRET` so the backend signs payloads. In n8n, add a **Header Auth** credential to verify `X-Aakashvani-Signature`.
- [ ] **Disable public registration:** After creating your admin account, set `N8N_USER_MANAGEMENT_DISABLED=true` in the docker-compose environment to prevent signup.

### Step 10.8 — n8n Backup
n8n stores workflows and credentials in SQLite inside the Docker volume. Back it up:
```bash
# Add to your backup script (/opt/aakashvani/backup.sh):
docker exec aakashvani-n8n n8n export:workflow --all --output=/tmp/n8n-workflows.json 2>/dev/null
docker cp aakashvani-n8n:/tmp/n8n-workflows.json /opt/aakashvani/backups/n8n-workflows-$(date +%Y%m%d).json
```

> **Pro tip:** You can also export workflows from the n8n UI → Settings → Export, and store them in your Git repo for version control.

---

## Phase 11 — Plivo Webhook Configuration

This is **critical**. Without this, calls won't work.

### Step 10.1 — Update Your `.env`
Make sure this is set:
```env
NGROK_URL=https://api.yourdomain.com
```

> Yes, the env var is still called `NGROK_URL` for backward compatibility. It's the public URL Plivo uses to reach your server.

### Step 10.2 — Configure Plivo Application
1. Log into [Plivo Console](https://console.plivo.com).
2. Go to **Voice** → **Applications** → **Create Application**.
3. Set:
   - **Answer URL:** `https://api.yourdomain.com/answer` (HTTP POST)
   - **Hangup URL:** `https://api.yourdomain.com/plivo-hangup` (HTTP POST)
4. Assign your phone number to this application.

### Step 10.3 — Verify Webhook Connectivity
```bash
# From any machine, hit the answer endpoint directly
curl -X POST https://api.yourdomain.com/answer?call_id=test
# Should return Plivo XML (even if it's an error response, it proves connectivity)
```

### Step 10.4 — (Recommended) Enable Plivo Signature Validation
In production, validate that webhooks genuinely came from Plivo by checking the `X-Plivo-Signature-V3` header against your `PLIVO_AUTH_TOKEN`. This prevents spoofed webhook attacks.

---

## Phase 12 — Monitoring, Logging & Alerting

### Step 11.1 — Structured JSON Logging
The app uses `loguru`. In production, configure it to output JSON:
```env
# Add to .env
LOG_FORMAT=json
```

Application logs are accessible via:
```bash
docker compose logs -f backend --tail=100
```

### Step 11.2 — System Monitoring (htop + Docker Stats)
For basic monitoring:
```bash
# Real-time system resources
htop

# Docker container resource usage
docker stats --no-stream
```

### Step 11.3 — Log Rotation
Docker log rotation is already configured (Phase 3.2). For Caddy logs:
```bash
# Caddy handles its own log rotation via the Caddyfile config above
```

### Step 11.4 — Health Check Monitoring
Set up a free uptime monitor (e.g., [UptimeRobot](https://uptimerobot.com) or [Betterstack](https://betterstack.com)):
- Monitor `https://api.yourdomain.com/health` every 60 seconds.
- Alert via email/Slack if it goes down.

### Step 11.5 — Sentry Error Tracking (Recommended)
1. Create a free account at [sentry.io](https://sentry.io).
2. Create a Python project and get the DSN.
3. Add to `.env`:
   ```env
   SENTRY_DSN=https://your-key@sentry.io/your-project-id
   ```
4. The backend should be updated to initialize Sentry in `server.py` lifespan.

### Step 11.6 — Critical Alert Checklist
Set up alerts (via UptimeRobot, Sentry, or a custom script) for:

| Alert | Threshold | Priority |
|-------|-----------|----------|
| **API down** | Health check fails 3x in a row | 🔴 Critical |
| **High error rate** | >5% of requests return 5xx | 🔴 Critical |
| **Plivo balance low** | Cash credits < $5 | 🟡 Warning |
| **Disk usage high** | >85% full | 🟡 Warning |
| **Database connections saturated** | Pool >90% utilized | 🟡 Warning |
| **Container OOM killed** | Docker restart event | 🔴 Critical |
| **SSL certificate expiry** | <14 days until expiry | 🟡 Warning |

### Step 11.7 — Simple Disk & Docker Health Cron
Create a basic monitoring script:
```bash
sudo nano /opt/aakashvani/monitor.sh
```

```bash
#!/bin/bash
# Simple health check script — add to crontab

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/health)
DISK=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$HEALTH" != "200" ]; then
    echo "$(date) ALERT: Backend health check failed (HTTP $HEALTH)" >> /var/log/aakashvani-monitor.log
    # Add notification here (email, Slack webhook, etc.)
fi

if [ "$DISK" -gt 85 ]; then
    echo "$(date) ALERT: Disk usage at ${DISK}%" >> /var/log/aakashvani-monitor.log
fi
```

```bash
chmod +x /opt/aakashvani/monitor.sh

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/aakashvani/monitor.sh") | crontab -
```

---

## Phase 13 — Backups & Disaster Recovery

### Step 12.1 — Automated PostgreSQL Backups
Create a backup script:
```bash
sudo mkdir -p /opt/aakashvani/backups
sudo nano /opt/aakashvani/backup.sh
```

```bash
#!/bin/bash
# Daily PostgreSQL backup with 14-day retention

BACKUP_DIR="/opt/aakashvani/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/aakashvani_${TIMESTAMP}.sql.gz"

# Dump and compress
docker exec aakashvani-postgres pg_dump -U aakashvani -d aakashvani | gzip > "$BACKUP_FILE"

# Verify backup is not empty
if [ ! -s "$BACKUP_FILE" ]; then
    echo "$(date) ALERT: Backup file is empty!" >> /var/log/aakashvani-monitor.log
    exit 1
fi

echo "$(date) Backup created: $BACKUP_FILE ($(du -h $BACKUP_FILE | cut -f1))" >> /var/log/aakashvani-backup.log

# Delete backups older than 14 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +14 -delete
```

```bash
chmod +x /opt/aakashvani/backup.sh

# Schedule daily at 3:00 AM IST
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/aakashvani/backup.sh") | crontab -
```

### Step 12.2 — Off-Site Backup (Recommended)
Don't keep backups only on the same server. Sync to an external location:
```bash
# Option A: Hetzner Storage Box (cheap, same DC)
# Option B: Cloudflare R2 or AWS S3
# Option C: rsync to a second server

# Example with rsync to Hetzner Storage Box:
rsync -avz /opt/aakashvani/backups/ u123456@u123456.your-storagebox.de:backups/
```

### Step 12.3 — Test Backup Restoration
**Do this BEFORE you need it.** Practice restoring to a test database:
```bash
# Create a test database
docker exec -it aakashvani-postgres createdb -U aakashvani aakashvani_test

# Restore
gunzip -c /opt/aakashvani/backups/aakashvani_LATEST.sql.gz | \
  docker exec -i aakashvani-postgres psql -U aakashvani -d aakashvani_test

# Verify
docker exec -it aakashvani-postgres psql -U aakashvani -d aakashvani_test \
  -c "SELECT count(*) FROM leads;"

# Clean up
docker exec -it aakashvani-postgres dropdb -U aakashvani aakashvani_test
```

### Step 12.4 — Hetzner Server Snapshots
In the Hetzner Cloud console:
1. Go to your server → **Snapshots**.
2. Create a manual snapshot before major deployments.
3. Enable **automatic weekly snapshots** (costs ~20% of server price).

> Snapshots capture the ENTIRE server disk (OS + Docker volumes + everything). This is your nuclear recovery option.

### Step 12.5 — Docker Volume Backups
PostgreSQL data lives in a Docker volume. To back up the raw volume:
```bash
# Stop postgres temporarily
docker compose stop postgres

# Backup the volume
docker run --rm -v aakashvani_pgdata:/data -v /opt/aakashvani/backups:/backup \
  alpine tar czf /backup/pgdata_volume_$(date +%Y%m%d).tar.gz -C /data .

# Restart
docker compose start postgres
```

---

## Phase 14 — CI/CD Pipeline (GitHub Actions)

### Step 13.1 — GitHub Repository Secrets
Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** and add:

| Secret Name | Value |
|------------|-------|
| `SERVER_HOST` | Your Hetzner server IP |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Contents of your private SSH key |
| `GHCR_TOKEN` | GitHub PAT with `packages:write` |

### Step 13.2 — Create the CI/CD Workflow
Create `.github/workflows/deploy.yml`:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  # ── Step 1: Lint & Test ──────────────────────────────────────
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: aakashvani
          POSTGRES_PASSWORD: testpassword
          POSTGRES_DB: aakashvani
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --locked

      - name: Lint
        run: uv run ruff check .

      - name: Run tests
        env:
          DATABASE_URL: postgresql://aakashvani:testpassword@localhost:5432/aakashvani
          REDIS_URL: redis://localhost:6379/0
          ADMIN_API_KEY: test-key-for-ci
        run: |
          uv run alembic upgrade head
          uv run pytest -x --tb=short

  # ── Step 2: Build & Push Docker Image ────────────────────────
  build:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        run: echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin

      - name: Build and push
        run: |
          IMAGE=ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
          IMAGE_LATEST=ghcr.io/${{ github.repository }}/backend:latest
          docker build -f Dockerfile.prod -t $IMAGE -t $IMAGE_LATEST .
          docker push $IMAGE
          docker push $IMAGE_LATEST

  # ── Step 3: Build Frontend ───────────────────────────────────
  build-frontend:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Build frontend
        working-directory: frontend
        run: |
          npm ci
          VITE_API_BASE_URL='' npm run build

      - name: Upload frontend artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/

  # ── Step 4: Deploy to Server ─────────────────────────────────
  deploy:
    needs: [build, build-frontend]
    runs-on: ubuntu-latest

    steps:
      - name: Download frontend artifact
        uses: actions/download-artifact@v4
        with:
          name: frontend-dist
          path: frontend-dist/

      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /opt/aakashvani

            # Pull latest backend image
            docker pull ghcr.io/${{ github.repository }}/backend:latest

            # Update docker-compose to use the new image
            # (update the image field in docker-compose.yml or use an override)

            # Restart backend with zero-downtime
            docker compose --env-file .env up -d backend

            # Run any new migrations
            docker exec aakashvani-backend uv run alembic upgrade head

            # Verify health
            sleep 10
            curl -f http://localhost:7860/health || exit 1

            echo "✅ Backend deployed successfully"

      - name: Deploy frontend
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          source: frontend-dist/*
          target: /opt/aakashvani/frontend-dist/
          strip_components: 1
```

### Step 13.3 — First-Time CI/CD Setup Verification
1. Push a small change to `main`.
2. Go to GitHub → **Actions** tab.
3. Watch the pipeline run through: Test → Build → Deploy.
4. Verify the app is running on your server.

---

## Phase 15 — Post-Deployment Verification

Run this checklist after EVERY deployment:

### Automated Checks
```bash
# 1. Health check
curl -f https://api.yourdomain.com/health
# Expected: {"status": "ok", "pool": {...}, ...}

# 2. Database connectivity
curl -f https://api.yourdomain.com/api/campaigns
# Expected: 401 (auth required) — proves the API is alive and DB is connected

# 3. SSL certificate
echo | openssl s_client -connect api.yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
# Expected: Shows valid notBefore and notAfter dates

# 4. Frontend loads
curl -s https://app.yourdomain.com | head -5
# Expected: HTML content with React root div

# 5. Container health
docker compose ps
# Expected: All services show "healthy"
```

### Manual Checks
- [ ] **Test login:** Open `https://app.yourdomain.com` and log in as a client.
- [ ] **Credits display:** Verify the sidebar shows the correct credit balance (not 0).
- [ ] **Test call:** Create a 1-lead test campaign with an internal phone number. Start it and verify:
  - [ ] Plivo dials the number.
  - [ ] The AI bot speaks.
  - [ ] The call log appears in the dashboard.
  - [ ] The lead status transitions correctly (calling → completed).
  - [ ] Credits are deducted.
- [ ] **Admin panel:** Open `https://admin.yourdomain.com` and verify the overview loads.

---

## Phase 16 — Rollback Procedure

If a deployment goes wrong, here's how to roll back:

### Step 15.1 — Backend Rollback
```bash
# See the previous image tag
docker images ghcr.io/YOUR_ORG/aakashvani/backend --format "{{.Tag}} {{.CreatedAt}}"

# Roll back to the previous image
docker compose --env-file .env down backend
# Edit docker-compose.yml to use the previous image tag, then:
docker compose --env-file .env up -d backend

# Verify
curl -f http://localhost:7860/health
```

### Step 15.2 — Database Rollback
```bash
# Check current migration
docker exec aakashvani-backend uv run alembic current

# Downgrade one step
docker exec aakashvani-backend uv run alembic downgrade -1

# Or restore from backup
gunzip -c /opt/aakashvani/backups/aakashvani_LATEST.sql.gz | \
  docker exec -i aakashvani-postgres psql -U aakashvani -d aakashvani
```

### Step 15.3 — Full Server Rollback
If everything is broken, restore from a Hetzner snapshot:
1. Go to Hetzner Cloud Console → Your Server → Snapshots.
2. Click **Restore** on the most recent pre-deployment snapshot.
3. The entire server reverts to that state.

---

## Appendix A — Complete Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NGROK_URL` | **YES** | — | Public URL for Plivo webhooks (use your production domain) |
| `DIALER_CALLBACK_HOST` | No | `NGROK_URL` | Override host for Plivo answer callbacks |
| `DATABASE_URL` | **YES** | — | PostgreSQL connection string |
| `REDIS_URL` | **YES** | — | Redis connection string (app crashes without it) |
| `DB_POOL_MIN` | No | `5` | asyncpg minimum pool size |
| `DB_POOL_MAX` | No | `50` | asyncpg maximum pool size |
| `CALL_LOG_DB_PATH` | No | `./data/call_logs.db` | SQLite fallback path |
| `ADMIN_API_KEY` | **YES** | — | Secret key for `/internal/*` endpoints |
| `BOT_ROUTE` | No | `sts` | `sts` or `cascaded` |
| `STS_SCRIPT` | No | `pyramid_mr` | STS script module |
| `CASCADE_SCRIPT` | No | `prowave` | Cascade script module |
| `PLIVO_AUTH_ID` | **YES** | — | Plivo account ID |
| `PLIVO_AUTH_TOKEN` | **YES** | — | Plivo auth token |
| `PLIVO_PHONE_NUMBER` | **YES** | — | Caller ID phone number |
| `PLIVO_MIN_BALANCE_USD` | No | `0.50` | Dialer pause threshold |
| `PLIVO_BALANCE_CACHE_SECONDS` | No | `30` | Balance check interval |
| `PLIVO_HANGUP_CALLBACK_ENABLED` | No | `true` | Enable hangup callback scheduling |
| `GOOGLE_API_KEY` | **YES** (STS) | — | Gemini Live API key |
| `GROQ_API_KEY` | Cascade | — | Groq LLM key |
| `SARVAM_API_KEY` | Cascade | — | Sarvam STT key |
| `CARTESIA_API_KEY` | Cascade | — | Cartesia TTS key |
| `CARTESIA_VOICE_ID` | Cascade | — | Default TTS voice |
| `DEEPGRAM_API_KEY` | No | — | Deepgram STT (alternative) |
| `OPENAI_API_KEY` | No | — | OpenAI (alternative) |
| `POST_CALL_MODEL` | No | `llama-3.3-70b-versatile` | LLM for post-call extraction |
| `MAX_CALL_MINUTES` | No | `10` | Max call duration |
| `GEMINI_CONTEXT_COMPRESSION` | No | `1` | Enable context window compression |
| `GEMINI_CWC_TRIGGER_TOKENS` | No | `20000` | Token threshold for compression |
| `USD_INR` | No | `84.0` | Exchange rate |
| `STALE_CALL_LOG_SWEEP_ENABLED` | No | `true` | Enable stale call cleanup |
| `STALE_CALL_LOG_SWEEP_SECONDS` | No | `300` | Sweep interval |
| `N8N_WEBHOOK_URL` | No | — | n8n webhook endpoint |
| `N8N_WEBHOOK_SECRET` | No | — | HMAC secret for n8n |
| `R2_ACCOUNT_ID` | No | — | Cloudflare R2 account |
| `R2_ACCESS_KEY_ID` | No | — | R2 access key |
| `R2_SECRET_ACCESS_KEY` | No | — | R2 secret |
| `R2_BUCKET_NAME` | No | `aakashvani-recordings` | Recording bucket |
| `RAZORPAY_KEY_ID` | Future | — | Payment integration |
| `RAZORPAY_KEY_SECRET` | Future | — | Payment integration |

---

## Appendix B — Port Map

| Port | Service | Binding | Exposed to Internet? |
|------|---------|---------|---------------------|
| `22` | SSH | `0.0.0.0` | ✅ Yes (firewall-restricted to your IP) |
| `80` | Caddy (HTTP→HTTPS redirect) | `0.0.0.0` | ✅ Yes |
| `443` | Caddy (HTTPS) | `0.0.0.0` | ✅ Yes |
| `7860` | FastAPI backend | `127.0.0.1` | ❌ No (Caddy proxies) |
| `5432` | PostgreSQL | `127.0.0.1` | ❌ No |
| `6379` | Redis | `127.0.0.1` | ❌ No |
| `5678` | n8n | `127.0.0.1` | ❌ No |

---

## Appendix C — External Service Dependencies

| Service | Provider | Required? | Used For | Failure Impact |
|---------|----------|-----------|----------|---------------|
| PostgreSQL 16 | Self-hosted (Docker) | **YES** | All data storage | Total app failure |
| Redis 7 | Self-hosted (Docker) | **YES** | Rate limiting, warmup signaling | App crashes on startup |
| Plivo | SaaS | **YES** | Outbound telephony, call recording | No calls can be placed |
| Google Gemini Live | SaaS | **YES** (STS mode) | Real-time speech-to-speech AI | Bot can't speak |
| Groq | SaaS | YES (Cascade) | LLM inference | Bot can't think |
| Sarvam AI | SaaS | YES (Cascade) | Indian language STT | Bot can't hear |
| Cartesia | SaaS | YES (Cascade) | TTS (text-to-speech) | Bot can't speak |
| Deepgram | SaaS | Optional | Alternative STT | N/A if not configured |
| Cloudflare R2 | SaaS | Optional | Recording storage | Recordings not saved |
| n8n | Self-hosted (Docker) | Optional | Workflow automation | Webhooks don't fire |

---

## Quick Reference — Deploy From Scratch in Order

```
1.  Buy server — Hostinger KVM 4 Mumbai (recommended) or Hetzner CCX23 Singapore
2.  Buy domain, set DNS A records (api / app / admin / n8n)
3.  SSH in, harden OS (user, firewall, fail2ban)
4.  Install Docker
5.  Create /opt/aakashvani/.env with all secrets
6.  Start Postgres + Redis (docker compose up -d)
7.  Run Alembic migrations (alembic upgrade head)
8.  Build backend Docker image
9.  Start backend (docker compose up -d backend)
10. Build frontend (npm ci && npm run build)
11. Upload frontend/dist to server
12. Install Caddy, write Caddyfile (api + app + admin + n8n), restart
13. Start n8n (docker compose up -d n8n), create admin account
14. Verify SSL + health check on all subdomains
15. Configure Plivo webhooks to api.yourdomain.com
16. Wire n8n webhook URL into .env, restart backend
17. Run a test call
18. Set up backups (cron + off-site + n8n workflow export)
19. Set up monitoring (UptimeRobot + Sentry)
20. Set up CI/CD (GitHub Actions)
21. Done. 🎉
```

# Production Deployment & Server Guide (`server.md`)

This guide documents the production server infrastructure, SSH access details, directory layouts, firewall configurations, and deployment troubleshooting commands for **Aakashvani**.

---

## 1. Server Overview

| Property | Value |
| :--- | :--- |
| **Server Host IP** | `77.37.47.133` |
| **Deployment User** | `deploy` |
| **Operating System** | Ubuntu 24.04.4 LTS (`x86_64`) |
| **Hostname** | `aakashvani-prod` |
| **App Directory** | `/opt/aakashvani/app` |
| **Compose Directory** | `/opt/aakashvani` |
| **Frontend Static Dist** | `/opt/aakashvani/frontend-dist` |

---

## 2. SSH Access

To access the production server from your terminal or command prompt:

```bash
ssh deploy@77.37.47.133
```

When prompted, enter the password for the `deploy` user or configure your public key in `~/.ssh/authorized_keys` on the server.

---

## 3. Firewall & Security Configuration

### Firewall Status (`ufw`)
The server firewall is configured to allow standard web and SSH ports:

```bash
sudo ufw status
```

**Expected Rules:**
* `22/tcp` — **ALLOW Anywhere** (SSH Access)
* `80/tcp` — **ALLOW Anywhere** (HTTP / Nginx / Caddy)
* `443/tcp` — **ALLOW Anywhere** (HTTPS / TLS)

### Fail2ban (`sshd`)
`fail2ban` protects the server against SSH brute-force attempts:

```bash
# Check SSH jail status
sudo fail2ban-client status sshd

# Unban all IPs if a GitHub Action or IP is blocked
sudo fail2ban-client unban --all
```

---

## 4. GitHub Actions CI/CD Secrets

The GitHub Action (`.github/workflows/deploy.yml`) requires the following repository secrets (**Settings → Secrets and variables → Actions**):

| Secret Name | Value / Description |
| :--- | :--- |
| `SERVER_HOST` | `77.37.47.133` |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Private SSH Key for `deploy` user |
| `GH_DEPLOY_TOKEN` | GitHub Personal Access Token (PAT with `Contents: Read` permission) |

---

## 5. Server Architecture & Service Ports

| Service | Container Name | Port / URL | Notes |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | `aakashvani-backend` | `127.0.0.1:7860` | Proxied by Nginx/Caddy |
| **PostgreSQL 16** | `aakashvani-postgres` | `5432` | Main database |
| **Redis 7** | `aakashvani-redis` | `6379` | Cache & locks |
| **n8n Workflow** | `aakashvani-n8n` | `127.0.0.1:5678` | Automation engine |

---

## 6. Maintenance & Troubleshooting Commands

### Inspect Running Containers & Logs
```bash
# Check container status
docker ps

# View backend container logs
docker logs aakashvani-backend --tail 100 -f

# Check health endpoint
curl -f http://localhost:7860/health
```

### Manual Trigger / Force Rebuild
If you need to manually trigger a pull and rebuild directly on the server:

```bash
# 1. Update source code
cd /opt/aakashvani/app
git pull origin main

# 2. Build production Docker image
docker build -f Dockerfile.prod -t aakashvani-backend:latest .

# 3. Build frontend static distribution
docker run --rm -v "$(pwd)/frontend:/app" -w /app node:20-alpine sh -c "npm ci && VITE_API_BASE_URL='' npm run build"
rsync -avz --delete frontend/dist/ /opt/aakashvani/frontend-dist/

# 4. Restart backend container & run migrations
cd /opt/aakashvani
docker compose --env-file .env up -d --force-recreate backend
docker exec aakashvani-backend uv run alembic upgrade head
```

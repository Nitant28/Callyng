# Aakashvani — Local Run Guide

Everything you need to start the stack, log in, and place an end-to-end test call on Windows.

---

## 1. Architecture

```
React + Vite Frontend (:5173)
        |
   Vite dev proxy  ->  /api, /internal
        |
FastAPI Backend (:7860)
        |
  +-----+-----------+-------------+
  |                 |             |
Postgres (:5432)  Redis (:6379)  Pipecat + Gemini Live
                                  |
                                Plivo  ->  Phone calls
                                  ^
                                  |
                          ngrok public URL
```

---

## 2. Prerequisites (already installed)

- Docker Desktop (running)
- Python 3.11+ and `uv`
- Node.js + npm
- ngrok (`npm install -g ngrok`, authtoken configured)

---

## 3. Credentials & Access

| What | Value |
|------|-------|
| Admin dashboard URL | http://localhost:5173/admin/login |
| Admin key | `dev-admin-key-123` |
| Client dashboard URL | http://localhost:5173/login |
| Client API key | `aakashvani_dev_key_change_me` |
| Backend API docs | http://localhost:7860/docs |
| Backend health | http://localhost:7860/health |
| ngrok inspector | http://localhost:4040 |

Database (Docker):
- Postgres: `postgresql://aakashvani:devpassword@localhost:5432/aakashvani`
- Redis: `redis://localhost:6379/0`

All app secrets (Plivo, Google/Gemini, etc.) live in `.env`.

---

## 4. One-Command Start

```powershell
cd C:\Users\Shubh\Desktop\AkashVani\aakashvani
.\scripts\start-local.ps1
```

This brings up Postgres + Redis, runs migrations, seeds the dev tenant, then starts the backend, frontend, and ngrok in separate windows.

---

## 5. Manual Start (step by step)

Run each block from the project root: `C:\Users\Shubh\Desktop\AkashVani\aakashvani`

### 5.1 Database + Redis
```powershell
docker compose up -d postgres redis
```

Wait until ready:
```powershell
docker exec aakashvani-postgres pg_isready -U aakashvani -d aakashvani
docker exec aakashvani-redis redis-cli ping
```

### 5.2 Migrations + seed (first time / after reset)
```powershell
uv run alembic upgrade head
Get-Content db\seed\dev_tenant.sql -Raw | docker exec -i aakashvani-postgres psql -U aakashvani -d aakashvani -v ON_ERROR_STOP=1
```

### 5.3 Backend (terminal 1)
```powershell
uv run uvicorn server:app --host 0.0.0.0 --port 7860
```
Wait for: `Application startup complete` + `PostgreSQL pool ready` + `Redis ready`.

### 5.4 Frontend (terminal 2)
```powershell
cd frontend
npm install   # first time only
npm run dev
```
Opens at http://localhost:5173

### 5.5 ngrok (terminal 3 — only needed for real calls)
```powershell
& "$env:APPDATA\npm\node_modules\ngrok\bin\ngrok.exe" http 7860
```
Copy the `https://...ngrok-free.dev` URL, then set it in `.env`:
```
NGROK_URL=https://your-ngrok-url.ngrok-free.dev
```
Restart the backend after changing `NGROK_URL`.

> Note: the free ngrok URL changes on every restart. The reserved domain
> `omission-wobbly-decorated.ngrok-free.dev` belongs to a different ngrok
> account, so it will not work with the locally configured authtoken.

---

## 6. Logging In

### Admin
1. Go to http://localhost:5173/admin/login
2. Enter `dev-admin-key-123`
3. You land on the admin overview (clients, campaigns, calls, diagnostics).

### Client
1. Go to http://localhost:5173/login
2. Enter `aakashvani_dev_key_change_me`
3. You land on the client dashboard (campaigns, credits, call logs).

If a page was already open, hard-refresh with `Ctrl+Shift+R`.

---

## 7. Quick API Tests (PowerShell)

```powershell
# Health
Invoke-WebRequest -UseBasicParsing http://localhost:7860/health | Select -Expand Content

# Admin (extended health)
Invoke-WebRequest -UseBasicParsing -Headers @{"X-Admin-Key"="dev-admin-key-123"} `
  http://localhost:7860/internal/health | Select -Expand Content

# Admin list clients
Invoke-WebRequest -UseBasicParsing -Headers @{"X-Admin-Key"="dev-admin-key-123"} `
  http://localhost:7860/internal/clients | Select -Expand Content

# Client credits
Invoke-WebRequest -UseBasicParsing -Headers @{"Authorization"="Bearer aakashvani_dev_key_change_me"} `
  http://localhost:7860/api/credits | Select -Expand Content
```

---

## 8. Placing an End-to-End Test Call

Requires backend + ngrok running and `NGROK_URL` set in `.env`.

```powershell
cd C:\Users\Shubh\Desktop\AkashVani\aakashvani
.\scripts\call.ps1 +91XXXXXXXXXX "Test Lead" "Pune"
```

Expected response:
```json
{ "status": "call_initiated", "call_id": "...", "call_uuid": "..." }
```

What happens:
1. Backend pre-warms Gemini Live and asks Plivo to dial the number.
2. Your phone rings — answer it.
3. Plivo hits `/answer` (via ngrok) and streams audio to `/ws`.
4. The Gemini voice bot talks using the `pyramid_bilingual` STS script.

Check the result:
- Watch backend logs for `[start]`, `[answer]`, Gemini warm-up lines.
- Admin UI: http://localhost:5173/admin/calls
- Or API:
```powershell
Invoke-WebRequest -UseBasicParsing -Headers @{"X-Admin-Key"="dev-admin-key-123"} `
  http://localhost:7860/internal/calls | Select -Expand Content
```

---

## 9. Stopping Everything

```powershell
# Backend / frontend: Ctrl+C in their terminals, or:
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object {$_.CommandLine -like '*uvicorn server:app*'} |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Containers (keeps data)
docker compose stop postgres redis

# Containers + wipe data
docker compose down -v
```

---

## 10. Verified Working

- PostgreSQL pool + Redis connected
- Alembic migrations 001 -> 006 applied
- Dev tenant seeded (Dev Client, 2 campaigns)
- Backend `/health`, `/docs`, `/internal/*`, `/api/*` responding
- Admin + client login (via Vite proxy, CORS fixed)
- Plivo credentials valid (balance ~ $22)
- Google/Gemini API key valid; Pipecat 1.1.0 + STS route loaded

---

## 11. Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `REDIS_URL is not set` / DB auth fails | Wrong containers up. Run `docker compose up -d postgres redis` (containers must be `aakashvani-postgres` / `aakashvani-redis`). |
| Login fails in browser | Frontend not on `:5173` or backend down. Use the Vite proxy; hard-refresh `Ctrl+Shift+R`. |
| `[Errno 10048] ... bind on address :7860` | Old backend still running. Kill it: `Get-NetTCPConnection -LocalPort 7860 \| %{ Stop-Process -Id $_.OwningProcess -Force }` then restart. |
| Call rings but no AI voice | ngrok not running or `NGROK_URL` wrong/stale in `.env`. Update and restart backend. |
| Phone never rings | Check Plivo balance and E.164 number format `+91...`. |
| `ERR_NGROK_320` | Reserved domain belongs to another ngrok account. Use an ephemeral URL (`ngrok http 7860`). |
| `LocalSmartTurnV3Analyzer` warning at startup | Harmless — STS/Gemini Live route does not use it. |

---

## 12. Code Changes Made for Local Run

- `server.py`: CORS allowlist now includes `http://localhost:5173` and `:5174`.
- `server.py`: `/start` and `/answer` use the public ngrok base URL for Plivo callbacks and the `/ws` stream (instead of localhost).
- `frontend/vite.config.js`: dev proxy for `/api` and `/internal` -> `:7860`.
- `frontend/src/api/{admin,client}.js`: `API_BASE_URL` defaults to relative (uses the proxy).
- `scripts/start-local.ps1`, `scripts/call.ps1`: Windows one-command start + test-call helpers.

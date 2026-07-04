# 15 — Environment Setup

Verified from `env.example`, `RUN_LOCAL.md`, `docker-compose.yml`, `pyproject.toml`,
`frontend/package.json`.

---

## Prerequisites

- Docker Desktop (Postgres + Redis)
- Python 3.11+ with **`uv`** package manager
- Node.js + npm (frontend)
- ngrok (for real Plivo calls — public URL to `:7860`)
- API keys: `GOOGLE_API_KEY`, `GROQ_API_KEY`, Plivo credentials (see `.env`)

---

## Quick start (Windows)

```powershell
cd aakashvani
.\scripts\start-local.ps1
```

Brings up Postgres+Redis, migrations, seed, backend `:7860`, frontend `:5173`, ngrok.

**Dev credentials** (`RUN_LOCAL.md`):
- Admin: `http://localhost:5173/admin/login` — key `dev-admin-key-123`
- Client: `http://localhost:5173/login` — key `aakashvani_dev_key_change_me`
- Postgres: `postgresql://aakashvani:devpassword@localhost:5432/aakashvani`
- Redis: `redis://localhost:6379/0`

---

## Manual start

### 1. Infrastructure
```powershell
docker compose up -d postgres redis
docker exec aakashvani-postgres pg_isready -U aakashvani -d aakashvani
```

### 2. Environment
```powershell
cp env.example .env
# Fill: DATABASE_URL, REDIS_URL, ADMIN_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY,
# PLIVO_*, NGROK_URL
```

### 3. Python deps + migrations
```powershell
uv sync
uv run alembic upgrade head
# Seed (if script exists): uv run python scripts/seed_dev.py  — verify script name in scripts/
```

### 4. Backend
```powershell
uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload
```

### 5. Frontend
```powershell
cd frontend
npm install
npm run dev   # :5173, proxies /api and /internal to :7860
```

### 6. ngrok (real calls)
```powershell
ngrok http 7860
# Set NGROK_URL=https://<subdomain>.ngrok-free.app in .env
```

---

## Key environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Phase 2+ | Postgres connection |
| `REDIS_URL` | yes (prod) | Redis; rate limit + warmup + locks |
| `ADMIN_API_KEY` | admin API | `/internal/*` auth |
| `NGROK_URL` / `DIALER_CALLBACK_HOST` | real calls | public telephony base URL |
| `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_PHONE_NUMBER` | real calls | outbound PSTN |
| `GOOGLE_API_KEY` | STS route | Gemini Live |
| `GROQ_API_KEY` | post-call + cascade | extraction LLM |
| `POST_CALL_MODEL` | optional | default `llama-3.3-70b-versatile` |
| `BOT_ROUTE` | dev fallback | `sts` or `cascaded` |
| `STS_SCRIPT` / `CASCADE_SCRIPT` | dev fallback | script module name |
| `MAX_CALL_MINUTES` | optional | default 10 |
| `CALL_LOG_DB_PATH` | optional | SQLite path `./data/call_logs.db` |
| `STALE_CALL_LOG_SWEEP_ENABLED` | optional | default true |
| `STALE_CALL_LOG_SWEEP_SECONDS` | optional | default 300 |
| `PLIVO_MIN_BALANCE_USD` | optional | dialer pause threshold |
| `VITE_API_BASE_URL` | frontend | empty = use Vite proxy |

Full list: `env.example`.

---

## Alembic

```powershell
uv run alembic upgrade head    # apply migrations
uv run alembic current         # check revision
```

Migrations: `alembic/versions/001` … `010`. Raw DDL also in `db/schema/*.sql`.

---

## Docker

`docker-compose.yml` services: `postgres` (5432), `redis` (6379). App container
in `Dockerfile` — **Not verified from source** for production deploy details;
see `pcc-deploy.toml` for Plivo PCC.

---

## Running tests

```powershell
# Requires running Postgres + Redis (same as dev)
uv run pytest tests/ -v
```

See `16_TESTING_GUIDE.md`.

---

## Frontend env

`frontend/.env` or Vite env:
```
VITE_API_BASE_URL=          # empty for dev proxy
```

CORS: backend must allow your frontend origin (`server.py` list).

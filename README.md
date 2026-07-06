# AakashVani - Local Setup

## Prerequisites

Install:

- Docker Desktop
- Python 3.12+
- Node.js 20+
- npm
- uv
- ngrok (optional)

---

## 1. Clone Repository

```bash
git clone <repo-url>
cd aakashvani
```

---

## 2. Start Infrastructure

```bash
docker compose up -d postgres redis
```

Verify:

```bash
docker ps
```

Both containers should be running.

---

## 3. Install Backend Dependencies

```bash
uv sync
```

---

## 4. Run Database Migrations

```bash
uv run alembic upgrade head
```

---

## 5. Seed Database (if required)

```powershell
Get-Content db\seed\dev_tenant.sql -Raw |
docker exec -i aakashvani-postgres psql -U <DB_USER> -d <DB_NAME>
```

Replace:

- `<DB_USER>`
- `<DB_NAME>`

with the values from your `.env`.

---

## 6. Start Backend

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload
```

Backend:

```
http://localhost:7860
```

Swagger:

```
http://localhost:7860/docs
```

Keep this terminal running.

---

## 7. Start Frontend

Open a new terminal.

```bash
cd frontend
```

Install dependencies (first time only):

```bash
npm install
```

Run:

```bash
npm run dev
```

Frontend:

```
http://localhost:3000
```

(or the port shown in the terminal)

Keep this terminal running.

---

## 8. Start ngrok (Optional)

Expose backend publicly.

```bash
ngrok http 7860
```

Use the generated HTTPS URL wherever a public backend endpoint is required.

---

# Terminal Layout

### Terminal 1

```bash
docker compose up -d postgres redis
```

### Terminal 2

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload
```

### Terminal 3

```bash
cd frontend
npm run dev
```

### Terminal 4 (Optional)

```bash
ngrok http 7860
```

---

# Verify

Backend:

```
http://localhost:7860/docs
```

Frontend:

```
http://localhost:3000
```

---

# Stop Everything

Stop Backend:

```
Ctrl + C
```

Stop Frontend:

```
Ctrl + C
```

Stop Docker:

```bash
docker compose down
```

---

# Restart

```bash
docker compose up -d postgres redis
```

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 7860 --reload
```

```bash
cd frontend
npm run dev
```

# Aakashvani

> **Managed AI outbound voice** for the Indian SMB market — outcomes and ops, not a self-serve bot builder.
> Built with Pipecat 1.1.0, Plivo, Gemini Live, and FastAPI.

---

## 📍 Current Project Status

We are currently finishing up **Phase 2 (Multi-tenant & Billing)** and have pulled ahead to complete major chunks of **Phase 3 (Bot Config UI)**.

| Phase | Milestone | Status |
| ----- | --------- | ------ |
| **Phase 0 & 1** | Foundation (Pipecat pipelines, Plivo integration, Groq extraction) | ✅ **DONE** |
| **Phase 2A** | Backend (PostgreSQL schema, Multi-tenant Admin APIs, Concurrent Dialers) | ✅ **DONE** |
| **Phase 3** | Bot Configuration UI (Script CMS, Dynamic Templates, Revision Rollbacks) | 🚀 **AHEAD OF SCHEDULE (DONE)** |
| **Phase 2B** | Client-Facing React SPAs (Upload -> Draft Leads -> Test Call -> Start) | 🚧 **IN PROGRESS (Current Focus)** |

For a deep dive into the long-term vision, read the [ROADMAP.md](ROADMAP.md).

---

## 🛠️ How to Run Locally

Follow these steps to get the entire Aakashvani stack (Backend, Frontend, PostgreSQL, n8n, and Webhooks) running on your local machine.

### 1. System Requirements & WSL Setup (Windows Users)
If you are on Windows, you **MUST** use WSL2 (Windows Subsystem for Linux).
1. Open PowerShell as Administrator and run: `wsl --install -d Ubuntu-24.04`
2. Install **Docker Desktop for Windows**. Go to *Settings -> Resources -> WSL Integration* and enable it for your Ubuntu distro.
3. Restart your terminal. All subsequent commands must be run **inside your WSL Ubuntu terminal**.
*(Mac/Linux users can simply use their native terminal with Docker installed).*

### 2. Install Prerequisites
You will need the following tools installed on your system:
- **Python 3.12+**
- **uv**: The ultra-fast Python package installer. `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker & Docker Compose**: For running PostgreSQL and n8n databases.
- **ngrok**: For exposing your local server to the internet so Plivo can send webhooks.
- **just**: A handy command runner (like make). `sudo apt install just` (Ubuntu) or `cargo install just`.
- **Node.js & npm**: For running the frontend React applications.

### 3. Environment Secrets
Copy the example environment file and fill it in:
```bash
cp env.example .env
```
Open `.env` and configure your keys:
- `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_PHONE_NUMBER`
- `GOOGLE_API_KEY` (Required for Gemini Live)
- `GROQ_API_KEY` (Required for Post-Call Data Extraction)
- `NGROK_URL` (Your reserved ngrok domain, e.g., `https://my-app.ngrok-free.dev`)
- `DATABASE_URL=postgresql://aakashvani:dev@localhost:5432/aakashvani` (Default for local Docker)

### 4. Database & Services (PostgreSQL + n8n)
Start the background services using Docker. The included `docker-compose.yml` handles Postgres 16 and n8n (port 5678).
```bash
just db-up          # Starts the Docker containers in the background
just db-migrate     # Runs all Alembic DB schema migrations
just db-seed        # Seeds the DB with a dev tenant and a sandbox campaign
```

### 5. Running the Backend (FastAPI)
Install the Python dependencies and boot the uvicorn server:
```bash
uv sync
just dev            # Runs the backend on localhost:7860
```

### 6. Exposing the Webhook Tunnel
Plivo needs a public URL to reach your local server during phone calls. In a **new terminal tab**, run:
```bash
just tunnel         # Starts ngrok on port 7860 using your NGROK_URL
```

### 7. Running the Frontend (React SPAs)
The Admin and Client dashboards are built with React and Vite. In a **third terminal tab**, run:
```bash
cd frontend
npm install
npm run dev         # Starts the Vite dev server
```

### 8. Making a Test Call
To verify the entire pipeline is working (without using the React UI), you can fire a CMS-driven test call directly from the CLI:
```bash
just cms-call <script-config-uuid> +91<your-phone-number> sts
```

---

## 📜 Operator CLI (`just` commands)

We use `scripts/cli.py` to interact with the database natively (no HTTP server required). You can use `just` shortcuts to inspect the system.

| Category | Command | Description |
| -------- | ------- | ----------- |
| **Inspection** | `just show-client "pyr"` | Shows client balance, bots, and campaigns. |
| | `just show-campaign "Renewal"` | Shows budget, counters, and bot config. |
| | `just campaign-calls "Renewal" --limit 10` | Shows recent `call_logs` rows. |
| | `just show-call <session_id> --full` | Shows the full transcript and extracted JSON. |
| **Actions** | `just reset-lead <phone> --campaign "Renewal"`| Moves a lead back to `pending` for re-testing. |
| | `just failed-extractions` | Lists calls missing outcomes or extraction errors. |
| | `just rerun-extraction <session_id>` | Re-runs Groq on the stored transcript. |
| **Testing** | `just test-call` | Fires a Phase 0 SQLite-isolated outbound call. |

For a full breakdown of CLI commands, read [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md).

---

## 📚 Documentation Reference

| Document | Purpose |
| -------- | ------- |
| [README.md](README.md) | Dev setup, local running instructions, basic CLI commands (this file). |
| [ROADMAP.md](ROADMAP.md) | Long-term vision, project phases, and pricing strategy. |
| [guides/aakash_arch.md](guides/aakash_arch.md) | **Source of Truth** for Database schema, billing logic, and API contracts. |
| [guides/TESTING.md](guides/TESTING.md) | E2E walk-through for setting up a client and campaign. |
| [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) | Complete Operator CLI reference. |
| [handoff/log.md](handoff/log.md) | Historical logs of agent development sessions. |

*Note: If anything in the README or ROADMAP conflicts with `aakash_arch.md`, **the architecture doc wins**.*

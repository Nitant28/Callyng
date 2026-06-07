# Project: Aakashvani Frontend Refinement

## Architecture
- **Frontend**: Vite + React SPA in `/home/satyam/aakashvani/frontend`. Using Tailwind CSS.
  - Page components: `Login.jsx`, `Dashboard.jsx`, `CampaignDetail.jsx`, `CallLogs.jsx` under `src/pages/client/`.
- **Backend**: FastAPI server defined in `/home/satyam/aakashvani/server.py` and API routes in `/home/satyam/aakashvani/api/routes/`.
- **Database**: SQLite/Postgres schemas managed by Alembic.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Backend & Frontend Audit | Analyze FastAPI endpoints, ROADMAP.md, and React component code to catalog supported vs unsupported features, and styling gaps. | None | DONE |
| M2 | E2E Test Suite Design | Create E2E test suite for verifying frontend builds, disabled/commented out features, and basic UX flow. | None | DONE |
| M3 | UI Cleanup & Feature Toggle | Comment out unsupported frontend features (like Call Recordings, analytics charts) with TODO markers. | M1 | IN_PROGRESS |
| M4 | Branding & Aesthetic Polish | Standardize style, colors, branding, and typography across all client pages for enterprise AI dialer. | M3, M2 | PLANNED |
| M5 | Final Verification & Hardening | Run all E2E tests, challenger adversarial validations, and Forensic Audit checks to guarantee cleanliness. | M4 | PLANNED |

## Interface Contracts
### React SPA ↔ FastAPI API
- Authentication: `/api/auth` (handled via login pages)
- Campaigns: `/api/campaigns` (CRUD, start/stop, status)
- Call Logs: `/api/calls` (listing call logs)
- Leads: `/api/leads` (list leads, upload/assign)
- Inactive endpoints (No backend routes or marked as Phase 3/4 in ROADMAP):
  - Call Recordings download/play (not supported, `call_logs.recording_url` not populated)
  - Bot config UI
  - Real-time SSE Live monitor (no WebSocket supports for specific metrics, only general WS connection)
  - Razorpay credit purchase

## Code Layout
- Frontend Root: `/home/satyam/aakashvani/frontend`
- Page Views: `/home/satyam/aakashvani/frontend/src/pages/client/`
- Backend API Routes: `/home/satyam/aakashvani/api/routes/`
- Integration Tests: `/home/satyam/aakashvani/tests/`

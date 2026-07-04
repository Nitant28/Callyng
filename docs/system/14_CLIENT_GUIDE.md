# 14 — Client Guide

Client UI routes under `/app/*`. Auth: Bearer API key.

---

## Login (`/login`)

Enter the API key provided by the operator (shown once at client creation).
Validated against `GET /api/credits`. Key stored in browser localStorage.

---

## Dashboard (`/app`)

**Shows:**
- Current credit balance (`balance_credits`).
- Grid of your campaigns with status badges and progress indicators from backend counters.

**Actions:**
- Click campaign → detail page.
- **Start** campaign (draft/paused/pausing) — confirm modal; requires budget remaining ≥2 credits.
- **Stop** campaign (running) — pauses dialer; may show `pausing` while calls finish.

**Polling:** refreshes every 5s while any campaign is active.

**TRAI notice:** UI shows whether current time is inside 9am–9pm IST calling window
(display only; backend enforces on dial).

---

## Campaign detail (`/app/campaigns/:id`)

**Overview tab:**
- Metric cards: pending, calling, callback, completed, failed, total leads — **from backend counters**.
- Budget used / remaining.
- Campaign status and controls: Start, Stop, Cancel, Release stuck calling leads.

**Leads tab:**
- Paginated lead table (search + status filter).
- **Upload CSV** — must match bot's lead schema; download template first.
- **Add lead** manually (draft/paused only).
- **Edit / delete** lead (not while campaign running; not while lead is `calling`).
- **Change status** manually (enforced transition table).
- View transcript for leads with calls (drawer).

**Settings tab:**
- Campaign name/throttle settings patch (draft/paused only).

**Polling:** stats every 2–5s when campaign active; leads every 5s.

---

## Call logs (`/app/calls`)

- Paginated list of all your calls (newest first).
- Click row → transcript drawer with live updates for in-progress calls.
- Play recording when available (proxied audio).

---

## Settings (`/app/settings`)

Theme preference only. No account settings API exists today.

---

## What clients cannot do

- Create bot configs or script configs (admin only).
- Top up credits (admin only).
- See `credits_per_minute` or provider costs.
- See other clients' data.
- Configure webhooks (admin only).

---

## Campaign status reference

| Status | Meaning for client |
|--------|-------------------|
| `draft` | Created; upload leads; not dialing |
| `running` | Dialer active |
| `pausing` | Stop requested; in-flight calls finishing |
| `paused` | Stopped; can resume |
| `completed` | All leads terminal; unused budget returned |
| `cancelled` | Manually stopped; non-terminal leads failed |

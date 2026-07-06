# 07 — Frontend State Model (Ideal)

Recommended state architecture for the **new** frontend. Maps 1:1 to verified
backend contracts.

---

## Global state

| Slice | Storage | Source | Notes |
|-------|---------|--------|-------|
| `auth.clientApiKey` | localStorage `client_api_key` | Login | |
| `auth.adminKey` | localStorage `aakashvani_admin_key` | AdminLogin | |
| `theme` | localStorage (via `useTheme`) | user pref | no API |
| `toast` | React context | ephemeral | |
| `admin.clients` | context cache | `GET /internal/clients` | optional; invalidate on create |
| `admin.botConfigs` | context cache | `GET /internal/bot-configs` | optional |

No global campaign/call cache required if using React Query per-route.

---

## Per-page state

### Login
| Kind | Fields |
|------|--------|
| Local | `apiKey`, `submitState: idle\|loading\|success\|error` |
| API | none persisted until success |
| Derived | none |

### Dashboard
| Kind | Fields |
|------|--------|
| API | `credits: { balance_credits, max_concurrent_calls, client_name }`, `campaigns: Campaign[]` |
| Loading | `isInitialLoading`, `isRefreshing` |
| Error | `creditsError`, `campaignsError` (**add in rebuild — current UI swallows**) |
| Local | `confirmStartId`, `copiedId` |
| Derived | `remainingBudget(c)`, `hasActiveCampaigns`, `istCompliance` (display) |
| Polling | `refetchInterval: 5000` when `hasActiveCampaigns` |

### CampaignDetail
| Kind | Fields |
|------|--------|
| API | `stats: Campaign+BotConfig`, `leads: { items, total_count }` |
| Loading | `statsLoading`, `leadsLoading`, `uploading`, `actionPending` |
| Error | per-mutation + fetch errors |
| Local | `tab`, modals, `leadsQuery: { limit, offset, search, status }`, drawer |
| Derived | `remainingBudget`, `progressPct`, `liveCalling` (= `stats.calling_leads`), outcome labels |
| Pagination | `offset/limit` on leads — **use `total_count` from API** |
| Filters | `status`, `search` → query params |
| Polling | stats 2–5s; leads 5s when active |

### CallLogs
| Kind | Fields |
|------|--------|
| API | `calls: { items, total_count }`, `selectedCall`, `callDetail` |
| Loading | list, detail, recording |
| Pagination | `limit=10`, `offset` |
| Polling | detail 2s if `in_progress` |

### Settings
| Kind | Fields |
|------|--------|
| Local | theme only |

### Admin pages
| Kind | Fields |
|------|--------|
| API | entity lists + detail per route |
| Loading | per-fetch |
| Pagination | calls list, campaign leads (admin) |
| Search | client-side filter on some admin lists (verified in routes) |

---

## TypeScript interfaces (recommended)

```typescript
interface Campaign {
  id: string;
  client_id: string;
  bot_config_id: string;
  name: string;
  status: 'draft' | 'running' | 'pausing' | 'paused' | 'completed' | 'cancelled';
  budget_credits: number;
  budget_used_credits: number;
  max_concurrent_calls: number;
  calls_per_minute: number;
  max_attempts: number;
  retry_delay_minutes: number;
  max_call_minutes: number | null;
  total_leads: number;
  pending_leads: number;
  calling_leads: number;
  callback_leads: number;
  completed_leads: number;
  failed_leads: number;
  created_at: string;
  completed_at: string | null;
  budget_returned_at: string | null;
}

interface Lead {
  id: string;
  phone: string;
  name: string | null;
  status: 'pending' | 'calling' | 'completed' | 'failed' | 'callback_scheduled';
  attempts: number;
  max_attempts: number;
  outcome: string | null;
  extraction: Record<string, unknown>;
  metadata: Record<string, unknown>;
  next_attempt_at: string | null;
  scheduled_callback_at: string | null;
  last_call_duration_seconds?: number | null;
  last_call_outcome?: string | null;
  last_call_ended_at?: string | null;
  last_hangup_source?: string | null;
}

interface CallLog {
  session_call_id: string;
  in_progress: boolean;
  duration_seconds: number | null;
  billed_minutes: number | null;
  credits_charged: number | null;
  outcome: string | null;
  qualified: boolean;
  transcript: TranscriptTurn[];
  extraction_json: Record<string, unknown>;
  plivo_hangup_json: Record<string, unknown>;
  recording_url: string | null;
  started_at: string;
  ended_at: string | null;
  name?: string; // joined on list
  phone?: string;
}
```

Shapes match `record_to_dict` output from Postgres; nullable fields as stored.

# 12 — Frontend Mapping (Component → API)

Maps UI surfaces to backend contracts. "Skeleton" = existing loading pattern.

---

## Client components

### `Dashboard` campaign card
| | |
|---|---|
| **Endpoint** | `GET /api/campaigns` (embedded counters per campaign) |
| **Key fields** | `name`, `status`, `pending_leads`, `calling_leads`, `completed_leads`, `failed_leads`, `callback_leads`, `budget_credits`, `budget_used_credits` |
| **Nullable** | `completed_at`, counters default 0 |
| **Skeleton** | `LoaderOverlay` full page |
| **Error** | silent (rebuild: show banner) |

### `CampaignDetail` metric cards
| | |
|---|---|
| **Endpoint** | `GET /api/campaigns/{id}/stats` → `stats` |
| **Key fields** | all `*_leads`, `total_leads`, budget fields, `status`, `max_concurrent_calls` |
| **Nullable** | `max_call_minutes` |
| **Skeleton** | `LoaderOverlay` |
| **Error** | toast on actions only |

### `CampaignDetail` leads table
| | |
|---|---|
| **Endpoint** | `GET /api/campaigns/{id}/leads?limit&offset&status&search` |
| **Key fields** | `leads[]`, `total_count`; per lead: `phone`, `name`, `status`, `outcome`, `attempts`, `next_attempt_at`, `last_call_*` |
| **Nullable** | `outcome`, `name`, all `last_call_*` |
| **Skeleton** | `leadsLoading` opacity |
| **Error** | toast on CRUD |

### `CallLogs` table row
| | |
|---|---|
| **Endpoint** | `GET /api/calls` |
| **Key fields** | `session_call_id`, `outcome`, `duration_seconds`, `started_at`, `name`, `phone`, `in_progress` |
| **Nullable** | `duration_seconds`, `outcome`, joined name/phone |
| **Skeleton** | table loading state |
| **Error** | console only |

### `CallTranscriptDrawer`
| | |
|---|---|
| **Endpoint** | `GET /api/calls/{session_call_id}`, `GET .../recording/play` |
| **Key fields** | `transcript[]`, `extraction_json`, `outcome`, `duration_seconds`, `plivo_hangup_json`, `in_progress` |
| **Nullable** | `extraction_json` may be `{}`; recording may 404 |
| **Skeleton** | spinner in drawer |
| **Error** | recording error message; poll continues on detail errors |

### `Login`
| | |
|---|---|
| **Endpoint** | `GET /api/credits` |
| **Key fields** | any 200 validates key |
| **Error** | inline "Invalid Client Key" |

---

## Admin components (representative)

### `AdminOverview` stat tiles
| | |
|---|---|
| **Endpoint** | `GET /internal/stats` |
| **Fields** | `total_calls_today`, `active_campaigns`, `total_credits_used_today` |

### `AdminClientDetail` ledger
| | |
|---|---|
| **Endpoint** | `GET /internal/clients/{id}/credits` |
| **Fields** | `transactions[]`: `amount`, `note`, `created_at` |

### `AdminCalls` row
| | |
|---|---|
| **Endpoint** | `GET /internal/calls`, `GET /internal/calls/{id}` |
| **Fields** | same as client call_log + cross-client |

### `AdminScriptConfigs` editor
| | |
|---|---|
| **Endpoints** | script-config CRUD, template, revisions, rollback, dial-test |
| **Fields** | full `script_configs` row shape — see `04_DATABASE_SCHEMA.md` |

---

## Shared UI (`components/shared/ui`)
Presentational only — no API coupling.

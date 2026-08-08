# Aakashvani Credit & Billing System Specification

This document details the complete architecture, mathematical billing formulas, technical mechanics, and native observability model for the **Aakashvani Hybrid Credit & Billing System**.

The platform supports two distinct voice AI architectures:
1. **SECTION 1: STS ROUTE (Gemini Live Speech-to-Speech)**
2. **SECTION 2: CASCADED ROUTE (STT + LLM + TTS Pipeline)**
3. **SECTION 3: NATIVE DASHBOARD OBSERVABILITY & ALERTING ARCHITECTURE**
4. **SECTION 4: TECHNICAL IMPLEMENTATION PLAN (Current Repo → New System)**

---

# SECTION 1: STS ROUTE (Gemini Live Speech-to-Speech)

## 1.1 Architecture & Component Overview

### Why This Architecture?
The **STS (Speech-to-Speech)** route uses Google's `gemini-3.1-flash-live-preview` native multimodal audio model over WebSockets. Unlike traditional cascaded stacks, Gemini Live processes audio natively and returns audio directly within a single model container.

Consequently, the STS route consists of only **2 primary operational components**:
1. **Telephony (Plivo)** — Telecommunication carrier setup and call duration.
2. **Gemini Live Multimodal Model** — Native audio and text token processing.

### Audio vs Text Token Separation: CANNOT Be Done Live

A critical technical constraint verified against the actual codebase:

> **Google's Gemini Live API does NOT expose a breakdown of audio tokens vs text tokens in its usage response.** The API returns aggregate `prompt_token_count` and `candidates_token_count` covering all modalities combined. Pipecat's `LLMUsageMetricsData` in `MetricsFrame` carries these aggregate numbers. `UsageMetricsAccumulator` in [`call_metrics.py`](file:///home/satyam/aakashvani/call_metrics.py) stores them as generic `llm_prompt_tokens` and `llm_completion_tokens` with no audio/text distinction.

**Implications for billing**: We **cannot** scope `UsageMetricsTap` to "text tokens only" for STS. Instead, we use a hybrid approach:

1. **Duration-based audio cost estimate**: Google publishes flat per-minute audio equivalents ($0.005/min in, $0.018/min out). We compute audio cost from call duration and **subtract** it from the total reported token cost to derive the text token residual. This is an approximation but matches Google's own published billing rates.
2. **Total token cost**: Compute total cost from aggregate `prompt_tokens` and `completion_tokens` using the blended per-1M rates.
3. **Recommended approach**: Use the **total aggregate token cost** (audio + text combined) from the Gemini usage metadata directly, since that is what Google actually bills us. The audio per-minute rates are published *equivalents*, not separate line items on the invoice. Trying to decompose and recompose them introduces rounding drift for zero benefit.

### STS Billing Model: Use Aggregate Token Cost + Telephony

Given the above constraint, the STS billing formula is:

$$C_{\text{STS}} = C_{\text{telephony}} + C_{\text{gemini\_tokens}} \times (1 + M_{\text{margin}}) + C_{\text{post\_call}}$$

Where $C_{\text{gemini\_tokens}}$ uses the aggregate token counts reported by the Gemini API.

---

## 1.2 Mathematical Billing Model & Formulas

$$\text{Total STS Call Cost } (C_{\text{STS}}) = C_{\text{telephony}} + C_{\text{gemini}} \times (1 + M_{\text{margin}}) + C_{\text{post\_call}}$$

### Detailed Component Calculation:

1. **Telephony Cost ($C_{\text{telephony}}$)**:
   - **Plivo Setup Fee ($C_{\text{fixed\_start}}$)**: **₹0.60** per attempt (Charged on every dial attempt initiated via Plivo, regardless of whether answered, busy, or failed, matching Plivo carrier charges).
   - **Telephony Minute Fee**: $\lceil t_{\text{seconds}} / 60 \rceil \times R_{\text{telephony\_min}}$ (Default: ₹0.50 per started minute).

2. **Gemini Token Cost ($C_{\text{gemini}}$)**:
   - Uses aggregate tokens reported by Gemini API (audio + text combined):
     $$C_{\text{gemini\_usd}} = \left( \frac{T_{\text{prompt}}}{1,000,000} \times R_{\text{sts\_in\_usd\_1m}} \right) + \left( \frac{T_{\text{completion}}}{1,000,000} \times R_{\text{sts\_out\_usd\_1m}} \right)$$
     $$C_{\text{gemini\_inr}} = C_{\text{gemini\_usd}} \times \text{USD\_INR}$$
   - Default rates for `gemini-3.1-flash-live-preview`:
     - Input (audio+text blended): **$3.00 / 1M tokens**
     - Output (audio+text blended): **$12.00 / 1M tokens**
   - **Note**: These are the audio-dominant blended rates. Text-only input is $0.75/1M and text-only output is $4.50/1M, but since the API does not separate them, we use the blended audio-inclusive rates as the billing basis. This slightly overcharges for text-heavy prompts (system prompt, tool schemas) but is conservative and matches what Google actually invoices.

3. **Profit Overhead Margin ($M_{\text{margin}}$)**:
   - A configurable profit margin percentage (Default: **25%**) applied to Gemini vendor costs.

4. **Post-Call Processing Charge ($C_{\text{post\_call}}$)**:
   - Fixed fee of **₹0.25** applied at post-call settlement to cover structured lead extraction (`post_call_extract.py`), normalization, and platform webhooks.

---

## 1.3 End-to-End Lifecycle & Technical Mechanics

### Phase 1: Pre-Reservation Hold (Dial Claim)
- **Objective**: Prevent credit overbooking under 50–100 parallel dials.
- **Current state**: `adjust_budget_used` in [`db/postgres.py`](file:///home/satyam/aakashvani/db/postgres.py#L1265) has **NO WHERE clause** checking balance. It blindly increments `budget_used_credits`. This must be fixed.
- **Required SQL**: Atomic conditional UPDATE:
  ```sql
  UPDATE campaigns
  SET budget_used_credits = budget_used_credits + $2
  WHERE id = $1 AND client_id = $3
    AND (budget_credits - budget_used_credits) >= $2
  RETURNING budget_credits, budget_used_credits;
  ```
- **Application Guard**: Dialer checks if a row was returned. If `None` (insufficient balance), reject before dialing Plivo.

### Phase 2: Live In-Memory Monitoring (Zero-DB Writes)
- **Objective**: Zero database queries during live audio streaming to prevent latency jitter.
- **Pipeline Capture**: `UsageMetricsTap` captures aggregate `prompt_tokens` and `completion_tokens` in memory via `UsageMetricsAccumulator`.
- **Minute Watchdog**: A 60-second timer increments started minute counts.
- **Redis Snapshotting**: **Does NOT currently exist.** Must be implemented from scratch. Active call metrics and running cost estimates will be written to Redis key `active_call:{call_id}:cost` periodically.

### Phase 3: Post-Call Settlement
- **Objective**: Atomic final settlement when call hangs up.
- **Execution**: [`post_call_processor.py`](file:///home/satyam/aakashvani/post_call_processor.py) executes a single PostgreSQL transaction:
  1. Computes final $C_{\text{STS\_INR}}$ from accumulated token counts.
  2. Executes `settle_call_budget`, replacing the initial reservation hold with exact final charges.
  3. If `budget_credits - budget_used_credits < 0`, automatically transitions campaign status to `paused` and queues deficit deduction against client `balance_credits`.

---

# SECTION 2: CASCADED ROUTE (STT + LLM + TTS Pipeline)

## 2.1 Architecture & Component Overview

### Why This Architecture?
The **Cascaded** route connects decoupled provider APIs in a serial audio processing pipeline.

### Current Provider Stack (Verified Against Codebase)
As verified in [`bot_cascade.py`](file:///home/satyam/aakashvani/bot_cascade.py), the cascaded route currently uses a **fixed provider stack**:
- **Telephony**: Plivo
- **Speech-to-Text (STT)**: **Sarvam AI** (`SarvamSTTService`)
- **Large Language Model (LLM)**: **Groq** (`GroqLLMService`)
- **Text-to-Speech (TTS)**: **Cartesia** (`CartesiaTTSService`)

> **Important correction**: The previous draft of this document listed "Deepgram / Sarvam AI" for STT and "OpenAI / ElevenLabs" as alternative providers. **These alternatives do NOT exist in the codebase.** There are no Deepgram, OpenAI, or ElevenLabs imports, API keys, or script config fields anywhere. All cascade scripts (`cascade_scripts/*.py`) exclusively configure Sarvam models, Groq models, and Cartesia voices via `script_runtime.py` fields (`sarvam_model`, `sarvam_language`, `groq_model`, `cartesia_voice`).

### Multi-Vendor Future Support
If we later add alternative providers (Deepgram STT, OpenAI LLM, ElevenLabs TTS), the billing system should be designed to handle it. The approach:
- Each `bot_config` / `script_config` record stores the specific vendor names alongside their rates.
- At post-call settlement, the pricing engine reads the vendor from the call's `bot_config` and applies the matching rate table.
- **For now**, we hardcode the current Sarvam + Groq + Cartesia rates as defaults and make the rate columns configurable for future vendors.

### STT Metrics Gap: Audio Duration Not Tracked

> **Critical gap verified**: Pipecat does **NOT** emit `STTUsageMetricsData` as a `MetricsFrame`. `UsageMetricsTap` in [`call_metrics.py`](file:///home/satyam/aakashvani/call_metrics.py) only captures `LLMUsageMetricsData` (tokens) and `TTSUsageMetricsData` (characters). **STT audio duration is completely untracked.**

**Resolution options**:
1. **Use call duration as STT proxy** — STT runs for the full duration of the call (Sarvam receives continuous audio). This slightly overestimates because it includes periods of silence, but Sarvam/Deepgram billing works on audio-seconds-sent, which correlates closely with call duration.
2. **Add VAD-aware STT duration tracking** — Track only the user-speaking segments via `UserStartedSpeakingFrame`/`UserStoppedSpeakingFrame` in a custom frame processor. More accurate but adds complexity.

**Recommended**: Option 1 (use call duration) for initial implementation. The overestimate is small and conservative. Option 2 can be added later if STT costs become a significant billing concern.

---

## 2.2 Mathematical Billing Model & Formulas

$$\text{Total Cascaded Call Cost } (C_{\text{Cascade}}) = C_{\text{telephony}} + \left( C_{\text{stt}} + C_{\text{llm}} + C_{\text{tts}} \right) \times (1 + M_{\text{margin}}) + C_{\text{post\_call}}$$

### Component Calculations:

1. **Component 1: Telephony (Plivo)**:
   - Setup Fee: $C_{\text{fixed\_start}} = 0.60$ INR.
   - Minute Fee: $\lceil t_{\text{seconds}} / 60 \rceil \times R_{\text{telephony\_min}}$.

2. **Component 2: Speech-to-Text (STT — Sarvam AI)**:
   - Billed per audio minute (approximated as call duration):
     $$C_{\text{stt\_inr}} = \frac{t_{\text{seconds}}}{60} \times R_{\text{stt\_usd\_min}} \times \text{USD\_INR}$$

3. **Component 3: Large Language Model (LLM — Groq)**:
   - Billed per input/output tokens (live-captured via `UsageMetricsTap`):
     $$C_{\text{llm\_usd}} = \left( \frac{T_{\text{llm\_in}}}{1,000,000} \times R_{\text{llm\_in\_usd}} \right) + \left( \frac{T_{\text{llm\_out}}}{1,000,000} \times R_{\text{llm\_out\_usd}} \right)$$
     $$C_{\text{llm\_inr}} = C_{\text{llm\_usd}} \times \text{USD\_INR}$$

4. **Component 4: Text-to-Speech (TTS — Cartesia)**:
   - Billed per 1,000 synthesized characters (live-captured via `UsageMetricsTap`):
     $$C_{\text{tts\_inr}} = \frac{\text{Chars}_{\text{tts}}}{1,000} \times R_{\text{tts\_usd\_1k}} \times \text{USD\_INR}$$

5. **Post-Call Processing Fee ($C_{\text{post\_call}}$)**:
   - Fixed fee of **₹0.25** applied at post-call extraction.

---

## 2.3 End-to-End Lifecycle & Technical Mechanics

### Phase 1: Pre-Reservation Hold
- Same atomic conditional UPDATE on `campaigns` table (see Section 1.3 Phase 1).

### Phase 2: Live In-Memory Monitoring
- `UsageMetricsTap` tracks LLM tokens (`llm_prompt_tokens`, `llm_completion_tokens`) and TTS characters (`tts_characters`) per frame.
- **STT duration**: Not tracked by `UsageMetricsTap`. Derived from `duration_seconds` at settlement.
- Redis snapshot of active call cost to `active_call:{call_id}:cost` (to be implemented).

### Phase 3: Post-Call Settlement
- Post-call processor computes itemized component costs.
- Saves component breakdown into new `call_logs` columns (to be added via migration).

---

# SECTION 3: NATIVE DASHBOARD OBSERVABILITY & ALERTING ARCHITECTURE

## 3.1 Why Native React Dashboard Over Grafana?

Rather than adding a third-party Grafana container requiring separate logins, plugins, and volume configurations, Aakashvani uses a **Native Integrated Observability Architecture** built directly into the existing FastAPI backend and React frontend ([`frontend/`](file:///home/satyam/aakashvani/frontend/)):

### Architectural Advantages:
1. **Zero Extra Infrastructure Overhead**: Eliminates extra Docker service dependencies and RAM overhead.
2. **Unified Authentication**: Admins and Clients view their metrics directly inside their existing JWT-authenticated dashboard.
3. **Role-Based Visibility**: Clients see their live campaign budget burn and call logs; Admins see vendor cost breakdowns, `profit_credits`, and margin % analytics.

## 3.2 Backend Endpoints & Native Alerting

### 1. Live Active Call Burn Rate (`GET /api/internal/metrics/live-burn`)
- Reads active call snapshots from Redis (`active_call:*:cost`) and returns real-time active call count, running cost burn rate (INR/sec), and route split.

### 2. Settled Revenue & Realized Margins (`GET /api/internal/metrics/margins`)
- Queries `call_logs` in PostgreSQL and returns total billed revenue, vendor cost, net profit, and margin %.

### 3. Wallet Health & Underflow List (`GET /api/internal/metrics/underflow-alerts`)
- Queries `clients` with `balance_credits < threshold` and `campaigns` where `budget_credits - budget_used_credits < 0`.

### 4. Automated Event-Driven Alerts
- When a campaign underflows or client balance drops below threshold, [`post_call_processor.py`](file:///home/satyam/aakashvani/post_call_processor.py) directly triggers an automated alert via [`n8n_webhook.py`](file:///home/satyam/aakashvani/n8n_webhook.py).

---

# SECTION 4: TECHNICAL IMPLEMENTATION PLAN

## 4.0 Current State of the Codebase (Verified)

| Aspect | Current State | Required State |
| :--- | :--- | :--- |
| **Billing model** | Flat `credits_per_minute` × `ceil(duration/60)` in [`post_call_processor.py:392-395`](file:///home/satyam/aakashvani/post_call_processor.py#L392) | Component-level token/duration billing with margin |
| **Token usage** | Captured by `UsageMetricsAccumulator` but **ignored for billing**. Written to `call_logs` as metrics only. | Used as primary billing input |
| **STT tracking** | **Not tracked at all** — no `STTUsageMetricsData` in Pipecat | Derived from `duration_seconds` at settlement |
| **Budget reservation** | `RESERVE_CREDITS_PER_LEAD = 2.0` credits, **no atomicity guard** — `adjust_budget_used` has no WHERE clause | Atomic conditional UPDATE with balance check |
| **Redis live snapshots** | **Does not exist** — Redis only used for dialer locks | Active call cost snapshots every 5s |
| **`call_logs` schema** | Single `credits_charged` column. No component breakdown. | Itemized: `fixed_credits_charged`, `variable_credits_charged`, `stt_credits_charged`, `llm_credits_charged`, `tts_credits_charged`, `post_call_credits_charged`, `profit_credits` |
| **`bot_configs` schema** | Single `credits_per_minute` column | Per-component USD rates, margin %, post-call fee |
| **Cascaded providers** | Hardcoded: Sarvam STT + Groq LLM + Cartesia TTS | Same, with configurable rates for future vendors |
| **STS token separation** | Aggregate prompt/completion tokens (audio+text combined) | Use aggregate tokens with blended rates |
| **Plivo setup fee** | Not tracked separately — bundled into `credits_per_minute` | Explicit `fixed_start_credits` on every dial attempt |
| **Campaign underflow** | Not handled — no auto-pause on negative budget | Auto-pause + deficit settled from client balance |
| **Observability endpoints** | None | 3 new FastAPI endpoints for admin dashboard |

---

## 4.1 Database Schema Changes

### File: New migration `alembic/versions/011_credit_system_redesign.py`

**ADD columns to `bot_configs`**:
```sql
-- Telephony
fixed_start_credits NUMERIC(6,4) NOT NULL DEFAULT 0.6000   -- Plivo setup fee (INR)
fixed_per_minute_credits NUMERIC(6,4) NOT NULL DEFAULT 0.5000  -- Platform fixed cost per started minute (INR)

-- STS rates (gemini-3.1-flash-live-preview, audio+text blended)
sts_input_usd_per_1m NUMERIC(10,4) DEFAULT 3.0000    -- Blended input rate
sts_output_usd_per_1m NUMERIC(10,4) DEFAULT 12.0000   -- Blended output rate

-- Cascaded rates (Sarvam + Groq + Cartesia)
stt_usd_per_min NUMERIC(10,4) DEFAULT 0.0060           -- Sarvam STT per audio minute
llm_input_usd_per_1m NUMERIC(10,4) DEFAULT 0.1500     -- Groq input per 1M tokens
llm_output_usd_per_1m NUMERIC(10,4) DEFAULT 0.6000    -- Groq output per 1M tokens
tts_usd_per_1k_chars NUMERIC(10,4) DEFAULT 0.0150     -- Cartesia per 1K chars

-- Profit & overhead
profit_margin_percent NUMERIC(6,2) NOT NULL DEFAULT 25.00
post_call_fee_credits NUMERIC(6,4) NOT NULL DEFAULT 0.2500
```

**ADD columns to `call_logs`**:
```sql
fixed_credits_charged NUMERIC(10,4) DEFAULT 0
variable_credits_charged NUMERIC(10,4) DEFAULT 0
post_call_credits_charged NUMERIC(10,4) DEFAULT 0
stt_credits_charged NUMERIC(10,4) DEFAULT 0
llm_credits_charged NUMERIC(10,4) DEFAULT 0
tts_credits_charged NUMERIC(10,4) DEFAULT 0
profit_credits NUMERIC(10,4) DEFAULT 0
```

**DO NOT remove** `credits_per_minute` from `bot_configs` or `credits_charged` from `call_logs` — keep for backward compatibility during rollout.

---

## 4.2 Files to MODIFY

### 1. [`pricing_sts.py`](file:///home/satyam/aakashvani/pricing_sts.py)
- **Current**: Single function `compute_sts_cost_inr()` using env vars, returns an estimate, result is never used for billing.
- **Change**: Add `calculate_sts_call_cost(duration_seconds, prompt_tokens, completion_tokens, bot_config)` that computes telephony + Gemini token cost + margin + post-call fee. Keep old function for backward compat.

### 2. [`post_call_processor.py`](file:///home/satyam/aakashvani/post_call_processor.py)
- **Current** (lines 392-395): `credits_charged = billed_minutes * credits_per_minute`.
- **Change**: Route-aware billing:
  - If `route == "sts"`: Call `calculate_sts_call_cost()`.
  - If `route == "cascaded"`: Call new `calculate_cascaded_call_cost()`.
  - Pass component breakdown to `finalize_call_log`.

### 3. [`db/postgres.py`](file:///home/satyam/aakashvani/db/postgres.py)
- **`adjust_budget_used`** (line 1265): Add WHERE clause for atomic balance check.
- **`reserve_campaign_budget`** (line 1293): Compute dynamic reservation amount from bot_config rates instead of static `RESERVE_CREDITS_PER_LEAD = 2.0`.
- **`finalize_call_log`**: Add new columns to the UPDATE statement.
- **`create_bot_config` / `update_bot_config`**: Add new pricing columns.
- **New function**: `maybe_auto_pause_underflow_campaign()` — pause campaign and deduct deficit from client `balance_credits`.

### 4. [`call_metrics.py`](file:///home/satyam/aakashvani/call_metrics.py)
- **No changes to capture logic** — `UsageMetricsAccumulator` already tracks all needed fields.
- **Add**: `estimate_running_cost_inr(bot_config, route, duration_seconds)` method for Redis live snapshot computation.

### 5. [`bot_sts.py`](file:///home/satyam/aakashvani/bot_sts.py) & [`bot_cascade.py`](file:///home/satyam/aakashvani/bot_cascade.py)
- **Add**: Redis snapshot writer that publishes `active_call:{session_call_id}:cost` JSON every 5 seconds during active calls.
- **Add**: Pass `bot_config` pricing fields into the pipeline context so `UsageMetricsAccumulator` can estimate live cost.

### 6. [`call_limits.py`](file:///home/satyam/aakashvani/call_limits.py)
- **Add**: Minute boundary ticker that increments started-minutes counter at 60s intervals (lightweight asyncio timer alongside existing watchdog).

### 7. [`dialer/cost_guard.py`](file:///home/satyam/aakashvani/dialer/cost_guard.py)
- **Change**: `MIN_REMAINING_CREDITS` from static `RESERVE_CREDITS_PER_LEAD` to dynamic reservation based on `bot_config.fixed_start_credits + bot_config.fixed_per_minute_credits + estimated_variable_buffer`.

### 8. [`api/routes/internal.py`](file:///home/satyam/aakashvani/api/routes/internal.py)
- **Change**: `BotConfigCreate` and `BotConfigUpdate` Pydantic models to include new pricing fields.
- **Keep**: `credits_per_minute` field as optional for backward compat.

---

## 4.3 Files to ADD

### 1. `alembic/versions/011_credit_system_redesign.py`
- Migration adding new columns to `bot_configs` and `call_logs`.

### 2. `pricing_cascade.py` (new file)
- `calculate_cascaded_call_cost(duration_seconds, usage, bot_config)` → returns itemized component costs.

### 3. `api/routes/metrics.py` (new file)
- Three admin endpoints: `/api/internal/metrics/live-burn`, `/api/internal/metrics/margins`, `/api/internal/metrics/underflow-alerts`.

### 4. Frontend Admin Billing Components
- Admin Bot Config form fields for new pricing columns.
- Call log detail view showing component cost breakdown.
- Admin dashboard revenue/margin analytics panel.

---

## 4.4 Files to NOT CHANGE

- [`call_transcript.py`](file:///home/satyam/aakashvani/call_transcript.py) — Transcript logic is billing-independent.
- [`call_log_db.py`](file:///home/satyam/aakashvani/call_log_db.py) — SQLite call log (local dev only), not used in production billing.
- [`script_runtime.py`](file:///home/satyam/aakashvani/script_runtime.py) — No pricing config belongs in script runtime.
- `cascade_scripts/*.py` and `sts_scripts/*.py` — Scripts define conversation behavior, not billing.
- [`n8n_webhook.py`](file:///home/satyam/aakashvani/n8n_webhook.py) — May optionally add component breakdown to webhook payload later, but not required for initial rollout.

---

## 4.5 Rollout Strategy

### Phase A: Schema + Pricing Engine (No Billing Change Yet)
1. Deploy migration `011_credit_system_redesign.py` — adds new columns with defaults, old `credits_per_minute` untouched.
2. Deploy updated `pricing_sts.py` and new `pricing_cascade.py` — calculate new costs but write them to `variable_credits_charged`, `profit_credits` etc. as **shadow columns** only.
3. Continue using old `credits_charged = billed_minutes * credits_per_minute` for actual billing.
4. Compare shadow vs actual charges across ~1000 calls to validate pricing accuracy.

### Phase B: Switch Billing Source
1. Flip `post_call_processor.py` to use new pricing engine for `credits_charged`.
2. Deploy atomic budget reservation SQL.
3. Enable auto-pause on campaign underflow.

### Phase C: Observability & Dashboard
1. Deploy Redis live snapshots.
2. Deploy admin metrics API endpoints.
3. Deploy frontend billing analytics components.

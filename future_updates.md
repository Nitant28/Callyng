# Future Architecture Updates: Path to Enterprise Scale

This document outlines the major architectural upgrades required to take Aakashvani from a single-client pilot to a highly available, multi-tenant enterprise dialer. 

These updates are designed to resolve current single-server bottlenecks and ensure robustness when scaling horizontally.

## 1. Distributed Task Management (Redis / Celery)
**The Problem:** Currently, dialer loops (`asyncio.create_task`) are managed in the local memory of the python process (`_active_tasks` dict). If you run multiple server workers (e.g., Gunicorn with 4 workers) or multiple instances behind a load balancer, a "Start Campaign" request runs the dialer on one worker, but a "Pause Campaign" request might route to a different worker, failing to stop the active dialer.
**The Fix:** 
- Implement a distributed message broker (Redis/RabbitMQ) and a task queue (Celery, ARQ, or Temporal).
- Move the dialer loop out of the main API server and into dedicated dialer worker nodes.
- **Estimated Time to Implement:** 1-2 weeks.

## 2. Global Rate Limiting
**The Problem:** Outbound calls are paced using a localized `asyncio.sleep(60 / cpm)`. If the system is horizontally scaled across 3 servers, a 30 CPM limit effectively becomes 90 CPM.
**The Fix:**
- Implement a Redis-backed token bucket algorithm for global, cross-server rate limiting per client and per campaign.
- **Estimated Time to Implement:** 2-4 days.

## 3. Auto-Resume Campaigns on Server Restart (COMPLETED)
**The Problem:** If the server reboots, deploys an update, or crashes, the local memory is cleared. Campaigns with a `running` status in the database are left frozen because their dialer loops are not automatically restarted.
**The Fix (Applied):**
- Added a startup hook in the server's `lifespan` to query Postgres for all campaigns where `status = 'running'` and auto-launch their dialer tasks.

## 4. Database Connection Pool Scaling (COMPLETED)
**The Problem:** The `asyncpg` connection pool was hardcoded to a maximum of 20 connections, risking connection starvation (`TimeoutError`).
**The Fix (Applied):**
- Exposed the pool size to environment variables (`DB_POOL_MIN`, `DB_POOL_MAX`) defaulting to 5 and 50 respectively.
- Future consideration: Introduce PgBouncer as a connection multiplexer if active connections still exceed Postgres limits.

## 5. Audited Security Logging System
**The Problem:** The "Recent Activity / Security Logs" card on the admin dashboard currently displays mock logs. There is no active backend mechanism to track critical admin operations, API key lifecycle actions, or client credit adjustments, creating a security audit gap.
**The Fix:**
- **Database Schema:** Create a database table `audit_logs` to store UUID identifiers, timestamps, actor types (`admin`, `client`, `system`), event types (e.g., `login_success`, `api_key_regenerate`, `credits_adjusted`), IP addresses, user agents, and context metadata in a JSONB field.
- **Backend Logging Helper:** Implement a global `log_security_event` helper in the backend to capture API key rotations, credit adjustments, onboarding actions, and admin login attempts (including failed attempts for brute-force alerting).
- **Audit Logs API:** Build a new route `GET /internal/audit-logs` that exposes a paginated list of security logs.
- **Frontend Dashboard Integration:** Wire the "Security Logs" component in `AdminOverview.jsx` to fetch recent events from the backend, mapping them to icons (`verified_user`, `lock_reset`, `payments`), and implement a dedicated `/admin/security-logs` page for full administrative audits.
- **Estimated Time to Implement:** 3-5 days.

## 6. Pipecat Analytics & Cost Monitoring Integration
**The Problem:** Currently, the system lacks granular tracing of LLM token usage, execution times, and agent-specific conversational metrics, making cost attribution and performance tuning difficult.
**The Fix:**
- Integrate **OpenInference** (`openinference-instrumentation-pipecat`) for comprehensive LLM tracing, allowing exact cost calculation based on token consumption and execution latency.
- Integrate **Sentry** (`pipecat-ai[sentry]`) to track errors and performance bottlenecks in text-to-speech and LLM requests.
- Explore specialized voice agent platforms (like **Roark** or **Future AGI**) to monitor conversational metrics (e.g., user interruption rates, average conversation lengths) to optimize the AI's behavior and estimate aggregate infrastructure costs.
- **Estimated Time to Implement:** 3-5 days.

## 7. Granular Per-Call Financial Cost Accounting
**The Problem:** While the system deducts internal credits from a client's balance based on a fixed rate, it does not currently compute or store the exact real-world API costs incurred per call (e.g., Plivo SIP minutes, LLM tokens, STT seconds, TTS characters). This makes it impossible to track precise profit margins or identify runaway infrastructure costs per campaign.
**The Fix:**
- **Database Schema Expansion:** Add specific cost-tracking columns to the `call_logs` table: `llm_cost_usd`, `tts_cost_usd`, `stt_cost_usd`, `telephony_cost_usd`, and `total_api_cost_usd`.
- **Pipeline Metrics Interception:** Update the Pipecat agent (`bot.py`) to subscribe to usage metrics events. As the call progresses, intercept the exact number of STT audio seconds processed, LLM input/output tokens generated, and TTS characters synthesized.
- **Dynamic Cost Calculation:** At call termination (or inside the Plivo hangup webhook), calculate the precise costs:
  - Plivo telephony cost (often provided directly in the hangup webhook payload, or computed via exact duration × SIP trunk rate).
  - STT cost = seconds × Deepgram rate.
  - LLM cost = (Input Tokens × input rate) + (Output Tokens × output rate).
  - TTS cost = characters × Cartesia/ElevenLabs rate.
- **Dashboard Profitability Metrics:** Aggregate the `total_api_cost_usd` against the `billed_credits` on the admin dashboard, providing a live "Gross Margin" metric and alerting the admin if a specific campaign is operating at a loss.
- **Estimated Time to Implement:** 2-3 days.

## 8. Gemini Live (STS) Bot Optimization (First-Sentence Dead Air Fix)
**The Problem:** Using Pipecat's `MuteUntilFirstBotCompleteUserMuteStrategy` to make the first sentence uninterruptible with a native STS (Speech-to-Speech) model like Gemini Live causes a 50% dead air pause. Because STS takes raw audio directly, muting the user physically discards their speech frames. When the bot finishes its greeting, the user is waiting for a reply to the words they just spoke, but Gemini heard nothing.
**The Fix Options:**
- **Option 1: Audio Buffering Strategy (Best Technical Solution):** Build a custom Pipecat component to replace the mute strategy. It will buffer incoming `AudioRawFrame`s while the bot speaks its first sentence, then immediately flush them to the Gemini API upon completion, solving the pause.
- **Option 2: Pre-recorded Initial Greeting (Enterprise Standard):** Use Pipecat's `PlayAudioAction` (or the telephony provider directly) to play a static `.wav` greeting file before connecting the live audio stream to Gemini, guaranteeing an uninterruptible greeting without causing STS sync issues.
- **Option 3: Lean into STS Superpowers (AI Native):** Remove the Pipecat mute strategy entirely and allow interruptions. Rely on Gemini Live's native full-duplex ability to handle early interjections gracefully, supported by a strict system prompt to keep the first sentence extremely brief.

## 9. Cascade Route Upgrades (TTS / STT Resilience)
**The Problem:** To achieve maximum reliability and localization (especially for Indian languages), the STT -> LLM -> TTS cascaded pipeline requires best-in-class models and failover options.
**The Fix (In Progress):**
- **Sarvam AI (COMPLETED):** Sarvam AI is already integrated and successfully connected in `bot_cascade.py` (`SarvamSTTService`) to handle native Indian language speech-to-text with superior accuracy and lower latency.
- **ElevenLabs Integration (PENDING):** While the `elevenlabs` extension is already installed via `pyproject.toml`, the current pipeline in `bot_cascade.py` hardcodes Cartesia (`CartesiaTTSService`) for text-to-speech. We need to wire ElevenLabs into the bot as a premium fallback or alternative TTS provider to offer highly realistic, emotive voices.

## 10. Dynamic Provider Injection (Frontend Configurable STT / LLM / TTS)
**The Problem:** Currently, the cascade pipeline in `bot_cascade.py` hardcodes the providers (`SarvamSTTService`, `GroqLLMService`, `CartesiaTTSService`). This prevents admins or clients from seamlessly swapping out AI models (e.g., switching from Cartesia to ElevenLabs, or Groq to OpenAI) directly from the frontend UI without changing backend code.
**The Fix:**
- **Provider Factory Pattern:** Implement factory functions (e.g., `create_stt_service(provider_name, config)`, `create_tts_service(...)`) that map string identifiers from the frontend to their respective Pipecat service classes. 
- **API/Frontend Payload Extension:** Update the dashboard to send provider preferences in the call payload (e.g., `body["bot_config"]["tts_provider"] = "elevenlabs"`).
- **Dynamic Pipeline Assembly:** In `bot_cascade.py`, replace the hardcoded instantiations with the factory outputs. Because Pipecat's `Pipeline` accepts generic service instances, the pipeline architecture (`Pipeline([transport.input(), stt, user_aggregator, llm, tts, transport.output()...])`) remains identical regardless of the underlying providers.
- **Unified Settings Management:** Since different providers have different setting structures (e.g., `ElevenLabsTTSService.Settings` vs `CartesiaTTSService.Settings`), the factory must abstract the mapping of frontend values (like voice IDs and speeds) into the provider-specific Pydantic models.

## 11. Model-Specific Parameter Validation & UI Constraints
**The Problem:** As you introduce dynamic providers, you will encounter the issue that different models have distinct configuration capabilities. For example, ElevenLabs v3 models might not support `speed` adjustments, while v2.5 does. Cartesia might support emotion controls that ElevenLabs does not. If the frontend blindly sends unsupported parameters in the configuration payload, the provider's API will reject the connection or Pipecat will crash upon initialization.
**The Fix:**
- **Backend Validation Schemas:** Build strict Pydantic schemas for each provider/model combination. When `body["bot_config"]` is received, the backend must validate the requested parameters against the known capabilities of that specific model before passing them to the Pipecat factory.
- **Dynamic Frontend UI:** The admin dashboard must become context-aware. When a user selects a specific TTS or LLM model from a dropdown, the frontend should dynamically show/hide the relevant configuration fields (e.g., hiding the "Speed" slider if the selected ElevenLabs model doesn't support it).

# Per-Campaign Call Duration & Extraction Schema Overrides

## Overview
This handoff document details the changes made to support per-campaign overrides for maximum call duration (`max_call_minutes`) and extraction schema (`extraction_schema_override`).

The implementation passes these settings directly via the `_pg` body dictionary during call initiation. This avoids adding synchronous database lookups to the high-performance `/answer` or WebSocket routes, which is crucial for scalability.

## Changes Made

### 1. Database Updates
- **Migration**: Added `db/schema/003_campaign_max_call_minutes.sql` to append `max_call_minutes INTEGER DEFAULT NULL` to the `campaigns` table.
- **Queries**: Updated `db/postgres.py` (`create_campaign` and `update_campaign_settings`) to accept and insert/update `max_call_minutes`.
- **API Models**: Added `max_call_minutes` to `CreateCampaignBody` and `PatchCampaignBody` in `api/routes/internal.py`.

### 2. Dialer Pass-through (`dialer/concurrent_dialer.py`)
- Extracted `max_call_minutes` and `extraction_schema_override` from the `campaign` record.
- Injected these values directly into `body_data["_pg"]` inside `fire_call()`. This allows downstream components to read them dynamically without performing extra database queries.

### 3. Call Duration Enforcement (`call_limits.py`, `bot_sts.py`, `bot_cascade.py`)
- **`call_limits.py`**: Modified `parse_max_call_minutes` to accept an optional `override` parameter. If provided and > 0, it takes precedence over the server-wide `MAX_CALL_MINUTES` environment variable.
- **Bots (`bot_sts.py` & `bot_cascade.py`)**: 
  - Extracted `max_call_minutes` from the incoming `_pg` metadata.
  - Passed this value into `parse_max_call_minutes()`.
  - The watchdog timer (`schedule_max_call_duration`) now strictly respects the campaign-specific time limit.

### 4. Dynamic Extraction Schema (`bot_sts.py`, `bot_cascade.py`)
- Extracted `extraction_schema_override` from the incoming `_pg` metadata.
- Updated both `bot_sts.py` and `bot_cascade.py` to prefer the `extraction_schema_override` from `_pg`. If unset (or `None`), it falls back to the default `EXTRACTION_SCHEMA` defined in the active script module.
- Passed this resolved schema into `attach_pipeline_finalize()`.

## Architectural Decisions
- **Minimal overhead**: Changes were strictly confined to areas processing existing context maps (`_pg`), adhering to the requirement of not issuing sync DB requests on the hot paths.
- **Backward compatibility**: The `parse_max_call_minutes` continues functioning gracefully with server-wide environment variables when overrides are not specified.
- **Resilience**: Handled missing or empty JSON properties optimally by defaulting gracefully. Asyncpg handles JSONB to Python dict parsing out of the box, mapping perfectly into Pipecat configurations.

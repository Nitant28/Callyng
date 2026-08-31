# Aakashvani WhatsApp / Messages Module

## What this module does

Tracks WhatsApp conversations, messages, templates, and delivery statuses for
every Aakashvani client. It sits alongside the existing Calls/Campaigns engine
and the n8n automation layer.

## Quick links

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level architecture + data flow |
| [PROVIDER_SYSTEM.md](PROVIDER_SYSTEM.md) | Provider abstraction and how to add a new BSP |
| [N8N_SETUP.md](N8N_SETUP.md) | How n8n triggers WhatsApp sends |
| [WEBHOOKS.md](WEBHOOKS.md) | Inbound webhook processing |
| [FOLLOWUPS.md](FOLLOWUPS.md) | Automated follow-up sequences |
| [SECURITY.md](SECURITY.md) | Credential handling, tenant isolation, write-only secrets |

## Current status

| Layer | Status |
|-------|--------|
| Database schema (4 + 2 tables) | ✅ Live |
| Provider abstraction (Stub, Meta, Custom, pending slots) | ✅ Live |
| Send API (`POST /internal/messages/send`) | ✅ Live |
| Inbound webhook persist | ✅ Live |
| Follow-up engine | ✅ Live |
| Admin provider-aware UI | ✅ Live |
| Client Messages inbox | ✅ Live |
| Meta Cloud real credentials | ⏳ Requires client's access token |
| FinBite / Wapi adapters | ⏳ Requires vendor API documentation |

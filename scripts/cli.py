#!/usr/bin/env python3
"""Aakashvani CLI — operator powertools for database inspection and management.

See guides/CLI_GUIDE.md for full command reference and examples.

Usage:
    PYTHONPATH=. uv run python scripts/cli.py <command> [args...]

All commands connect directly to Postgres via DATABASE_URL (no running server needed).
Name-based lookups use case-insensitive fuzzy matching on the `name` column.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env", override=True)


# ── Formatting helpers ────────────────────────────────────────────────────────

_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def _header(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'─' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'─' * 60}{_RESET}")


def _kv(key: str, value: Any, indent: int = 2) -> None:
    """Print a key-value pair with formatting."""
    pad = " " * indent
    if value is None:
        print(f"{pad}{_DIM}{key}:{_RESET} {_DIM}—{_RESET}")
    elif isinstance(value, bool):
        color = _GREEN if value else _RED
        print(f"{pad}{_DIM}{key}:{_RESET} {_c(str(value), color)}")
    elif isinstance(value, (int, float)):
        print(f"{pad}{_DIM}{key}:{_RESET} {_c(str(value), _YELLOW)}")
    else:
        print(f"{pad}{_DIM}{key}:{_RESET} {value}")


def _status_color(status: str) -> str:
    colors = {
        "running": _GREEN,
        "completed": _CYAN,
        "draft": _DIM,
        "paused": _YELLOW,
        "cancelled": _RED,
        "pending": _DIM,
        "calling": _GREEN,
        "failed": _RED,
        "dnc": _RED,
        "callback_scheduled": _YELLOW,
    }
    color = colors.get(status, "")
    return _c(status, color) if color else status


def _outcome_color(outcome: str | None) -> str:
    if not outcome:
        return _c("—", _DIM)
    colors = {
        "Interested": _GREEN,
        "Not_Interested": _RED,
        "Callback_Requested": _YELLOW,
        "Busy": _DIM,
        "Unknown": _DIM,
        "Wrong_Requirement": _DIM,
    }
    color = colors.get(outcome, "")
    return _c(outcome, color) if color else outcome


def _ts(dt: Any) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(dt)


def _credits(val: Any) -> str:
    if val is None:
        return "—"
    return f"₹{float(val):,.2f}"


def _table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    """Print a simple table. columns: [(header, dict_key, width), ...]."""
    if not rows:
        print(f"  {_DIM}(no rows){_RESET}")
        return

    # Header
    header = "  ".join(h.ljust(w) for h, _, w in columns)
    print(f"  {_BOLD}{header}{_RESET}")
    print(f"  {'─' * len(header)}")

    for row in rows:
        parts = []
        for _, key, w in columns:
            val = row.get(key)
            if key == "status":
                s = _status_color(str(val)) if val else "—"
                parts.append(s.ljust(w + len(s) - len(str(val or "—"))))
            elif key == "outcome":
                s = _outcome_color(val)
                parts.append(s.ljust(w + len(s) - len(str(val or "—"))))
            elif "credits" in key or key in ("balance_credits",):
                parts.append(_credits(val).ljust(w))
            elif isinstance(val, datetime):
                parts.append(_ts(val).ljust(w))
            elif isinstance(val, UUID):
                parts.append(str(val)[:8].ljust(w))
            elif val is None:
                parts.append("—".ljust(w))
            else:
                s = str(val)
                parts.append((s[:w] if len(s) > w else s.ljust(w)))
        print(f"  {'  '.join(parts)}")


def _json_compact(obj: Any, max_len: int = 120) -> str:
    if obj is None:
        return "—"
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except (json.JSONDecodeError, TypeError):
            return obj[:max_len]
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


# ── DB connection ─────────────────────────────────────────────────────────────


async def _get_pool():
    import asyncpg

    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        print(f"{_RED}ERROR: DATABASE_URL is not set in .env{_RESET}", file=sys.stderr)
        sys.exit(1)
    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, command_timeout=30)


# ── Name resolution ──────────────────────────────────────────────────────────


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except ValueError:
        return False


async def _resolve_client(pool, name_or_id: str) -> dict:
    """Resolve a client by UUID or fuzzy name match."""
    if _is_uuid(name_or_id):
        row = await pool.fetchrow("SELECT * FROM clients WHERE id = $1", UUID(name_or_id))
        if row is None:
            print(f"{_RED}Client not found: {name_or_id}{_RESET}", file=sys.stderr)
            sys.exit(1)
        return dict(row)

    rows = await pool.fetch(
        "SELECT * FROM clients WHERE name ILIKE $1 AND active = TRUE ORDER BY created_at DESC",
        f"%{name_or_id}%",
    )
    if not rows:
        print(f"{_RED}No client matching '{name_or_id}'{_RESET}", file=sys.stderr)
        sys.exit(1)
    if len(rows) > 1:
        print(f"{_YELLOW}Multiple clients match '{name_or_id}':{_RESET}")
        for r in rows:
            print(f"  {r['id']}  {r['name']}")
        print(f"\n{_DIM}Be more specific or use the full UUID.{_RESET}")
        sys.exit(1)
    return dict(rows[0])


async def _resolve_campaign(pool, name_or_id: str) -> dict:
    """Resolve a campaign by UUID or fuzzy name match."""
    if _is_uuid(name_or_id):
        row = await pool.fetchrow("SELECT * FROM campaigns WHERE id = $1", UUID(name_or_id))
        if row is None:
            print(f"{_RED}Campaign not found: {name_or_id}{_RESET}", file=sys.stderr)
            sys.exit(1)
        return dict(row)

    rows = await pool.fetch(
        "SELECT * FROM campaigns WHERE name ILIKE $1 ORDER BY created_at DESC",
        f"%{name_or_id}%",
    )
    if not rows:
        print(f"{_RED}No campaign matching '{name_or_id}'{_RESET}", file=sys.stderr)
        sys.exit(1)
    if len(rows) > 1:
        print(f"{_YELLOW}Multiple campaigns match '{name_or_id}':{_RESET}")
        for r in rows:
            print(f"  {r['id']}  {r['name']}  ({r['status']})")
        print(f"\n{_DIM}Be more specific or use the full UUID.{_RESET}")
        sys.exit(1)
    return dict(rows[0])


async def _resolve_lead(pool, id_or_phone: str, campaign_id: UUID | None = None) -> dict:
    """Resolve a lead by UUID or phone number."""
    if _is_uuid(id_or_phone):
        row = await pool.fetchrow("SELECT * FROM leads WHERE id = $1", UUID(id_or_phone))
        if row is None:
            print(f"{_RED}Lead not found: {id_or_phone}{_RESET}", file=sys.stderr)
            sys.exit(1)
        return dict(row)

    # Phone lookup
    phone = id_or_phone if id_or_phone.startswith("+") else f"+91{id_or_phone.lstrip('0')}"
    if campaign_id:
        row = await pool.fetchrow(
            "SELECT * FROM leads WHERE phone = $1 AND campaign_id = $2",
            phone, campaign_id,
        )
    else:
        row = await pool.fetchrow(
            "SELECT * FROM leads WHERE phone = $1 ORDER BY created_at DESC LIMIT 1",
            phone,
        )
    if row is None:
        print(f"{_RED}Lead not found for phone: {phone}{_RESET}", file=sys.stderr)
        sys.exit(1)
    return dict(row)


# ── Client commands ───────────────────────────────────────────────────────────


async def cmd_show_client(args):
    pool = await _get_pool()
    try:
        client = await _resolve_client(pool, args.name_or_id)
        cid = client["id"]

        _header(f"Client: {client['name']}")
        _kv("ID", cid)
        _kv("Email", client.get("contact_email"))
        _kv("Industry", client.get("industry"))
        _kv("Balance", _credits(client.get("balance_credits")))
        _kv("Max Concurrent Calls", client.get("max_concurrent_calls"))
        _kv("Active", client.get("active"))
        _kv("Created", _ts(client.get("created_at")))

        # Campaign summary
        camps = await pool.fetch(
            "SELECT id, name, status, budget_credits, budget_used_credits, total_leads "
            "FROM campaigns WHERE client_id = $1 ORDER BY created_at DESC", cid,
        )
        print(f"\n  {_BOLD}Campaigns ({len(camps)}):{_RESET}")
        _table(
            [dict(r) for r in camps],
            [("Name", "name", 25), ("Status", "status", 12), ("Budget", "budget_credits", 12),
             ("Used", "budget_used_credits", 12), ("Leads", "total_leads", 8)],
        )
    finally:
        await pool.close()


async def cmd_client_bots(args):
    pool = await _get_pool()
    try:
        client = await _resolve_client(pool, args.name_or_id)
        cid = client["id"]

        bots = await pool.fetch(
            "SELECT * FROM bot_configs WHERE client_id = $1 ORDER BY created_at DESC", cid,
        )
        _header(f"Bot Configs for {client['name']} ({len(bots)})")
        _table(
            [dict(r) for r in bots],
            [("ID", "id", 36), ("Name", "name", 30), ("Route", "route", 10),
             ("Script", "script_id", 20), ("₹/min", "credits_per_minute", 8)],
        )
    finally:
        await pool.close()


async def cmd_client_campaigns(args):
    pool = await _get_pool()
    try:
        client = await _resolve_client(pool, args.name_or_id)
        cid = client["id"]

        camps = await pool.fetch(
            """SELECT c.*, b.name AS bot_name, b.script_id
               FROM campaigns c
               JOIN bot_configs b ON b.id = c.bot_config_id
               WHERE c.client_id = $1
               ORDER BY c.created_at DESC""",
            cid,
        )
        _header(f"Campaigns for {client['name']} ({len(camps)})")
        _table(
            [dict(r) for r in camps],
            [("Name", "name", 22), ("Status", "status", 12), ("Bot", "bot_name", 20),
             ("Total", "total_leads", 6), ("Pending", "pending_leads", 7),
             ("Calling", "calling_leads", 7), ("Done", "completed_leads", 6),
             ("Failed", "failed_leads", 6)],
        )
    finally:
        await pool.close()


async def cmd_client_webhooks(args):
    pool = await _get_pool()
    try:
        client = await _resolve_client(pool, args.name_or_id)
        cid = client["id"]

        hooks = await pool.fetch(
            "SELECT * FROM webhook_configs WHERE client_id = $1 ORDER BY event ASC", cid,
        )
        _header(f"Webhooks for {client['name']} ({len(hooks)})")
        _table(
            [dict(r) for r in hooks],
            [("Event", "event", 25), ("URL", "url", 40), ("Active", "active", 8)],
        )
    finally:
        await pool.close()


# ── Campaign commands ─────────────────────────────────────────────────────────


async def cmd_show_campaign(args):
    pool = await _get_pool()
    try:
        camp = await _resolve_campaign(pool, args.name_or_id)
        cid = camp["client_id"]

        client = await pool.fetchrow("SELECT name FROM clients WHERE id = $1", cid)
        bot = await pool.fetchrow("SELECT name, route, script_id, credits_per_minute FROM bot_configs WHERE id = $1", camp["bot_config_id"])

        _header(f"Campaign: {camp['name']}")
        _kv("ID", camp["id"])
        _kv("Client", client["name"] if client else "?")
        _kv("Client ID", cid)
        _kv("Status", _status_color(camp["status"]))
        _kv("Created", _ts(camp.get("created_at")))
        _kv("Completed", _ts(camp.get("completed_at")))

        print(f"\n  {_BOLD}Bot Config:{_RESET}")
        if bot:
            _kv("Name", bot["name"], indent=4)
            _kv("Route", bot["route"], indent=4)
            _kv("Script", bot["script_id"], indent=4)
            _kv("Credits/min", bot["credits_per_minute"], indent=4)

        print(f"\n  {_BOLD}Budget:{_RESET}")
        budget = float(camp.get("budget_credits") or 0)
        used = float(camp.get("budget_used_credits") or 0)
        remaining = budget - used
        _kv("Allocated", _credits(budget), indent=4)
        _kv("Used", _credits(used), indent=4)
        _kv("Remaining", _credits(remaining), indent=4)
        _kv("Returned At", _ts(camp.get("budget_returned_at")), indent=4)

        print(f"\n  {_BOLD}Lead Counters:{_RESET}")
        _kv("Total", camp.get("total_leads"), indent=4)
        _kv("Pending", camp.get("pending_leads"), indent=4)
        _kv("Calling", camp.get("calling_leads"), indent=4)
        _kv("Callback", camp.get("callback_leads"), indent=4)
        _kv("Completed", camp.get("completed_leads"), indent=4)
        _kv("Failed", camp.get("failed_leads"), indent=4)
        _kv("DNC", camp.get("dnc_leads"), indent=4)

        print(f"\n  {_BOLD}Dialer Config:{_RESET}")
        _kv("Max Concurrent", camp.get("max_concurrent_calls"), indent=4)
        _kv("Calls/min", camp.get("calls_per_minute"), indent=4)
        _kv("Max Attempts", camp.get("max_attempts"), indent=4)
        _kv("Retry Delay", f"{camp.get('retry_delay_minutes')} min", indent=4)
    finally:
        await pool.close()


async def cmd_campaign_leads(args):
    pool = await _get_pool()
    try:
        camp = await _resolve_campaign(pool, args.name_or_id)
        cid = camp["client_id"]
        camp_id = camp["id"]
        limit = int(args.limit)

        sql = """
            SELECT id, phone, name, status, outcome, attempts, max_attempts,
                   next_attempt_at, last_attempted_at, scheduled_callback_at
            FROM leads
            WHERE campaign_id = $1 AND client_id = $2
        """
        params: list[Any] = [camp_id, cid]
        status_filter = (args.status or "").strip()
        if status_filter:
            sql += " AND status = $3"
            params.append(status_filter)
        sql += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await pool.fetch(sql, *params)
        title = f"Leads in '{camp['name']}'"
        if status_filter:
            title += f" (status={status_filter})"
        _header(f"{title} — showing {len(rows)}/{camp.get('total_leads', '?')}")
        _table(
            [dict(r) for r in rows],
            [("Phone", "phone", 15), ("Name", "name", 18), ("Status", "status", 18),
             ("Outcome", "outcome", 18), ("Att", "attempts", 4), ("Max", "max_attempts", 4),
             ("Next At", "next_attempt_at", 22)],
        )
    finally:
        await pool.close()


async def cmd_campaign_calls(args):
    pool = await _get_pool()
    try:
        camp = await _resolve_campaign(pool, args.name_or_id)
        camp_id = camp["id"]
        limit = int(args.limit)

        rows = await pool.fetch(
            """SELECT cl.session_call_id, cl.started_at, cl.ended_at,
                      cl.duration_seconds, cl.outcome, cl.in_progress,
                      cl.credits_charged, cl.extraction_error,
                      l.phone, l.name AS lead_name
               FROM call_logs cl
               LEFT JOIN leads l ON l.id = cl.lead_id
               WHERE cl.campaign_id = $1
               ORDER BY cl.started_at DESC
               LIMIT $2""",
            camp_id, limit,
        )
        _header(f"Recent Calls for '{camp['name']}' — {len(rows)} shown")
        _table(
            [dict(r) for r in rows],
            [("Session", "session_call_id", 12), ("Phone", "phone", 15),
             ("Lead", "lead_name", 15), ("Duration", "duration_seconds", 8),
             ("Outcome", "outcome", 18), ("Credits", "credits_charged", 10),
             ("Error", "extraction_error", 20)],
        )
    finally:
        await pool.close()


# ── Call / Lead commands ──────────────────────────────────────────────────────


async def cmd_show_call(args):
    pool = await _get_pool()
    try:
        row = await pool.fetchrow(
            "SELECT * FROM call_logs WHERE session_call_id = $1",
            args.session_call_id,
        )
        if row is None:
            print(f"{_RED}Call not found: {args.session_call_id}{_RESET}", file=sys.stderr)
            sys.exit(1)

        call = dict(row)
        _header(f"Call: {args.session_call_id}")
        _kv("ID", call["id"])
        _kv("Session Call ID", call["session_call_id"])
        _kv("Plivo Call SID", call.get("call_sid"))
        _kv("Route", call.get("route"))
        _kv("In Progress", call.get("in_progress"))

        print(f"\n  {_BOLD}Timing:{_RESET}")
        _kv("Started", _ts(call.get("started_at")), indent=4)
        _kv("Ended", _ts(call.get("ended_at")), indent=4)
        _kv("Duration", f"{call.get('duration_seconds') or '—'} sec", indent=4)
        _kv("Billed Minutes", call.get("billed_minutes"), indent=4)

        print(f"\n  {_BOLD}Result:{_RESET}")
        _kv("Outcome", _outcome_color(call.get("outcome")), indent=4)
        _kv("Qualified", call.get("qualified"), indent=4)
        _kv("Credits Charged", _credits(call.get("credits_charged")), indent=4)

        print(f"\n  {_BOLD}Extraction:{_RESET}")
        _kv("Model", call.get("extraction_model"), indent=4)
        _kv("Error", call.get("extraction_error") or "none", indent=4)
        ext = call.get("extraction_json")
        if ext:
            if isinstance(ext, str):
                try:
                    ext = json.loads(ext)
                except json.JSONDecodeError:
                    pass
            if isinstance(ext, dict):
                for k, v in ext.items():
                    _kv(k, v, indent=6)
            else:
                _kv("Raw", _json_compact(ext), indent=4)
        else:
            _kv("Data", "—", indent=4)

        print(f"\n  {_BOLD}Usage:{_RESET}")
        _kv("Prompt Tokens", call.get("usage_prompt_tokens"), indent=4)
        _kv("Completion Tokens", call.get("usage_completion_tokens"), indent=4)
        _kv("Total Tokens", call.get("usage_total_tokens"), indent=4)
        _kv("TTS Characters", call.get("usage_tts_characters"), indent=4)

        # Lead info
        if call.get("lead_id"):
            lead = await pool.fetchrow("SELECT phone, name, status FROM leads WHERE id = $1", call["lead_id"])
            if lead:
                print(f"\n  {_BOLD}Lead:{_RESET}")
                _kv("Phone", lead["phone"], indent=4)
                _kv("Name", lead["name"], indent=4)
                _kv("Status", _status_color(lead["status"]), indent=4)

        # Transcript
        transcript = call.get("transcript")
        if transcript:
            if isinstance(transcript, str):
                try:
                    transcript = json.loads(transcript)
                except json.JSONDecodeError:
                    pass

            if isinstance(transcript, list) and transcript:
                print(f"\n  {_BOLD}Transcript ({len(transcript)} turns):{_RESET}")
                if args.full:
                    for turn in transcript:
                        role = turn.get("role", "?")
                        content = turn.get("content", "")
                        color = _GREEN if role == "assistant" else _CYAN
                        print(f"    {_c(role, color)}: {content}")
                else:
                    for turn in transcript[:10]:
                        role = turn.get("role", "?")
                        content = str(turn.get("content", ""))
                        preview = content[:100] + ("…" if len(content) > 100 else "")
                        color = _GREEN if role == "assistant" else _CYAN
                        print(f"    {_c(role, color)}: {preview}")
                    if len(transcript) > 10:
                        print(f"    {_DIM}… {len(transcript) - 10} more turns (use --full to see all){_RESET}")
            else:
                print(f"\n  {_BOLD}Transcript:{_RESET} {_DIM}(empty){_RESET}")
        else:
            print(f"\n  {_BOLD}Transcript:{_RESET} {_DIM}(not stored in DB){_RESET}")
    finally:
        await pool.close()


async def cmd_show_lead(args):
    pool = await _get_pool()
    try:
        lead = await _resolve_lead(pool, args.id_or_phone)

        _header(f"Lead: {lead.get('name') or lead['phone']}")
        _kv("ID", lead["id"])
        _kv("Phone", lead["phone"])
        _kv("Name", lead.get("name"))
        _kv("Status", _status_color(lead.get("status", "")))
        _kv("Outcome", _outcome_color(lead.get("outcome")))
        _kv("Attempts", f"{lead.get('attempts', 0)}/{lead.get('max_attempts', 3)}")
        _kv("Lead Type", lead.get("lead_type"))
        _kv("Campaign ID", lead.get("campaign_id"))
        _kv("Created", _ts(lead.get("created_at")))
        _kv("Last Attempted", _ts(lead.get("last_attempted_at")))
        _kv("Next Attempt", _ts(lead.get("next_attempt_at")))
        _kv("Scheduled Callback", _ts(lead.get("scheduled_callback_at")))

        metadata = lead.get("metadata")
        if metadata and metadata != {}:
            print(f"\n  {_BOLD}Metadata:{_RESET}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    pass
            if isinstance(metadata, dict):
                for k, v in metadata.items():
                    _kv(k, v, indent=4)

        extraction = lead.get("extraction")
        if extraction and extraction != {}:
            print(f"\n  {_BOLD}Latest Extraction:{_RESET}")
            if isinstance(extraction, str):
                try:
                    extraction = json.loads(extraction)
                except json.JSONDecodeError:
                    pass
            if isinstance(extraction, dict):
                for k, v in extraction.items():
                    _kv(k, v, indent=4)

        # Call attempts
        calls = await pool.fetch(
            """SELECT session_call_id, started_at, duration_seconds, outcome,
                      extraction_error, in_progress
               FROM call_logs WHERE lead_id = $1 ORDER BY started_at DESC""",
            lead["id"],
        )
        if calls:
            print(f"\n  {_BOLD}Call Attempts ({len(calls)}):{_RESET}")
            _table(
                [dict(r) for r in calls],
                [("Session", "session_call_id", 12), ("Started", "started_at", 22),
                 ("Duration", "duration_seconds", 8), ("Outcome", "outcome", 18),
                 ("Error", "extraction_error", 25)],
            )
    finally:
        await pool.close()


async def cmd_lead_history(args):
    pool = await _get_pool()
    try:
        phone = args.phone if args.phone.startswith("+") else f"+91{args.phone.lstrip('0')}"

        rows = await pool.fetch(
            """SELECT cl.session_call_id, cl.started_at, cl.duration_seconds,
                      cl.outcome, cl.credits_charged, cl.extraction_error,
                      c.name AS campaign_name, l.name AS lead_name
               FROM call_logs cl
               LEFT JOIN leads l ON l.id = cl.lead_id
               LEFT JOIN campaigns c ON c.id = cl.campaign_id
               WHERE l.phone = $1
               ORDER BY cl.started_at DESC""",
            phone,
        )
        _header(f"Call History for {phone} — {len(rows)} calls")
        _table(
            [dict(r) for r in rows],
            [("Session", "session_call_id", 12), ("Campaign", "campaign_name", 20),
             ("Started", "started_at", 22), ("Duration", "duration_seconds", 8),
             ("Outcome", "outcome", 18), ("Credits", "credits_charged", 10)],
        )
    finally:
        await pool.close()


# ── Post-call debugging ──────────────────────────────────────────────────────


async def cmd_failed_extractions(args):
    pool = await _get_pool()
    try:
        limit = int(args.limit)
        campaign_filter = (args.campaign or "").strip()

        if campaign_filter:
            camp = await _resolve_campaign(pool, campaign_filter)
            rows = await pool.fetch(
                """SELECT cl.session_call_id, cl.started_at, cl.duration_seconds,
                          cl.outcome, cl.extraction_error, cl.extraction_model,
                          l.phone, l.name AS lead_name
                   FROM call_logs cl
                   LEFT JOIN leads l ON l.id = cl.lead_id
                   WHERE cl.campaign_id = $1
                     AND (cl.extraction_error IS NOT NULL OR cl.outcome IS NULL)
                     AND cl.in_progress = FALSE
                   ORDER BY cl.started_at DESC LIMIT $2""",
                camp["id"], limit,
            )
            title = f"Failed Extractions in '{camp['name']}'"
        else:
            rows = await pool.fetch(
                """SELECT cl.session_call_id, cl.started_at, cl.duration_seconds,
                          cl.outcome, cl.extraction_error, cl.extraction_model,
                          l.phone, l.name AS lead_name,
                          c.name AS campaign_name
                   FROM call_logs cl
                   LEFT JOIN leads l ON l.id = cl.lead_id
                   LEFT JOIN campaigns c ON c.id = cl.campaign_id
                   WHERE (cl.extraction_error IS NOT NULL OR cl.outcome IS NULL)
                     AND cl.in_progress = FALSE
                   ORDER BY cl.started_at DESC LIMIT $1""",
                limit,
            )
            title = "Failed Extractions (all campaigns)"

        _header(f"{title} — {len(rows)} found")
        cols = [("Session", "session_call_id", 12), ("Phone", "phone", 15),
                ("Duration", "duration_seconds", 8), ("Outcome", "outcome", 18),
                ("Model", "extraction_model", 25), ("Error", "extraction_error", 30)]
        if not campaign_filter:
            cols.insert(1, ("Campaign", "campaign_name", 20))
        _table([dict(r) for r in rows], cols)
    finally:
        await pool.close()


async def cmd_stuck_calls(args):
    pool = await _get_pool()
    try:
        from db.postgres import live_call_grace_minutes
        grace = live_call_grace_minutes()

        campaign_filter = (args.campaign or "").strip()
        if campaign_filter:
            camp = await _resolve_campaign(pool, campaign_filter)
            rows = await pool.fetch(
                """SELECT cl.session_call_id, cl.started_at, cl.lead_id,
                          l.phone, l.name AS lead_name,
                          EXTRACT(EPOCH FROM (NOW() - cl.started_at))/60 AS minutes_stuck
                   FROM call_logs cl
                   LEFT JOIN leads l ON l.id = cl.lead_id
                   WHERE cl.campaign_id = $1 AND cl.in_progress = TRUE
                     AND cl.started_at < NOW() - ($2 * INTERVAL '1 minute')
                   ORDER BY cl.started_at ASC""",
                camp["id"], grace,
            )
            title = f"Stuck Calls in '{camp['name']}' (>{grace} min)"
        else:
            rows = await pool.fetch(
                """SELECT cl.session_call_id, cl.started_at, cl.lead_id,
                          l.phone, l.name AS lead_name, c.name AS campaign_name,
                          EXTRACT(EPOCH FROM (NOW() - cl.started_at))/60 AS minutes_stuck
                   FROM call_logs cl
                   LEFT JOIN leads l ON l.id = cl.lead_id
                   LEFT JOIN campaigns c ON c.id = cl.campaign_id
                   WHERE cl.in_progress = TRUE
                     AND cl.started_at < NOW() - ($1 * INTERVAL '1 minute')
                   ORDER BY cl.started_at ASC""",
                grace,
            )
            title = f"Stuck Calls (all campaigns, >{grace} min)"

        _header(f"{title} — {len(rows)} found")
        if not rows:
            print(f"  {_GREEN}No stuck calls found ✓{_RESET}")
        else:
            for r in rows:
                r_dict = dict(r)
                mins = r_dict.get("minutes_stuck")
                mins_str = f"{float(mins):.1f} min" if mins else "?"
                print(
                    f"  {_RED}●{_RESET} {r_dict.get('session_call_id', '?')[:12]}  "
                    f"{r_dict.get('phone', '?')}  {r_dict.get('lead_name', '?')}  "
                    f"stuck {_c(mins_str, _RED)}  "
                    f"started {_ts(r_dict.get('started_at'))}"
                )
    finally:
        await pool.close()


async def cmd_rerun_extraction(args):
    pool = await _get_pool()
    try:
        row = await pool.fetchrow(
            "SELECT * FROM call_logs WHERE session_call_id = $1",
            args.session_call_id,
        )
        if row is None:
            print(f"{_RED}Call not found: {args.session_call_id}{_RESET}", file=sys.stderr)
            sys.exit(1)
        call = dict(row)

        transcript = call.get("transcript")
        if not transcript:
            print(f"{_RED}No transcript stored for this call — cannot re-extract{_RESET}", file=sys.stderr)
            sys.exit(1)

        if isinstance(transcript, str):
            try:
                transcript = json.loads(transcript)
            except json.JSONDecodeError:
                print(f"{_RED}Transcript is not valid JSON{_RESET}", file=sys.stderr)
                sys.exit(1)

        if not isinstance(transcript, list) or not transcript:
            print(f"{_RED}Transcript is empty{_RESET}", file=sys.stderr)
            sys.exit(1)

        # Resolve extraction schema from bot config
        bot_config_id = call.get("bot_config_id")
        campaign_id = call.get("campaign_id")
        extraction_schema = None

        if campaign_id:
            camp_row = await pool.fetchrow(
                "SELECT extraction_schema_override FROM campaigns WHERE id = $1", campaign_id,
            )
            if camp_row and camp_row["extraction_schema_override"]:
                extraction_schema = camp_row["extraction_schema_override"]
                if isinstance(extraction_schema, str):
                    extraction_schema = json.loads(extraction_schema)

        if extraction_schema is None and bot_config_id:
            bot = await pool.fetchrow(
                "SELECT route, script_id FROM bot_configs WHERE id = $1", bot_config_id,
            )
            if bot:
                route = bot["route"]
                script_id = bot["script_id"]
                module_path = f"{'sts_scripts' if route == 'sts' else 'cascade_scripts'}.{script_id}"
                try:
                    import importlib
                    mod = importlib.import_module(module_path)
                    extraction_schema = getattr(mod, "EXTRACTION_SCHEMA", None)
                except Exception as exc:
                    print(f"{_YELLOW}Could not load script module {module_path}: {exc}{_RESET}")

        if extraction_schema is None:
            print(f"{_RED}No extraction schema found — cannot determine what to extract{_RESET}", file=sys.stderr)
            sys.exit(1)

        groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not groq_key:
            print(f"{_RED}GROQ_API_KEY not set in .env{_RESET}", file=sys.stderr)
            sys.exit(1)

        print(f"  {_BOLD}Re-running extraction on {len(transcript)} turns…{_RESET}")

        from post_call_extract import extract_post_call, normalize_post_call_extraction

        parsed, err, model_used = await extract_post_call(
            transcript, extraction_schema=extraction_schema,
        )

        if parsed is not None and err is None:
            extraction = normalize_post_call_extraction(parsed)
            ext_json = json.dumps(extraction, ensure_ascii=False)
            outcome = extraction.get("intent_status", "Unknown")

            await pool.execute(
                """UPDATE call_logs SET
                       extraction_json = $1::jsonb,
                       extraction_error = NULL,
                       extraction_model = $2,
                       outcome = $3,
                       qualified = $4
                   WHERE session_call_id = $5""",
                ext_json, model_used, outcome, outcome == "Interested",
                args.session_call_id,
            )

            # Also update lead if exists
            lead_id = call.get("lead_id")
            client_id = call.get("client_id")
            if lead_id and client_id:
                await pool.execute(
                    """UPDATE leads SET
                           outcome = $1,
                           extraction = $2::jsonb
                       WHERE id = $3 AND client_id = $4""",
                    outcome, ext_json, lead_id, client_id,
                )
                print(f"  {_GREEN}✓ Lead updated with new extraction{_RESET}")

            print(f"\n  {_GREEN}✓ Extraction succeeded!{_RESET}")
            _kv("Model", model_used)
            _kv("Outcome", _outcome_color(outcome))
            print(f"\n  {_BOLD}Extracted Fields:{_RESET}")
            for k, v in extraction.items():
                _kv(k, v, indent=4)
        else:
            await pool.execute(
                """UPDATE call_logs SET
                       extraction_error = $1,
                       extraction_model = $2
                   WHERE session_call_id = $3""",
                err, model_used, args.session_call_id,
            )
            print(f"\n  {_RED}✗ Extraction failed: {err}{_RESET}")
            _kv("Model", model_used)
    finally:
        await pool.close()


# ── Operator actions ──────────────────────────────────────────────────────────


async def cmd_reset_lead(args):
    pool = await _get_pool()
    try:
        campaign_id = None
        campaign_filter = (args.campaign or "").strip()
        if campaign_filter:
            camp = await _resolve_campaign(pool, campaign_filter)
            campaign_id = camp["id"]

        lead = await _resolve_lead(pool, args.id_or_phone, campaign_id=campaign_id)

        old_status = lead["status"]
        lead_id = lead["id"]
        client_id = lead["client_id"]
        camp_id = lead["campaign_id"]

        if old_status == "pending" and lead.get("attempts", 0) == 0:
            print(f"{_YELLOW}Lead is already pending with 0 attempts — nothing to reset{_RESET}")
            return

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """UPDATE leads SET
                           status = 'pending',
                           outcome = NULL,
                           attempts = 0,
                           next_attempt_at = NOW(),
                           last_attempted_at = NULL,
                           scheduled_callback_at = NULL,
                           extraction = '{}'::jsonb
                       WHERE id = $1 AND client_id = $2""",
                    lead_id, client_id,
                )
                # Fix campaign counters
                from db.postgres import reconcile_campaign_counters
                counts = await reconcile_campaign_counters(conn, camp_id, client_id)

        print(f"  {_GREEN}✓ Lead reset: {old_status} → pending (attempts: {lead.get('attempts', 0)} → 0){_RESET}")
        _kv("Lead", f"{lead.get('name')} ({lead['phone']})")
        _kv("Campaign Counters", _json_compact(counts))
    finally:
        await pool.close()


async def cmd_force_outcome(args):
    pool = await _get_pool()
    try:
        valid_outcomes = {"Interested", "Not_Interested", "Busy", "Callback_Requested",
                          "Wrong_Requirement", "Unknown", "dnc"}
        if args.outcome not in valid_outcomes:
            print(f"{_RED}Invalid outcome: {args.outcome}{_RESET}", file=sys.stderr)
            print(f"  Valid: {', '.join(sorted(valid_outcomes))}", file=sys.stderr)
            sys.exit(1)

        row = await pool.fetchrow(
            "SELECT * FROM call_logs WHERE session_call_id = $1",
            args.session_call_id,
        )
        if row is None:
            print(f"{_RED}Call not found: {args.session_call_id}{_RESET}", file=sys.stderr)
            sys.exit(1)
        call = dict(row)
        old_outcome = call.get("outcome")

        await pool.execute(
            """UPDATE call_logs SET
                   outcome = $1,
                   qualified = $2
               WHERE session_call_id = $3""",
            args.outcome, args.outcome == "Interested", args.session_call_id,
        )

        # Update lead too
        lead_id = call.get("lead_id")
        client_id = call.get("client_id")
        if lead_id and client_id:
            await pool.execute(
                "UPDATE leads SET outcome = $1 WHERE id = $2 AND client_id = $3",
                args.outcome, lead_id, client_id,
            )

        print(f"  {_GREEN}✓ Outcome updated: {_outcome_color(old_outcome)} → {_outcome_color(args.outcome)}{_RESET}")
        _kv("Call", args.session_call_id)
        if lead_id:
            _kv("Lead updated", True)
    finally:
        await pool.close()


async def cmd_settle_campaign(args):
    pool = await _get_pool()
    try:
        camp = await _resolve_campaign(pool, args.name_or_id)
        camp_id = camp["id"]
        client_id = camp["client_id"]

        if camp.get("budget_returned_at"):
            print(f"{_YELLOW}Campaign already settled at {_ts(camp['budget_returned_at'])}{_RESET}")
            return

        from db.postgres import try_settle_campaign_budget

        async with pool.acquire() as conn:
            async with conn.transaction():
                returned, just_completed = await try_settle_campaign_budget(
                    camp_id, client_id, final_status="completed", conn=conn,
                )

        if returned > 0:
            print(f"  {_GREEN}✓ Campaign settled — {_credits(returned)} returned to client balance{_RESET}")
        else:
            print(f"  {_YELLOW}Settlement returned ₹0 (budget fully consumed or leads still active){_RESET}")

        if just_completed:
            from n8n_webhook import fire_campaign_completed_webhook
            await fire_campaign_completed_webhook(pool, client_id, camp)
            print(f"  {_DIM}campaign_completed webhook triggered.{_RESET}")

        _kv("Campaign", camp["name"])
        _kv("Budget", _credits(camp.get("budget_credits")))
        _kv("Used", _credits(camp.get("budget_used_credits")))
        _kv("Returned", _credits(returned))
    finally:
        await pool.close()


async def cmd_register_webhook(args):
    pool = await _get_pool()
    try:
        client = await _resolve_client(pool, args.name_or_id)
        cid = client["id"]
        from db import postgres as pg_db
        await pg_db.upsert_webhook_config(pool, cid, args.event, args.url, args.secret)
        print(f"{_GREEN}Webhook for '{args.event}' registered successfully.{_RESET}")
    finally:
        await pool.close()


# ── Argument parser ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Aakashvani operator CLI — database inspection & management",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # -- Client commands
    p = sub.add_parser("show-client", help="Show client details by name or UUID")
    p.add_argument("name_or_id", help="Client name (fuzzy) or UUID")

    p = sub.add_parser("client-bots", help="List bot configs for a client")
    p.add_argument("name_or_id", help="Client name (fuzzy) or UUID")

    p = sub.add_parser("client-campaigns", help="List campaigns for a client")
    p.add_argument("name_or_id", help="Client name (fuzzy) or UUID")

    p = sub.add_parser("client-webhooks", help="List n8n webhooks for a client")
    p.add_argument("name_or_id", help="Client name (fuzzy) or UUID")

    # -- Campaign commands
    p = sub.add_parser("show-campaign", help="Show full campaign details")
    p.add_argument("name_or_id", help="Campaign name (fuzzy) or UUID")

    p = sub.add_parser("campaign-leads", help="List leads in a campaign")
    p.add_argument("name_or_id", help="Campaign name (fuzzy) or UUID")
    p.add_argument("--status", default="", help="Filter by lead status")
    p.add_argument("--limit", default="20", help="Max rows to show (default: 20)")

    p = sub.add_parser("campaign-calls", help="Recent call logs for a campaign")
    p.add_argument("name_or_id", help="Campaign name (fuzzy) or UUID")
    p.add_argument("--limit", default="10", help="Max rows to show (default: 10)")

    # -- Call / Lead commands
    p = sub.add_parser("show-call", help="Full call detail by session_call_id")
    p.add_argument("session_call_id", help="Session call ID")
    p.add_argument("--full", action="store_true", help="Show full transcript")

    p = sub.add_parser("show-lead", help="Show lead detail by UUID or phone")
    p.add_argument("id_or_phone", help="Lead UUID or phone number")

    p = sub.add_parser("lead-history", help="All calls for a phone across campaigns")
    p.add_argument("phone", help="Phone number (E.164 or 10-digit)")

    # -- Post-call debugging
    p = sub.add_parser("failed-extractions", help="List calls with failed extraction")
    p.add_argument("--campaign", default="", help="Filter by campaign name/UUID")
    p.add_argument("--limit", default="20", help="Max rows (default: 20)")

    p = sub.add_parser("stuck-calls", help="Show calls stuck in_progress beyond grace")
    p.add_argument("--campaign", default="", help="Filter by campaign name/UUID")

    p = sub.add_parser("rerun-extraction", help="Re-run Groq extraction on a call")
    p.add_argument("session_call_id", help="Session call ID")

    # -- Operator actions
    p = sub.add_parser("reset-lead", help="Reset lead to pending with 0 attempts")
    p.add_argument("id_or_phone", help="Lead UUID or phone number")
    p.add_argument("--campaign", default="", help="Campaign name/UUID (for phone disambiguation)")

    p = sub.add_parser("force-outcome", help="Manually set outcome on a call")
    p.add_argument("session_call_id", help="Session call ID")
    p.add_argument("outcome", help="Outcome value (Interested, Not_Interested, etc)")

    p = sub.add_parser("settle-campaign", help="Force-settle campaign and return budget")
    p.add_argument("name_or_id", help="Campaign name (fuzzy) or UUID")

    p = sub.add_parser("register-webhook", help="Register an n8n webhook for a client")
    p.add_argument("name_or_id", help="Client name (fuzzy) or UUID")
    p.add_argument("event", help="Event (e.g. lead_qualified, campaign_completed)")
    p.add_argument("url", help="n8n webhook URL")
    p.add_argument("secret", help="HMAC signing secret")

    return parser


_COMMANDS = {
    "show-client": cmd_show_client,
    "client-bots": cmd_client_bots,
    "client-campaigns": cmd_client_campaigns,
    "client-webhooks": cmd_client_webhooks,
    "show-campaign": cmd_show_campaign,
    "campaign-leads": cmd_campaign_leads,
    "campaign-calls": cmd_campaign_calls,
    "show-call": cmd_show_call,
    "show-lead": cmd_show_lead,
    "lead-history": cmd_lead_history,
    "failed-extractions": cmd_failed_extractions,
    "stuck-calls": cmd_stuck_calls,
    "rerun-extraction": cmd_rerun_extraction,
    "reset-lead": cmd_reset_lead,
    "force-outcome": cmd_force_outcome,
    "settle-campaign": cmd_settle_campaign,
    "register-webhook": cmd_register_webhook,
}


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    asyncio.run(handler(args))


if __name__ == "__main__":
    main()

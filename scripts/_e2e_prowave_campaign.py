#!/usr/bin/env python3
"""Create Prowave Excel campaign, import leads, dial +917397867643."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import openpyxl
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
TARGET_PHONE = "+917397867643"
XLSX = Path(r"c:\Users\Shubh\Downloads\prowave leads.xlsx")

LEAD_SCHEMA = {
    "fields": [
        {"key": "location", "label": "Location", "type": "text", "required": False, "csv_column": "Location"},
        {"key": "language", "label": "Language", "type": "text", "required": False, "csv_column": "Language"},
        {"key": "bhk", "label": "BHK", "type": "text", "required": False, "csv_column": "BHK"},
        {
            "key": "extracted_location",
            "label": "Extracted Location",
            "type": "text",
            "required": False,
            "csv_column": "Extracted Location",
        },
        {"key": "intent", "label": "Intent", "type": "text", "required": False, "csv_column": "Intent"},
        {
            "key": "call_summary",
            "label": "Call Summary",
            "type": "text",
            "required": False,
            "csv_column": "Call Summary",
        },
    ]
}


def normalize_phone(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        raw = str(int(raw))
    s = "".join(ch for ch in str(raw) if ch.isdigit())
    if not s:
        return None
    if s.startswith("91") and len(s) >= 12:
        return f"+{s}"
    if len(s) == 10:
        return f"+91{s}"
    return f"+{s}"


def load_excel_rows(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    headers = [str(h or "").strip() for h in rows[0]]
    out = []
    for row in rows[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        d = {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}
        out.append(d)
    return out


async def main() -> int:
    from db import postgres as pg_db
    from dialer.concurrent_dialer import fire_call, _release_lead_to_pending
    from compliance import is_call_allowed
    from telephony import normalize_plivo_number
    import aiohttp

    allowed, reason = is_call_allowed()
    print("compliance:", allowed, reason)
    if not allowed:
        return 1

    from_number = normalize_plivo_number(os.environ.get("PLIVO_PHONE_NUMBER") or "")
    print("from_number:", from_number)
    if not from_number:
        print("ERROR: PLIVO_PHONE_NUMBER missing", file=sys.stderr)
        return 1

    excel_rows = load_excel_rows(XLSX)
    print(f"excel_rows: {len(excel_rows)}")

    pool = await pg_db.init_pool()
    try:
        from db import redis_client as redis_db

        await redis_db.init_redis()

        # Prefer STS bot with script_config (agent speech via Gemini + lead schema)
        bot = await pool.fetchrow(
            """
            SELECT * FROM bot_configs
            WHERE client_id = $1 AND active = TRUE
              AND script_config_id IS NOT NULL AND route = 'sts'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            CLIENT_ID,
        )
        if bot is None:
            bot = await pool.fetchrow(
                """
                SELECT * FROM bot_configs
                WHERE client_id = $1 AND active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                CLIENT_ID,
            )
        if bot is None:
            print("ERROR: no bot found", file=sys.stderr)
            return 1
        bot = pg_db.record_to_dict(bot)
        print("bot:", bot["id"], bot.get("name"), bot.get("script_id"), bot.get("script_config_id"))

        # Ensure telephony from env
        await pool.execute(
            "UPDATE bot_configs SET telephony_number = $1 WHERE id = $2",
            from_number,
            UUID(str(bot["id"])),
        )
        bot["telephony_number"] = from_number

        # Attach / update lead schema on script config if present
        script_config_id = bot.get("script_config_id")
        if script_config_id:
            await pool.execute(
                """
                UPDATE script_configs
                SET lead_schema = $1::jsonb, updated_at = NOW()
                WHERE id = $2 AND client_id = $3
                """,
                json.dumps(LEAD_SCHEMA),
                UUID(str(script_config_id)),
                CLIENT_ID,
            )
            print("updated lead_schema on", script_config_id)

        # Create campaign
        campaign_id = await pg_db.create_campaign(
            pool,
            client_id=CLIENT_ID,
            bot_config_id=UUID(str(bot["id"])),
            name="Prowave Excel E2E",
            budget_credits=200,
            max_concurrent_calls=3,
            calls_per_minute=10,
            max_attempts=3,
            retry_delay_minutes=30,
        )
        print("campaign_id:", campaign_id)

        # Build lead insert list — put TARGET first
        leads = []
        leads.append(
            {
                "client_id": CLIENT_ID,
                "campaign_id": campaign_id,
                "phone": TARGET_PHONE,
                "name": "E2E Agent Test",
                "lead_type": "warm",
                "status": "pending",
                "max_attempts": 3,
                "metadata": {
                    "location": "Pune",
                    "language": "hi",
                    "bhk": "2BHK",
                    "extracted_location": "Khadakwasla",
                    "intent": "YES",
                    "call_summary": "Excel E2E test lead",
                },
            }
        )

        seen = {TARGET_PHONE}
        for row in excel_rows:
            phone = normalize_phone(row.get("Phone Number") or row.get("Phone") or row.get("phone"))
            if not phone or phone in seen:
                continue
            seen.add(phone)
            meta = {}
            for key, header in [
                ("location", "Location"),
                ("language", "Language"),
                ("bhk", "BHK"),
                ("extracted_location", "Extracted Location"),
                ("intent", "Intent"),
                ("call_summary", "Call Summary"),
            ]:
                val = row.get(header)
                if val is not None and str(val).strip() and str(val).strip() != "-":
                    meta[key] = str(val).strip()
            leads.append(
                {
                    "client_id": CLIENT_ID,
                    "campaign_id": campaign_id,
                    "phone": phone,
                    "name": str(row.get("Name") or "").strip() or None,
                    "lead_type": "cold",
                    "status": "pending",
                    "max_attempts": 3,
                    "metadata": meta,
                }
            )

        inserted = await pg_db.bulk_insert_leads(pool, leads)
        print(f"leads_inserted: {inserted} (requested {len(leads)})")
        await pg_db.reconcile_campaign_counters(pool, campaign_id, CLIENT_ID)

        campaign = await pg_db.get_campaign(pool, campaign_id, CLIENT_ID)
        # Claim target lead for immediate test dial (full pipeline without starting dialer)
        target = await pool.fetchrow(
            """
            SELECT * FROM leads
            WHERE campaign_id = $1 AND client_id = $2 AND phone = $3
            LIMIT 1
            """,
            campaign_id,
            CLIENT_ID,
            TARGET_PHONE,
        )
        if not target:
            print("ERROR: target lead missing", file=sys.stderr)
            return 1
        lead = pg_db.record_to_dict(target)
        await pool.execute(
            """
            UPDATE leads SET status = 'calling', last_attempted_at = NOW(), attempts = attempts + 1
            WHERE id = $1 AND status = 'pending'
            """,
            lead["id"],
        )
        await pg_db.increment_campaign_counters(
            pool, campaign_id, from_status="pending", to_status="calling"
        )
        lead["status"] = "calling"

        print(f"Dialing {TARGET_PHONE} from {from_number} campaign={campaign_id}")
        print("Answer the phone — agent should speak.")

        async with aiohttp.ClientSession() as session:
            try:
                session_call_id = await fire_call(
                    session,
                    lead,
                    campaign,
                    bot,
                    host="localhost:7860",
                    pool=pool,
                    client_id=CLIENT_ID,
                    campaign_id=campaign_id,
                    dial_phone=TARGET_PHONE,
                    is_test_call=True,
                )
            except Exception as exc:
                print(f"ERROR dial: {exc}", file=sys.stderr)
                await _release_lead_to_pending(pool, lead, campaign_id, CLIENT_ID)
                return 1

        if not session_call_id:
            print("ERROR: call skipped", file=sys.stderr)
            await _release_lead_to_pending(pool, lead, campaign_id, CLIENT_ID)
            return 1

        print("session_call_id:", session_call_id)
        print("campaign ready in UI; target dial placed.")
        return 0
    finally:
        try:
            from db import redis_client as redis_db

            await redis_db.close_redis()
        except Exception:
            pass
        await pg_db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

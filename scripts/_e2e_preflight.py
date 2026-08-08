#!/usr/bin/env python3
"""Preflight for E2E test call — no secrets printed."""

from __future__ import annotations

import asyncio
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    from db import postgres as pg_db
    from compliance import is_call_allowed

    print("compliance:", is_call_allowed())

    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    print("ngrok_set:", bool(ngrok))
    for path in ("/health", "/"):
        try:
            r = urllib.request.urlopen(ngrok + path, timeout=8)
            print(f"ngrok{path}:", r.status)
        except Exception as exc:
            code = getattr(exc, "code", None)
            print(f"ngrok{path}: FAIL", code or type(exc).__name__)

    try:
        r = urllib.request.urlopen("http://127.0.0.1:7860/health", timeout=5)
        print("local/health:", r.status)
    except Exception as exc:
        print("local/health: FAIL", exc)

    pool = await pg_db.create_db_pool(os.environ["DATABASE_URL"])
    try:
        cols = await pool.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'script_configs'
            ORDER BY ordinal_position
            """
        )
        print("script_configs_cols:", [c["column_name"] for c in cols])

        rows = await pool.fetch(
            """
            SELECT id, client_id, route, script_id, active
            FROM script_configs
            WHERE active = TRUE
            ORDER BY created_at DESC
            LIMIT 8
            """
        )
        print("active_script_configs:", len(rows))
        for r in rows:
            print(dict(r))

        camp = await pool.fetchrow(
            """
            SELECT id, name, status, bot_config_id, client_id
            FROM campaigns
            WHERE id = $1
            """,
            "00000000-0000-4000-8000-000000000006",
        )
        print("sandbox_campaign:", dict(camp) if camp else None)

        bots = await pool.fetch(
            """
            SELECT id, name, route, script_id, script_config_id, active, telephony_number
            FROM bot_configs
            WHERE active = TRUE
            ORDER BY created_at DESC
            LIMIT 8
            """
        )
        for b in bots:
            print("bot:", dict(b))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""CMS end-to-end test call — dial via script_configs without campaign dialer.

Usage:
    uv run python scripts/test_call.py --script-config-id <UUID> --phone +91... --route sts

Prerequisites:
    - server.py running (``just dev``)
    - NGROK_URL or public DIALER_CALLBACK_HOST for Plivo callbacks
    - DATABASE_URL, PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_PHONE_NUMBER
    - ``just db-seed`` applied (sandbox campaign + bots)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import aiohttp
from dotenv import load_dotenv

from api.script_config_validation import normalize_route

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DEV_CLIENT_ID = UUID("00000000-0000-4000-8000-000000000001")
SANDBOX_BOT_STS = UUID("00000000-0000-4000-8000-000000000004")
SANDBOX_BOT_CASCADED = UUID("00000000-0000-4000-8000-000000000005")
SANDBOX_CAMPAIGN_ID = UUID("00000000-0000-4000-8000-000000000006")

_VALID_ROUTES = frozenset({"sts", "cascaded"})


def synthetic_lead_phone() -> str:
    """Unique placeholder phone for sandbox lead rows (real dial uses --phone)."""
    return f"+cli{uuid4().hex[:12]}"


def sandbox_bot_id_for_route(route: str) -> UUID:
    if route == "sts":
        return SANDBOX_BOT_STS
    if route == "cascaded":
        return SANDBOX_BOT_CASCADED
    raise ValueError(f"Invalid route: {route!r}")


def _warn_localhost_callbacks(host: str) -> None:
    ngrok = (os.getenv("NGROK_URL") or "").strip()
    if ngrok:
        return
    if host.startswith(("localhost", "127.0.0.1")) or not host:
        print(
            "WARNING: NGROK_URL is not set — Plivo cannot reach localhost callbacks.",
            file=sys.stderr,
        )


async def _get_pool():
    from db import postgres as pg_db

    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        print("ERROR: DATABASE_URL is not set in .env", file=sys.stderr)
        sys.exit(1)
    return await pg_db.create_db_pool(dsn)


async def _resolve_bot_config(
    pool,
    *,
    client_id: UUID,
    script_config_id: UUID,
    route: str,
) -> dict:
    from db import postgres as pg_db

    row = await pool.fetchrow(
        """
        SELECT * FROM bot_configs
        WHERE client_id = $1 AND script_config_id = $2 AND active = TRUE
        LIMIT 1
        """,
        client_id,
        script_config_id,
    )
    if row is not None:
        bot = pg_db.record_to_dict(row)
        if bot.get("route") != route:
            raise ValueError(
                f"Linked bot route {bot.get('route')!r} != --route {route!r}"
            )
        return bot

    sandbox_bot_id = sandbox_bot_id_for_route(route)
    await pool.execute(
        """
        UPDATE bot_configs
        SET script_config_id = $1
        WHERE id = $2 AND client_id = $3
        """,
        script_config_id,
        sandbox_bot_id,
        client_id,
    )
    bot = await pg_db.get_bot_config(pool, sandbox_bot_id, client_id)
    if bot is None:
        raise RuntimeError(
            f"Sandbox bot {sandbox_bot_id} not found — run ``just db-seed``"
        )
    return bot


async def _ensure_campaign_bot(
    pool,
    *,
    campaign_id: UUID,
    client_id: UUID,
    bot_config_id: UUID,
) -> dict:
    from db import postgres as pg_db

    campaign = await pg_db.get_campaign(pool, campaign_id, client_id)
    if campaign is None:
        raise RuntimeError(f"Campaign {campaign_id} not found — run ``just db-seed``")

    if str(campaign.get("bot_config_id")) != str(bot_config_id):
        await pool.execute(
            """
            UPDATE campaigns
            SET bot_config_id = $1
            WHERE id = $2 AND client_id = $3
            """,
            bot_config_id,
            campaign_id,
            client_id,
        )
        campaign = await pg_db.get_campaign(pool, campaign_id, client_id)
    return campaign or {}


async def _claim_throwaway_lead(
    pool,
    *,
    client_id: UUID,
    campaign_id: UUID,
    dial_phone: str,
    lead_name: str,
    city: str,
) -> dict:
    from db import postgres as pg_db

    lead = await pg_db.insert_single_lead(
        pool,
        {
            "client_id": client_id,
            "campaign_id": campaign_id,
            "phone": synthetic_lead_phone(),
            "name": lead_name,
            "metadata": {"city": city, "real_phone": dial_phone},
            "status": "pending",
        },
    )
    lead_id = UUID(str(lead["id"]))
    await pool.execute(
        """
        UPDATE leads
        SET status = 'calling', last_attempted_at = NOW()
        WHERE id = $1 AND client_id = $2 AND status = 'pending'
        """,
        lead_id,
        client_id,
    )
    await pg_db.increment_campaign_counters(
        pool, campaign_id, from_status="pending", to_status="calling"
    )
    lead["status"] = "calling"
    return lead


def _call_log_finalized(row: dict | None) -> bool:
    """True when hangup + post-call have written duration/outcome (not just in_progress cleared)."""
    if not row or row.get("in_progress"):
        return False
    if row.get("duration_seconds") is not None and row.get("ended_at"):
        return True
    if row.get("outcome"):
        return True
    return False


async def _poll_call_log(pool, session_call_id: str, *, timeout_s: int) -> dict | None:
    from db import postgres as pg_db

    elapsed = 0
    interval = 2
    while elapsed <= timeout_s:
        row = await pg_db.get_call_log_by_session(pool, session_call_id)
        if _call_log_finalized(row):
            return row
        await asyncio.sleep(interval)
        elapsed += interval
    return await pg_db.get_call_log_by_session(pool, session_call_id)


def _print_summary(
    *,
    session_call_id: str,
    call_log: dict | None,
) -> None:
    from script_runtime import parse_post_call_snapshot

    print(f"\nSession call ID: {session_call_id}")
    if call_log is None:
        print("No call_log row found.")
        return

    print(f"In progress: {call_log.get('in_progress')}")
    print(f"Duration (s): {call_log.get('duration_seconds')}")
    print(f"Outcome: {call_log.get('outcome')}")
    transcript = call_log.get("transcript") or []
    if isinstance(transcript, str):
        try:
            transcript = json.loads(transcript)
        except json.JSONDecodeError:
            transcript = []
    print(f"Transcript turns: {len(transcript)}")
    print(f"Recording: {'yes' if call_log.get('recording_url') else 'no'}")

    extraction = call_log.get("extraction_json")
    if isinstance(extraction, str):
        try:
            extraction = json.loads(extraction)
        except json.JSONDecodeError:
            pass
    if extraction:
        print(f"Extraction: {json.dumps(extraction, ensure_ascii=False, indent=2)}")

    snap = parse_post_call_snapshot(call_log.get("call_data"))
    print(f"Post-call snapshot present: {snap is not None}")
    if snap:
        print(f"  script_config_id: {snap.get('script_config_id')}")
        print(f"  version: {snap.get('version')}")

    ext_err = call_log.get("extraction_error")
    if ext_err:
        print(f"Extraction error: {ext_err}")


async def run_test_call(args: argparse.Namespace) -> int:
    from db import postgres as pg_db
    from dialer.concurrent_dialer import _release_lead_to_pending, fire_call

    args.route = normalize_route(args.route)
    if args.route not in _VALID_ROUTES:
        print(f"ERROR: --route must be one of {sorted(_VALID_ROUTES)}", file=sys.stderr)
        return 1

    for key in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN"):
        if not (os.getenv(key) or "").strip():
            print(f"ERROR: {key} is not set", file=sys.stderr)
            return 1
    if not (os.getenv("PLIVO_PHONE_NUMBER") or "").strip():
        print("ERROR: PLIVO_PHONE_NUMBER is not set", file=sys.stderr)
        return 1

    _warn_localhost_callbacks(args.host)

    client_id = UUID(args.client_id)
    campaign_id = UUID(args.campaign_id)
    script_config_id = UUID(args.script_config_id)

    pool = await _get_pool()
    try:
        from db import redis_client as redis_db

        await redis_db.init_redis()
        script_config = await pg_db.get_script_config(
            pool, script_config_id, client_id
        )
        if script_config is None:
            print(
                f"ERROR: script_config {script_config_id} not found or inactive",
                file=sys.stderr,
            )
            return 1
        if script_config.get("route") != args.route:
            print(
                f"ERROR: script_config route {script_config.get('route')!r} "
                f"!= --route {args.route!r}",
                file=sys.stderr,
            )
            return 1

        bot_config = await _resolve_bot_config(
            pool,
            client_id=client_id,
            script_config_id=script_config_id,
            route=args.route,
        )
        campaign = await _ensure_campaign_bot(
            pool,
            campaign_id=campaign_id,
            client_id=client_id,
            bot_config_id=UUID(str(bot_config["id"])),
        )

        lead = await _claim_throwaway_lead(
            pool,
            client_id=client_id,
            campaign_id=campaign_id,
            dial_phone=args.phone,
            lead_name=args.lead_name,
            city=args.city,
        )
        lead_id = UUID(str(lead["id"]))

        print(
            f"Dialing {args.phone} via script_config {script_config_id} "
            f"(route={args.route}, lead={lead_id})"
        )

        session_call_id: str | None = None
        try:
            async with aiohttp.ClientSession() as session:
                session_call_id = await fire_call(
                    session,
                    lead,
                    campaign,
                    bot_config,
                    host=args.host,
                    pool=pool,
                    client_id=client_id,
                    campaign_id=campaign_id,
                    dial_phone=args.phone,
                )
        except Exception as exc:
            print(f"ERROR: dial failed: {exc}", file=sys.stderr)
            await _release_lead_to_pending(
                pool, lead, campaign_id, client_id
            )
            return 1

        if not session_call_id:
            print("ERROR: call was skipped (duplicate guard?)", file=sys.stderr)
            await _release_lead_to_pending(
                pool, lead, campaign_id, client_id
            )
            return 1

        print(f"Plivo dial placed. Polling up to {args.poll_seconds}s…")
        call_log = await _poll_call_log(
            pool, session_call_id, timeout_s=args.poll_seconds
        )
        _print_summary(
            session_call_id=session_call_id,
            call_log=call_log,
        )

        if call_log and _call_log_finalized(call_log):
            return 0
        print("Call still in progress or not finalized (timeout).", file=sys.stderr)
        return 2
    finally:
        await pool.close()
        try:
            from db import redis_client as redis_db

            await redis_db.close_redis()
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fire a CMS test call through the full prefetch + post-call pipeline.",
    )
    parser.add_argument(
        "--script-config-id",
        required=True,
        help="UUID of script_configs row to test",
    )
    parser.add_argument("--phone", required=True, help="E.164 number to dial")
    parser.add_argument(
        "--route",
        required=True,
        help="Bot route (sts or cascaded; legacy alias cascade)",
    )
    parser.add_argument(
        "--client-id",
        default=str(DEV_CLIENT_ID),
        help="Client UUID (default: dev tenant)",
    )
    parser.add_argument(
        "--campaign-id",
        default=str(SANDBOX_CAMPAIGN_ID),
        help="Sandbox campaign UUID",
    )
    parser.add_argument("--lead-name", default="Test Lead")
    parser.add_argument("--city", default="")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--host", default="localhost:7860")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_test_call(args)))


if __name__ == "__main__":
    main()

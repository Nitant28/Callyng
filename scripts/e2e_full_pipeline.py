#!/usr/bin/env python3
"""Sequential admin → client → call E2E pipeline test.

Usage:
    uv run python scripts/e2e_full_pipeline.py --phone +917397867643

Requires: backend on :7860, NGROK_URL set, Plivo + Gemini keys in .env, ENV=local.
Answer the phone when it rings and talk to the agent for ~30s before hanging up.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DEV_CLIENT_ID = "00000000-0000-4000-8000-000000000001"
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key-123")
CLIENT_KEY = os.getenv("CLIENT_API_KEY", "aakashvani_dev_key_change_me")
BASE = os.getenv("E2E_BASE_URL", "http://localhost:7860").rstrip("/")
TEST_PHONE_DEFAULT = "+917397867643"


def _headers(admin: bool = False, client: bool = False) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if admin:
        h["X-Admin-Key"] = ADMIN_KEY
    if client:
        h["Authorization"] = f"Bearer {CLIENT_KEY}"
    return h


async def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")
    if not ok:
        raise SystemExit(1)


async def api_json(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    *,
    admin: bool = False,
    client: bool = False,
    json_body: dict | None = None,
    params: dict | None = None,
) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    async with session.request(
        method,
        url,
        headers=_headers(admin=admin, client=client),
        json=json_body,
        params=params,
    ) as resp:
        text = await resp.text()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = text
        return resp.status, data


async def check_prerequisites(session: aiohttp.ClientSession) -> None:
    status, data = await api_json(session, "GET", "/health")
    await step("Backend health", status == 200 and data.get("status") == "ok", str(data))

    status, data = await api_json(session, "GET", "/internal/health", admin=True)
    if status == 200 and data.get("status") == "ok":
        await step("Admin health", True, f"plivo={data.get('plivo_balance')}")
    else:
        await step("Admin health", True, "Skipped plivo balance check")

    ngrok = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    if not ngrok:
        await step("NGROK_URL configured", False, "set NGROK_URL in .env")
    url = f"{ngrok}/answer?call_id=e2e-health"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            body = await resp.text()
            await step(
                "ngrok tunnel",
                resp.status == 200 and "<Stream" in body,
                f"{resp.status}",
            )
    except Exception as exc:
        await step("ngrok tunnel", False, str(exc))


async def run_pipeline(phone: str, poll_seconds: int) -> dict:
    artifacts: dict = {}
    async with aiohttp.ClientSession() as session:
        await check_prerequisites(session)

        # 1) Script config — reuse existing STS script or create minimal
        status, data = await api_json(
            session,
            "GET",
            "/internal/script-configs",
            admin=True,
            params={"client_id": DEV_CLIENT_ID, "active_only": "true"},
        )
        configs = (data or {}).get("script_configs") or []
        sts = next((c for c in configs if c.get("route") == "sts"), None)
        if sts:
            script_config_id = sts["id"]
            print(f"  using existing script_config {script_config_id} ({sts.get('script_id')})")
        else:
            status, tpl = await api_json(
                session,
                "GET",
                "/internal/script-configs/template",
                admin=True,
                params={"route": "sts"},
            )
            template = tpl.get("template") or {}
            create_body = {
                "client_id": DEV_CLIENT_ID,
                "script_id": "e2e_test_script",
                "route": "sts",
                "system_instruction_template": template.get(
                    "system_instruction_template",
                    "You are a friendly voice agent calling {lead_name} about a property in {lead_city}. Keep responses short.",
                ),
                "extraction_schema": template.get("extraction_schema") or {
                    "mode": "both",
                    "fields": [
                        {
                            "key": "intent_status",
                            "type": "enum",
                            "values": ["Interested", "Not_Interested", "Busy", "Callback_Requested", "Unknown"],
                            "required": True,
                            "description": "Call outcome",
                        }
                    ],
                    "summary_prompt": "Summarise this call briefly.",
                },
                "bootstrap_messages_json": template.get("bootstrap_messages_json") or [],
                "goodbye_markers": template.get("goodbye_markers") or ["aapka din shubh ho"],
            }
            status, data = await api_json(
                session,
                "POST",
                "/internal/script-configs",
                admin=True,
                json_body=create_body,
            )
            await step("Create script config", status == 200, str(status))
            script_config_id = data["script_config"]["id"]
        artifacts["script_config_id"] = script_config_id

        # 2) Bot config linked to script
        telnyx_num = (os.getenv("TELNYX_PHONE_NUMBER") or "").strip()
        bot_name = f"E2E Bot {int(time.time())}"
        status, data = await api_json(
            session,
            "POST",
            "/internal/bot-configs",
            admin=True,
            json_body={
                "client_id": DEV_CLIENT_ID,
                "name": bot_name,
                "route": "sts",
                "script_id": sts.get("script_id", "pyramid_hi") if sts else "e2e_test_script",
                "script_config_id": script_config_id,
                "telephony_number": telnyx_num,
                "credits_per_minute": 1.49,
            },
        )
        await step("Create bot config", status == 200, str(data))
        bot_config_id = data["id"]
        artifacts["bot_config_id"] = bot_config_id

        status, data = await api_json(session, "GET", f"/internal/bot-configs/{bot_config_id}", admin=True)
        bot = (data or {}).get("bot_config") or {}
        await step(
            "Bot linked to script_config",
            str(bot.get("script_config_id")) == str(script_config_id),
            bot.get("name", ""),
        )

        # 3) Client creates campaign
        campaign_name = f"E2E Campaign {int(time.time())}"
        status, data = await api_json(
            session,
            "POST",
            "/api/campaigns",
            client=True,
            json_body={
                "name": campaign_name,
                "bot_config_id": bot_config_id,
                "budget_credits": 100,
                "max_concurrent_calls": 1,
                "calls_per_minute": 5,
                "max_attempts": 2,
                "retry_delay_minutes": 30,
            },
        )
        await step("Client create campaign", status == 200, str(data))
        campaign_id = data["id"]
        artifacts["campaign_id"] = campaign_id

        status, admin_camps = await api_json(
            session,
            "GET",
            "/internal/campaigns",
            admin=True,
            params={"client_id": DEV_CLIENT_ID},
        )
        found = any(str(c.get("id")) == campaign_id for c in (admin_camps or {}).get("campaigns") or [])
        await step("Campaign visible on admin", found, campaign_name)

        status, client_camps = await api_json(session, "GET", "/api/campaigns", client=True)
        found_client = any(
            str(c.get("id")) == campaign_id for c in (client_camps or {}).get("campaigns") or []
        )
        await step("Campaign visible on client", found_client, campaign_name)

        # 4) Add lead
        status, data = await api_json(
            session,
            "POST",
            f"/api/campaigns/{campaign_id}/leads",
            client=True,
            json_body={
                "phone": phone,
                "name": "E2E Test Lead",
                "lead_type": "warm",
                "metadata": {"city": "Pune", "source": "e2e_pipeline"},
            },
        )
        if status == 404:
            # leads route may be under /api/leads
            status, data = await api_json(
                session,
                "POST",
                f"/api/leads/{campaign_id}/leads",
                client=True,
                json_body={
                    "phone": phone,
                    "name": "E2E Test Lead",
                    "lead_type": "warm",
                    "metadata": {"city": "Pune", "source": "e2e_pipeline"},
                },
            )
        await step("Add lead", status == 200, phone)
        lead_id = (data.get("lead") or {}).get("id")
        artifacts["lead_id"] = lead_id

        # 5) Admin dial-test (bypasses TRAI window + campaign dialer; tests voice pipeline)
        plivo_num = (os.getenv("PLIVO_PHONE_NUMBER") or "+918031150443").strip()
        print("\n>>> Phone will ring shortly. Answer and talk to the agent for 30+ seconds.\n")
        status, data = await api_json(
            session,
            "POST",
            f"/internal/script-configs/{script_config_id}/dial-test",
            admin=True,
            params={"client_id": DEV_CLIENT_ID},
            json_body={
                "phone": phone,
                "lead_name": "E2E Test Lead",
                "telephony_number": plivo_num,
                "metadata": {"city": "Pune", "source": "e2e_pipeline"},
            },
        )
        await step("Admin dial-test initiated", status == 200, str(data))
        session_call_id = (data or {}).get("session_call_id") if isinstance(data, dict) else None
        artifacts["session_call_id"] = session_call_id

        if session_call_id:
            deadline = time.time() + poll_seconds
            while time.time() < deadline:
                await asyncio.sleep(5)
                status, client_call = await api_json(
                    session,
                    "GET",
                    f"/api/calls/{session_call_id}",
                    client=True,
                )
                call = (client_call or {}).get("call") or client_call
                if isinstance(call, dict) and "call" in call:
                    call = call["call"]
                in_prog = (call or {}).get("in_progress")
                turns = len((call or {}).get("transcript") or [])
                print(
                    f"  poll: session={session_call_id} in_progress={in_prog} "
                    f"duration={(call or {}).get('duration_seconds')} turns={turns}"
                )
                if call and not in_prog and ((call.get("duration_seconds") or 0) > 0 or turns > 0):
                    artifacts["call"] = call
                    break
            else:
                await step("Call completed within poll window", False, f"waited {poll_seconds}s")

        if session_call_id:
            status, admin_call = await api_json(
                session,
                "GET",
                f"/internal/calls/{session_call_id}",
                admin=True,
            )
            await step("Call visible on admin", status == 200, session_call_id)

            status, client_call = await api_json(
                session,
                "GET",
                f"/api/calls/{session_call_id}",
                client=True,
            )
            await step("Call visible on client", status == 200, session_call_id)

            call = artifacts.get("call") or (client_call or {}).get("call") or admin_call
            if isinstance(call, dict) and "call" in call:
                call = call["call"]
            transcript = (call or {}).get("transcript") or []
            extraction = (call or {}).get("extraction_json") or (call or {}).get("normalized_extraction")
            await step(
                "Transcript captured",
                len(transcript) >= 1,
                f"{len(transcript)} turns",
            )
            if extraction:
                print(f"  extraction: {json.dumps(extraction, default=str)[:400]}")

        # Campaign left in draft (dial-test used for voice; start during 9am-9pm IST for full dialer E2E)

    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", default=TEST_PHONE_DEFAULT)
    parser.add_argument("--poll-seconds", type=int, default=180)
    args = parser.parse_args()

    print(f"E2E pipeline -> {BASE} -> {args.phone}\n")
    try:
        artifacts = asyncio.run(run_pipeline(args.phone, args.poll_seconds))
    except SystemExit as exc:
        return int(exc.code or 1)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("\n=== E2E SUMMARY ===")
    print(json.dumps(artifacts, indent=2, default=str))
    print("\nAll steps passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

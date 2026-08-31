#!/usr/bin/env python3
"""One-shot test POST to the deployed Mega_Workflow webhook.

Does NOT modify n8n. Does NOT use real customer production call data.
Does NOT print secrets.

Usage (from repo root):
  uv run python scripts/test_n8n_followup_webhook.py
  uv run python scripts/test_n8n_followup_webhook.py --dry-run
  uv run python scripts/test_n8n_followup_webhook.py --url https://n8n.bhuvisx.com/webhook/...

Env (optional):
  N8N_LEAD_WEBHOOK_URL / N8N_FOLLOWUP_WEBHOOK_URL  — override target URL
  N8N_WEBHOOK_SECRET                               — sent as X-Aakashvani-Webhook-Secret if set
  N8N_TIMEOUT_SECONDS                              — default 15
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

# Allow running as `python scripts/...` without installing the package.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

import urllib.error
import urllib.request

from integrations.n8n.payload import build_lead_qualified_payload

DEFAULT_WEBHOOK = (
    "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)


def build_sample_payload() -> dict:
    """Mega_Workflow Lead Context–compatible payload (dummy data only)."""
    fixture = _ROOT / "test-webhook.json"
    if fixture.is_file():
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        lead = payload.get("lead") or {}
        call = payload.get("call") or {}
        event_id = payload.get("event_id")
        if not event_id and call.get("session_call_id") and lead.get("id"):
            payload["event_id"] = f"{call['session_call_id']}:{lead['id']}"
        if "aakashvani" not in payload or not isinstance(payload.get("aakashvani"), dict):
            payload["aakashvani"] = {}
        if not payload["aakashvani"].get("record_url"):
            from integrations.n8n.payload import _record_url

            payload["aakashvani"]["record_url"] = _record_url()
        payload["metadata"] = {**(payload.get("metadata") or {}), "test": True}
        return payload

    client_id = uuid4()
    lead_id = uuid4()
    campaign_id = uuid4()
    bot_id = uuid4()
    session_call_id = f"test_{uuid4().hex[:12]}"

    payload = build_lead_qualified_payload(
        client_id=client_id,
        lead={
            "id": lead_id,
            "name": "Test Customer",
            "phone": "+919359210080",
            "email": "getin2grave@gmail.com",
            "lead_type": "warm",
            "metadata": {
                "email": "getin2grave@gmail.com",
                "lead_city": "Pune",
                "source": "n8n_followup_manual_test",
            },
        },
        session_call_id=session_call_id,
        duration_seconds=95,
        extraction={
            "intent_status": "Interested",
            "summary": (
                "Connectivity test — customer interested in a 2 BHK in Pune. "
                "Not a real call."
            ),
            "bhk_preference": "2 BHK",
            "location_preference": "Pune",
            "budget": "8000000",
            "callback_time": None,
        },
        campaign={"id": campaign_id, "name": "n8n Manual Test Campaign"},
        outcome="Interested",
        bot_config_id=bot_id,
        billed_minutes=2,
        credits_charged=0,
        route="sts",
        recording_url=None,
        client={
            "name": "Test Client",
            "industry": "real_estate",
        },
    )
    # Mark clearly as a test so Mega Executions are easy to spot.
    payload["metadata"] = {**(payload.get("metadata") or {}), "test": True}
    return payload


def post_json(url: str, payload: dict, *, secret: str | None, timeout: int) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "aakashvani-n8n-followup-test/1.0",
    }
    if secret:
        headers["X-Aakashvani-Webhook-Secret"] = secret

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), raw
    except urllib.error.URLError as exc:
        return 0, f"connection_error: {exc.reason}"


def main() -> int:
    parser = argparse.ArgumentParser(description="POST one test lead_qualified event to n8n")
    parser.add_argument(
        "--url",
        default=(
            (os.getenv("N8N_LEAD_WEBHOOK_URL") or "").strip()
            or (os.getenv("N8N_FOLLOWUP_WEBHOOK_URL") or "").strip()
            or DEFAULT_WEBHOOK
        ),
        help="Deployed Mega_Workflow webhook URL",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payload only; no HTTP")
    parser.add_argument(
        "--timeout",
        type=int,
        default=max(5, int(os.getenv("N8N_TIMEOUT_SECONDS") or "15")),
    )
    args = parser.parse_args()

    payload = build_sample_payload()
    print("Target URL:", args.url)
    print("event:", payload.get("event"))
    print("event_id:", payload.get("event_id"))
    print("lead.phone:", payload["lead"].get("phone"))
    print("lead.email:", payload["lead"].get("email"))
    print("extraction.intent_status:", payload["extraction"].get("intent_status"))
    print()
    print("=== FULL PAYLOAD ===")
    print(json.dumps(payload, indent=2))
    print()

    if args.dry_run:
        print("Dry run only — no request sent.")
        return 0

    secret = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip() or None
    if secret:
        print("Sending header X-Aakashvani-Webhook-Secret: <set>")
    else:
        print("N8N_WEBHOOK_SECRET not set — sending without webhook secret header.")

    status, text = post_json(args.url, payload, secret=secret, timeout=args.timeout)
    print()
    print("=== RESPONSE ===")
    print("HTTP status:", status if status else "(no response)")
    print("Body:", text[:2000] if text else "(empty)")
    print()
    if status and 200 <= status < 300:
        print("OK - check n8n Mega_Workflow Executions for this event_id.")
        return 0
    print("FAILED - see status/body above. Common causes: workflow inactive, auth, wrong URL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

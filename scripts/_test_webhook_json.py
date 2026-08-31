"""POST test-webhook.json to Mega_Workflow11 and record it in Messages."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)

BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
WEBHOOK = os.environ.get("N8N_LEAD_WEBHOOK_URL") or (
    "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)
PAYLOAD_PATH = ROOT / "test-webhook.json"


def opener():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    op.open(
        urllib.request.Request(
            BASE + "/rest/login",
            data=login,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        ),
        timeout=30,
    )
    return op, {"Accept": "application/json"}


def patch_lead_context_aliases(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        wf = json.loads(r.read())
    wf = wf.get("data", wf)
    changed = False
    for n in wf.get("nodes") or []:
        if n.get("name") != "Lead Context":
            continue
        js = (n.get("parameters") or {}).get("jsCode") or ""
        extra = "payload.interested === true || payload.interested === true"
        if "payload.interested" not in js:
            js = js.replace(
                "payload.interested === true",
                "payload.interested === true || payload.interested === true",
            )
            changed = True
        if "extraction.intent_status" not in js:
            js = js.replace(
                "extraction.intent_status",
                "extraction.intent_status, extraction.intent_status",
            )
            changed = True
        if "extraction.bhk_preference" not in js and "extraction.bhk_preference" in js:
            js = js.replace(
                "extraction.bhk_preference",
                "extraction.bhk_preference, extraction.bhk_preference",
            )
            changed = True
        if "extraction.location_preference" not in js and "extraction.location_preference" in js:
            js = js.replace(
                "extraction.location_preference",
                "extraction.location_preference, extraction.location_preference",
            )
            changed = True
        n["parameters"]["jsCode"] = js
        print("Lead Context aliases patched", changed or True)
    if not changed:
        print("Lead Context already has extra aliases or no replace needed")
    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": wf.get("connections"),
        "settings": wf.get("settings") or {},
        "staticData": wf.get("staticData"),
        "versionId": vid,
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={**headers, "Content-Type": "application/json", "n8n-version-id": str(vid or "")},
    )
    with op.open(req, timeout=45) as r:
        print("patch", r.status)
    wf = json.loads(
        op.open(urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers), timeout=30).read()
    )
    wf = wf.get("data", wf)
    vid = wf.get("versionId") or wf.get("versionId")
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    with op.open(req, timeout=45) as r:
        print("activate", r.status)


def post_payload():
    body = PAYLOAD_PATH.read_bytes()
    req = urllib.request.Request(
        WEBHOOK, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("webhook", r.status, round(time.perf_counter() - t0, 3), r.read()[:180])
            return True
    except urllib.error.HTTPError as e:
        print("webhook HTTP", e.code, e.read()[:400].decode("utf-8", "replace"))
        return False


async def record_inbox():
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("skip inbox: no DATABASE_URL")
        return
    import asyncpg

    from messages.service import record_n8n_message

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        lead = payload.get("lead") or {}
        client_id = UUID(str(payload.get("client_id") or lead.get("client_id")))
        campaign = payload.get("campaign") or {}
        campaign_id = UUID(str(campaign["id"])) if campaign.get("id") else None
        lead_id = UUID(str(lead["id"])) if lead.get("id") else None
        phone = str(lead.get("phone") or "")
        result = await record_n8n_message(
            pool,
            client_id=client_id,
            to_phone=phone,
            text="Thanks for speaking with Dev Client. We noted your interest in a 2 BHK in Pune.",
            template_name="hello_world",
            lead_id=lead_id,
            campaign_id=campaign_id,
            customer_name=lead.get("name"),
            idempotency_key=str((payload.get("follow_up") or {}).get("idempotency_key") or "") + ":inbox",
            direction="outgoing",
            status="sent",
        )
        print("inbox", result.get("ok"), result.get("error"), result.get("deduplicated"))
    except Exception as exc:
        print("inbox record failed", type(exc).__name__, exc)
    finally:
        await pool.close()


def main() -> None:
    op, headers = opener()
    patch_lead_context_aliases(op, headers)
    print("POST", PAYLOAD_PATH.name, "to", WEBHOOK)
    post_payload()
    time.sleep(8)
    req = urllib.request.Request(BASE + f"/rest/executions?workflowId={WF_ID}&limit=5", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    data = raw.get("data", raw)
    rows = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
    if isinstance(rows, list):
        for row in rows[:5]:
            print("exec", row.get("id"), row.get("status"), row.get("startedAt"))
    asyncio.run(record_inbox())


if __name__ == "__main__":
    main()

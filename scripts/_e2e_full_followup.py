"""One interested-lead POST that includes record_url, then inspect Record node."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)

N8N_BASE = (os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WEBHOOK = (
    os.getenv("N8N_LEAD_WEBHOOK_URL")
    or "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)
WF = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    op.open(
        urllib.request.Request(
            N8N_BASE + "/rest/login",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    )
    return op


def flatted(arr):
    cache: dict[int, object] = {}

    def revive(token):
        if isinstance(token, str):
            try:
                idx = int(token)
            except ValueError:
                return token
            return resolve(idx)
        return token

    def resolve(idx):
        if idx in cache:
            return cache[idx]
        raw = arr[idx]
        if isinstance(raw, list):
            out: list = []
            cache[idx] = out
            out.extend(revive(x) for x in raw)
            return out
        if isinstance(raw, dict):
            out_d: dict = {}
            cache[idx] = out_d
            for k, v in raw.items():
                out_d[k] = revive(v)
            return out_d
        cache[idx] = raw
        return raw

    return resolve(0)


def main() -> None:
    from integrations.n8n.payload import _context_url, _record_url

    event_id = f"e2e-record-{uuid4()}"
    payload = {
        "event": "lead_qualified",
        "event_type": "INTERESTED_LEAD",
        "flow_type": "INITIAL_FOLLOWUP",
        "interested": True,
        "event_id": event_id,
        "client_id": "00000000-0000-4000-8000-000000000001",
        "lead": {
            "id": "00000000-0000-4000-8000-000000000011",
            "name": "Nitant",
            "phone": "+917397867643",
            "email": "singhnitant28@gmail.com",
            "lead_type": "interested",
        },
        "extraction": {
            "intent_status": "Interested",
            "intent_status": "hot",
            "bhk_preference": "2 BHK",
            "bhk_preference": "2 BHK",
            "location_preference": "Pune",
            "summary": "Interested in 2 BHK Pune",
            "budget": "8000000",
        },
        "campaign": {"id": "00000000-0000-4000-8000-000000000003", "name": "Aakashvani Test"},
        "client": {"id": "00000000-0000-4000-8000-000000000001", "name": "Dev Client"},
        "call": {"session_call_id": event_id, "id": event_id},
        "qualification": {"status": "interested"},
        "agent": {"id": None},
        "follow_up": {"idempotency_key": f"n8n_{event_id}_wa_1"},
        "aakashvani": {"record_url": _record_url(), "context_url": _context_url()},
        "fallback": {
            "generated_by": "aakashvani-backend",
            "whatsapp": {"message": "Hi Nitant, thanks for speaking with Dev Client about a 2 BHK in Pune."},
            "email": {"subject": "Follow-up from Dev Client", "body": "Hi Nitant,\nThanks for the call.\nDev Client"},
        },
        "metadata": {"test": True},
    }
    print("record_url_included", bool((payload["aakashvani"] or {}).get("record_url")))
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=20) as resp:
        elapsed = time.perf_counter() - t0
        print("webhook HTTP", resp.status, f"{elapsed:.3f}s", resp.read()[:120])

    time.sleep(4)
    op = login()
    q = urllib.parse.quote(json.dumps({"workflowId": WF}))
    listing = json.loads(
        op.open(
            urllib.request.Request(
                N8N_BASE + f"/rest/executions?filter={q}&limit=8",
                headers={"Accept": "application/json"},
            ),
            timeout=60,
        ).read()
    )
    items = listing.get("data", {}).get("results") if isinstance(listing.get("data"), dict) else listing.get("data")
    target = None
    for it in items or []:
        # Prefer executions that ran Send WhatsApp recently
        eid = it.get("id")
        detail = json.loads(
            op.open(
                urllib.request.Request(
                    N8N_BASE + f"/rest/executions/{eid}?includeData=true",
                    headers={"Accept": "application/json"},
                ),
                timeout=60,
            ).read()
        )
        data = detail.get("data") or detail
        raw = data.get("data")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list):
            raw = flatted(raw)
        run = ((raw or {}).get("resultData") or {}).get("runData") or {}
        if "Send WhatsApp" in run:
            target = eid
            print("\nusing execution", eid, "status", data.get("status"))
            rec_runs = run.get("Record in Aakashvani") or []
            for r in rec_runs:
                err = r.get("error")
                main = ((r.get("data") or {}).get("main") or [[]])
                head = main[0][0] if main and main[0] else {}
                js = (head or {}).get("json") if isinstance(head, dict) else {}
                print("Record error", err)
                print("Record json", json.dumps(js, default=str)[:600])
            break
    if not target:
        print("no Send WhatsApp execution found in last 8")
        for it in items or []:
            print(" ", it.get("id"), it.get("startedAt"))


if __name__ == "__main__":
    main()

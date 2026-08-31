"""Stop Add Lead from blocking WhatsApp template; send template first; retest."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
WEBHOOK = os.environ.get("N8N_LEAD_WEBHOOK_URL") or (
    "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)
PHONE = "+917397867643"
EMAIL = "singhnitant28@gmail.com"


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


def get_wf(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        return json.loads(r.read()).get("data") or json.loads(r.read())


def get_wf(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    return raw.get("data", raw)


def main() -> None:
    op, headers = opener()
    wf = get_wf(op, headers)
    for n in wf.get("nodes") or []:
        if n.get("name") == "Add Lead":
            n["onError"] = "continueRegularOutput"
            print("Add Lead continue on error")
    con = wf.get("connections") or {}
    con["If Interested"] = {
        "main": [
            [
                {"node": "Send template", "type": "main", "index": 0},
                {"node": "Generate Follow-up Email", "type": "main", "index": 0},
            ],
            [],
        ]
    }
    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": con,
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
    wf = get_wf(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    with op.open(req, timeout=45) as r:
        print("activate", r.status)
    print("active", get_wf(op, headers).get("active"))

    body = json.dumps(
        {
            "event": "lead_qualified",
            "interested": True,
            "event_id": f"manual-test-{int(time.time())}",
            "lead": {
                "name": "Nitant Singh",
                "phone": PHONE,
                "email": EMAIL,
                "lead_type": "warm",
                "whatsapp_opt_in": True,
            },
            "extraction": {
                "intent_status": "Interested",
                "summary": "Interested after the call. Follow up on WhatsApp and email.",
            },
            "qualification": {"status": "interested"},
            "client": {"name": "BhuvisX"},
            "campaign": {"name": "Mega_Workflow11 live test"},
        }
    ).encode()
    req = urllib.request.Request(
        WEBHOOK, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("webhook", r.status, r.read()[:200])
    except urllib.error.HTTPError as e:
        print("webhook HTTP", e.code, e.read()[:400].decode("utf-8", "replace"))
    time.sleep(12)
    req = urllib.request.Request(BASE + f"/rest/executions?workflowId={WF_ID}&limit=3", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    data = raw.get("data", raw)
    rows = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
    if isinstance(rows, list):
        for row in rows[:3]:
            print("exec", row.get("id"), row.get("status"))


if __name__ == "__main__":
    main()

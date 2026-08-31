"""Tighten If Interested so 'not interested' does not match."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)
BASE = os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com"
WF = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")
BACKUP = Path("fixtures/n8n_exports_local")

LEAD_CONTEXT_INTERESTED = """
const rawIntent = String(pick(extraction.intent_status, extraction.intent_status, qualification.status, lead.lead_type)).toLowerCase();
const negative = /not[\\s_]?interest|unqualified|\\bcold\\b/.test(rawIntent);
const interested = payload.interested === true
  || String(payload.interested) === 'true'
  || (!negative && /\\b(hot|warm|qualified|interested)\\b/.test(rawIntent));
"""


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    op.open(
        urllib.request.Request(
            BASE + "/rest/login",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    )
    return op


def main() -> None:
    op = login()
    wf = json.loads(
        op.open(
            urllib.request.Request(BASE + f"/rest/workflows/{WF}", headers={"Accept": "application/json"}),
            timeout=60,
        ).read()
    )
    if "nodes" not in wf and "data" in wf:
        wf = wf["data"]
    BACKUP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (BACKUP / f"Mega_Workflow__backup_{stamp}.json").write_text(json.dumps(wf, indent=2), encoding="utf-8")

    by = {n["name"]: n for n in wf["nodes"]}
    interested = by["If Interested"]
    interested["parameters"]["conditions"]["combinator"] = "or"
    interested["parameters"]["conditions"]["conditions"] = [
        {
            "id": "int-flag",
            "leftValue": "={{ $json.interested }}",
            "rightValue": True,
            "operator": {"type": "boolean", "operation": "true"},
        },
        {
            "id": "int-hot-eq",
            "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
            "rightValue": "hot",
            "operator": {"type": "string", "operation": "equals"},
        },
        {
            "id": "int-warm-eq",
            "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
            "rightValue": "warm",
            "operator": {"type": "string", "operation": "equals"},
        },
        {
            "id": "int-interested-eq",
            "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
            "rightValue": "interested",
            "operator": {"type": "string", "operation": "equals"},
        },
    ]

    lc = by["Lead Context"]
    js = lc["parameters"]["jsCode"]
    old = "const interested = payload.interested === true\n  || String(payload.interested) === 'true'\n  || /interest|hot|warm|qualified/i.test(String(pick(extraction.intent_status, qualification.status, lead.lead_type, payload.event_type)));"
    if old not in js:
        # try compact
        import re as _re
        js2, n = _re.subn(
            r"const interested = payload\.interested === true[\s\S]*?;",
            LEAD_CONTEXT_INTERESTED.strip() + "\n",
            js,
            count=1,
        )
        if n != 1:
            print("Lead Context interested block not replaced; dumping snippet")
            idx = js.find("interested")
            print(js[idx : idx + 400] if idx >= 0 else js[:400])
        else:
            lc["parameters"]["jsCode"] = js2
            print("Lead Context interested logic replaced")
    else:
        lc["parameters"]["jsCode"] = js.replace(old, LEAD_CONTEXT_INTERESTED.strip())
        print("Lead Context interested logic replaced (exact)")

    payload = {
        "name": wf.get("name"),
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {},
        "staticData": wf.get("staticData"),
        "versionId": wf.get("versionId"),
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "n8n-version-id": str(wf.get("versionId") or ""),
        },
    )
    saved = json.loads(op.open(req, timeout=60).read())
    data = saved.get("data", saved)
    print("published", data.get("versionId"), "active", data.get("active"))
    print("If Interested now uses equals + boolean flag (no substring match)")


if __name__ == "__main__":
    main()

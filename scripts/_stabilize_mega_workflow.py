"""Stabilize Mega_Workflow: If Interested equals-match + first_contact fields.

Does not recreate the workflow. Patches the live Mega_Workflow in place.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)
BASE = os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com"
WF = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")
BACKUP = Path("fixtures/n8n_exports_local")


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
    print("backup", stamp, "active", wf.get("active"), "nodes", len(wf.get("nodes") or []))

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
    print("patched If Interested")

    lc = by["Lead Context"]
    js = lc["parameters"].get("jsCode") or ""
    js2, n = re.subn(
        r"const interested = payload\.interested === true[\s\S]*?;",
        (
            "const rawIntent = String(pick(extraction.intent_status, extraction.intent_status, "
            "qualification.status, lead.lead_type)).toLowerCase();\n"
            "const negative = /not[\\s_]?interest|unqualified|\\bcold\\b/.test(rawIntent);\n"
            "const interested = payload.interested === true\n"
            "  || String(payload.interested) === 'true'\n"
            "  || (!negative && /\\b(hot|warm|qualified|interested)\\b/.test(rawIntent));"
        ),
        js,
        count=1,
    )
    if n != 1:
        print("Lead Context interested block not replaced, n=", n)
    else:
        js = js2
        print("patched Lead Context interested")

    extras = (
        "\n  first_contact_mode: pick(payload.first_contact && payload.first_contact.mode),\n"
        "  first_contact_template_name: pick(payload.first_contact && payload.first_contact.template_name),\n"
        "  first_contact_language: pick(payload.first_contact && payload.first_contact.language_code),\n"
        "  send_url: pick(aak.send_url),\n"
    )
    if "first_contact_mode:" not in js:
        js = js.replace("  record_url: pick(aak.record_url),", extras + "  record_url: pick(aak.record_url),")
        print("added first_contact + send_url fields")
    lc["parameters"]["jsCode"] = js

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


if __name__ == "__main__":
    main()

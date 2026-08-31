"""Route first contact to template, replies to session text, then keep active."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")


def opener():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps(
        {
            "emailOrLdapLoginId": os.environ["N8N_EMAIL"],
            "password": os.environ["N8N_PASSWORD"],
        }
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


def load(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    return raw.get("data", raw)


def main() -> None:
    op, headers = opener()
    wf = load(op, headers)
    nodes = []
    for n in wf.get("nodes") or []:
        node = dict(n)
        name = n.get("name")
        params = dict(node.get("parameters") or {})
        if name == "If1":
            params["conditions"] = {
                "options": {
                    "caseSensitive": False,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 3,
                },
                "conditions": [
                    {
                        "id": "inbound-executed",
                        "leftValue": "={{ $('WhatsApp Trigger').isExecuted }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            }
            node["parameters"] = params
            print("patched If1 inbound vs first-contact")
        if name == "Edit Fields1":
            assignments = (((params.get("assignments") or {}).get("assignments")) or [])
            new_assign = []
            for a in assignments:
                item = dict(a)
                if a.get("name") == "phone":
                    item["value"] = (
                        "={{ $('WhatsApp Trigger').isExecuted "
                        "? $('Edit Fields').item.json.phone "
                        ": $('Lead Context').item.json.phone }}"
                    )
                if a.get("name") == "name":
                    item["value"] = (
                        "={{ $('WhatsApp Trigger').isExecuted "
                        "? $('Edit Fields').item.json.name "
                        ": $('Lead Context').item.json.name }}"
                    )
                new_assign.append(item)
            params["assignments"] = {"assignments": new_assign}
            node["parameters"] = params
            print("patched Edit Fields1 phone/name")
        if name in {"Send message", "Send template"}:
            params["recipientPhoneNumber"] = "={{ $json.phone }}"
            node["parameters"] = params
            print("patched recipient on", name)
        nodes.append(node)

    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": wf.get("connections") or {},
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
    wf = load(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with op.open(req, timeout=45) as r:
            data = json.loads(r.read()).get("data", {})
            print("activate", r.status, "active", data.get("active") if isinstance(data, dict) else data)
    except urllib.error.HTTPError as e:
        print("activate HTTP", e.code, e.read()[:600].decode("utf-8", "replace"))
    wf = load(op, headers)
    print("final active", wf.get("active"))


if __name__ == "__main__":
    main()

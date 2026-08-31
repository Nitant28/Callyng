"""Dump Mega_Workflow11 nodes/connections/key params."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")


def main() -> None:
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
    raw = json.loads(
        op.open(
            urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers={"Accept": "application/json"}),
            timeout=30,
        ).read()
    )
    wf = raw.get("data", raw)
    print("name", wf.get("name"), "active", wf.get("active"), "nodes", len(wf.get("nodes") or []))
    for n in wf.get("nodes") or []:
        print("NODE", n.get("name"), n.get("type"), n.get("typeVersion"))
        params = n.get("parameters") or {}
        if n.get("name") in {
            "Generate WhatsApp Message",
            "Generate Follow-up Email",
            "Send a message",
            "Send template",
            "Send message",
            "Lead Context",
            "If",
            "If1",
            "Webhook",
        }:
            dump = dict(params)
            if "text" in dump and isinstance(dump["text"], str) and len(dump["text"]) > 400:
                dump["text"] = dump["text"][:400] + "..."
            print(json.dumps(dump, indent=2)[:1800])
            print("creds", n.get("credentials"))
    print("CONNECTIONS")
    print(json.dumps(wf.get("connections") or {}, indent=2))


if __name__ == "__main__":
    main()

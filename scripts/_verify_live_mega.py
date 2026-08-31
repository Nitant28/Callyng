"""Print live Mega_Workflow Gemini models and Lead Context type."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://n8n.bhuvisx.com"
WF = "4xarbWK3DXLbENzC"


def main() -> None:
    email = os.environ["N8N_EMAIL"]
    password = os.environ["N8N_PASSWORD"]
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=login,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=25):
        pass
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF}", headers={"Accept": "application/json"})
    with op.open(req, timeout=30) as r:
        wf = json.loads(r.read())
    if "nodes" not in wf and "data" in wf:
        wf = wf["data"]
    print("version", wf.get("versionId"), "active", wf.get("active"), "nodes", len(wf.get("nodes") or []))
    for n in wf.get("nodes") or []:
        nm = n.get("name")
        if nm == "Webhook":
            print("Webhook options", (n.get("parameters") or {}).get("options"))
        if n.get("disabled"):
            print("DISABLED", nm)
        if "Gemini" in nm or nm in ("Lead Context", "If Continue Chat", "Lookup Lead"):
            print(nm, "type=", n.get("type"), "disabled=", n.get("disabled"), "model=", (n.get("parameters") or {}).get("modelName"))
    conns = wf.get("connections") or {}
    for src in ("Lead Payload", "If Continue Chat", "If Has Email"):
        if src in conns:
            print("conn", src, "->", conns[src])


if __name__ == "__main__":
    main()

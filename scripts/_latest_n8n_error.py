"""Print last Mega_Workflow execution status + error (no secrets)."""
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
    req = urllib.request.Request(
        BASE + f"/rest/executions?workflowId={WF}&limit=3",
        headers={"Accept": "application/json"},
    )
    with op.open(req, timeout=25) as r:
        data = json.loads(r.read())
    items = data.get("data", data)
    if isinstance(items, dict):
        items = items.get("data") or items.get("results") or []
    for ex in items[:3]:
        print("id", ex.get("id"), "status", ex.get("status"), "started", ex.get("startedAt"))
    eid = items[0]["id"]
    req = urllib.request.Request(
        BASE + f"/rest/executions/{eid}?includeData=true",
        headers={"Accept": "application/json"},
    )
    with op.open(req, timeout=30) as r:
        full = json.loads(r.read())
    ex = full.get("data", full)
    print("detail status", ex.get("status"))
    blob = ex.get("data")
    if isinstance(blob, str):
        blob = json.loads(blob)
    # flattened: resultData error often in index 2
    if isinstance(blob, list) and len(blob) > 2 and isinstance(blob[2], dict):
        print("lastNode", blob[2].get("lastNodeExecuted"))
        err = blob[2].get("error")
        if isinstance(err, dict):
            print("error", err.get("message") or err)
        elif err:
            print("error", err)
        rd = blob[2].get("runData")
        print("runData type", type(rd).__name__, "keys-or-val", str(rd)[:80] if not isinstance(rd, dict) else list(rd)[:20])


if __name__ == "__main__":
    main()

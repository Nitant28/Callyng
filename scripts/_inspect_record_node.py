"""Print Record node URL expression and Lead Context output for an execution."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar

from dotenv import load_dotenv

load_dotenv(override=False)
BASE = os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com"
WF = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")


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
    op = login()
    wf = json.loads(
        op.open(
            urllib.request.Request(BASE + f"/rest/workflows/{WF}", headers={"Accept": "application/json"}),
            timeout=60,
        ).read()
    )
    if "nodes" not in wf and "data" in wf:
        wf = wf["data"]
    for n in wf.get("nodes") or []:
        if n.get("name") == "Record in Aakashvani":
            print("RECORD NODE PARAMS")
            print(json.dumps(n.get("parameters"), indent=2)[:2500])
        if n.get("name") == "Lead Context":
            js = (n.get("parameters") or {}).get("jsCode") or ""
            if "record_url" in js:
                for line in js.splitlines():
                    if "record" in line.lower() or "aakashvani" in line.lower() or "public_url" in line.lower():
                        print("LC", line[:200])

    eid = os.environ.get("EXEC_ID", "656")
    detail = json.loads(
        op.open(
            urllib.request.Request(
                BASE + f"/rest/executions/{eid}?includeData=true",
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
    for name in ("Lead Context", "Prepare Send", "Record in Aakashvani"):
        runs = run.get(name) or []
        for r in runs:
            main = ((r.get("data") or {}).get("main") or [[]])
            head = main[0][0] if main and main[0] else {}
            js = (head or {}).get("json") if isinstance(head, dict) else {}
            keys = list(js) if isinstance(js, dict) else []
            print(f"\n{name} keys", keys)
            if isinstance(js, dict):
                for k in ("record_url", "public_url", "context_url", "phone", "message"):
                    print(f"  {k}={js.get(k)!r}"[:200])


if __name__ == "__main__":
    main()

"""Print node-by-node timings for the latest Mega_Workflow executions."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from dotenv import load_dotenv

load_dotenv(override=False)

BASE = os.environ.get("N8N_BASE", "https://n8n.bhuvisx.com")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def get(op, path):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with op.open(req, timeout=90) as r:
        return json.loads(r.read())


def flatted_parse(arr):
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
    q = urllib.parse.quote(json.dumps({"workflowId": WF}))
    listing = get(op, f"/rest/executions?filter={q}&limit=12")
    items = listing.get("data", {}).get("results") if isinstance(listing.get("data"), dict) else listing.get("data")
    print("== recent executions ==")
    for it in items or []:
        print(f"  #{it.get('id')} {it.get('status')} started={it.get('startedAt')} stopped={it.get('stoppedAt')} mode={it.get('mode')}")

    # Prefer the longest / error executions
    for it in items or []:
        eid = it.get("id")
        detail = get(op, f"/rest/executions/{eid}?includeData=true")
        d = detail.get("data") or detail
        raw = d.get("data")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list):
            raw = flatted_parse(raw)
        run = ((raw or {}).get("resultData") or {}).get("runData") or {}
        print(f"\n== #{eid} status={d.get('status')} ==")
        rows = []
        for node, runs in run.items():
            for r in runs or []:
                start = r.get("startTime") or 0
                ms = r.get("executionTime") or 0
                err = r.get("error")
                msg = ""
                if err:
                    msg = (err.get("message") if isinstance(err, dict) else str(err))[:80]
                rows.append((ms, node, msg))
        rows.sort(reverse=True)
        total = sum(x[0] for x in rows)
        print(f"  summed node time: {total}ms ({total/1000:.1f}s)")
        for ms, node, msg in rows:
            flag = " ERROR" if msg else ""
            print(f"  {ms:7}ms  {node}{flag} {msg}")


if __name__ == "__main__":
    main()

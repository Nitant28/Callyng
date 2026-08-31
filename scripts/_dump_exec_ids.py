"""Dump node timings for specific Mega_Workflow execution IDs."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar

from dotenv import load_dotenv

load_dotenv(override=False)
BASE = os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com"


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
    ids = [int(x) for x in (sys.argv[1:] or ["623", "624", "625", "630", "632"])]
    op = login()
    for eid in ids:
        req = urllib.request.Request(
            BASE + f"/rest/executions/{eid}?includeData=true",
            headers={"Accept": "application/json"},
        )
        detail = json.loads(op.open(req, timeout=60).read())
        data = detail.get("data") or detail
        raw = data.get("data")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list):
            raw = flatted(raw)
        run = ((raw or {}).get("resultData") or {}).get("runData") or {}
        print(f"\n#{eid} status={data.get('status')}")
        rows = []
        for node, runs in run.items():
            for r in runs or []:
                err = r.get("error")
                msg = ""
                if err:
                    msg = (err.get("message") if isinstance(err, dict) else str(err))[:100]
                rows.append((r.get("executionTime") or 0, node, msg))
        rows.sort(reverse=True)
        for ms, node, msg in rows:
            extra = f" ERROR {msg}" if msg else ""
            print(f"  {ms:6}ms {node}{extra}")


if __name__ == "__main__":
    main()

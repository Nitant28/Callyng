"""Find recent executions that started from the HTTP Webhook (not WhatsApp Trigger)."""
from __future__ import annotations

import json
import os
import urllib.parse
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
    q = urllib.parse.quote(json.dumps({"workflowId": WF}))
    listing = json.loads(
        op.open(
            urllib.request.Request(
                BASE + f"/rest/executions?filter={q}&limit=25",
                headers={"Accept": "application/json"},
            ),
            timeout=60,
        ).read()
    )
    items = listing.get("data", {}).get("results") if isinstance(listing.get("data"), dict) else listing.get("data")
    for it in items or []:
        eid = it.get("id")
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
        nodes = list(run)
        kind = "HTTP" if "Webhook" in run else ("WA" if "WhatsApp Trigger" in run else "other")
        rec = "Record in Aakashvani" in run
        print(f"#{eid} {kind} nodes={len(nodes)} rec={rec} {it.get('startedAt')}")
        if kind == "HTTP":
            lc = ((run.get("Lead Context") or [{}])[0].get("data") or {}).get("main") or [[]]
            head = lc[0][0] if lc and lc[0] else {}
            js = (head or {}).get("json") or {}
            print("  record_url", (js.get("record_url") or "")[:90])
            rec_runs = run.get("Record in Aakashvani") or []
            if rec_runs:
                r = rec_runs[0]
                main = ((r.get("data") or {}).get("main") or [[]])
                rjs = ((main[0][0] if main and main[0] else {}) or {}).get("json")
                print("  record_out", json.dumps(rjs, default=str)[:250], "err", r.get("error"))


if __name__ == "__main__":
    main()

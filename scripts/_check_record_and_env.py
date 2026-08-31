"""Inspect record-node output and whether public URL is configured (no secrets)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)
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
    public = (os.getenv("AAKASHVANI_PUBLIC_URL") or "").strip()
    ngrok = (os.getenv("NGROK_URL") or "").strip()
    envn = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").strip()
    print("AAKASHVANI_PUBLIC_URL set", bool(public), "looks_ngrok", "ngrok" in public.lower())
    print("NGROK_URL set", bool(ngrok), "looks_ngrok", "ngrok" in ngrok.lower())
    print("ENV", envn or "(empty)")
    from integrations.n8n.payload import _context_url, _record_url, public_backend_base_url

    print("resolved public", public_backend_base_url())
    ru = _record_url()
    cu = _context_url()
    print("record_url host", (ru or "")[:80])
    print("context_url host", (cu or "")[:80])

    op = login()
    req = urllib.request.Request(
        BASE + "/rest/executions/623?includeData=true",
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
    for node in ("Record in Aakashvani", "Send WhatsApp", "Send Email", "Ensure WhatsApp Text", "If Interested"):
        runs = run.get(node) or []
        for r in runs:
            main = ((r.get("data") or {}).get("main") or [[]])
            head = main[0][0] if main and main[0] else None
            js = (head or {}).get("json") if isinstance(head, dict) else None
            print(f"\n{node} err={bool(r.get('error'))} json_keys={list(js)[:12] if isinstance(js, dict) else None}")
            if isinstance(js, dict):
                print("  snippet", json.dumps({k: js.get(k) for k in ("message", "id", "error", "record_url", "interested", "email") if k in js or True}, default=str)[:500])


if __name__ == "__main__":
    main()

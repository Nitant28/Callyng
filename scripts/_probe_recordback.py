"""Probe record-back URL reachability and WhatsApp provider message id (no secrets dumped)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
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
    from integrations.n8n.payload import _record_url, public_backend_base_url

    base = public_backend_base_url()
    print("public_base", base)
    for path in ("/internal/health", "/health"):
        url = f"{base}{path}" if base else None
        if not url:
            print("skip", path)
            continue
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                print(path, r.status, r.read()[:120])
        except urllib.error.HTTPError as e:
            print(path, "HTTP", e.code, e.read()[:160].decode("utf-8", "replace"))
        except Exception as e:
            print(path, "ERR", type(e).__name__, str(e)[:160])

    record = _record_url()
    print("record_url_set", bool(record))
    if record:
        payload = {
            "client_id": "00000000-0000-4000-8000-000000000001",
            "to_phone": "+917397867643",
            "text": "prod-validate record probe",
            "direction": "outgoing",
            "status": "sent",
            "idempotency_key": "prod-validate-record-probe-1",
        }
        req = urllib.request.Request(
            record,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                print("record POST", r.status, r.read()[:300].decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            print("record POST HTTP", e.code, e.read()[:400].decode("utf-8", "replace"))
        except Exception as e:
            print("record POST ERR", type(e).__name__, str(e)[:200])

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
    wa = ((run.get("Send WhatsApp") or [{}])[0].get("data") or {}).get("main") or [[]]
    head = wa[0][0] if wa and wa[0] else {}
    js = (head or {}).get("json") or {}
    msgs = js.get("messages")
    print("whatsapp messages", json.dumps(msgs, default=str)[:400])
    print("whatsapp contacts", json.dumps(js.get("contacts"), default=str)[:200])


if __name__ == "__main__":
    main()

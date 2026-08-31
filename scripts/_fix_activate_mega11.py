"""Fix HTTP Request1 URL so Mega_Workflow11 can activate."""
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
RECORD_URL = (
    (os.environ.get("AAKASHVANI_PUBLIC_URL") or os.environ.get("AAKASHVANI_PUBLIC_URL") or "").strip().rstrip("/")
    + "/internal/messages/record"
    if (os.environ.get("AAKASHVANI_PUBLIC_URL") or os.environ.get("AAKASHVANI_PUBLIC_URL"))
    else "={{ $('Lead Context').item.json.record_url || $('Webhook').item.json.body.aakashvani.record_url }}"
)


def opener():
    email = (os.environ.get("N8N_EMAIL") or "").strip()
    password = (os.environ.get("N8N_PASSWORD") or "").strip()
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=login,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30) as r:
        print("login", r.status)
    return op, {"Accept": "application/json"}


def load(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    return raw.get("data", raw)


def main() -> None:
    op, headers = opener()
    wf = load(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    print("active", wf.get("active"), "vid", vid)
    for n in wf.get("nodes") or []:
        if n.get("name") == "HTTP Request1":
            print("HTTP Request1 params", json.dumps(n.get("parameters") or {}, indent=2)[:1500])
        if n.get("name") in {"If", "If1", "Send template", "Send message"}:
            print("conn-related", n.get("name"))
    print("connections", json.dumps(wf.get("connections") or {}, indent=2)[:2500])

    nodes = []
    for n in wf.get("nodes") or []:
        node = dict(n)
        if n.get("name") == "HTTP Request1":
            params = dict(node.get("parameters") or {})
            params["method"] = params.get("method") or "POST"
            params["url"] = RECORD_URL
            params["onError"] = "continueRegularOutput"
            node["parameters"] = params
            node["onError"] = "continueRegularOutput"
            print("patched HTTP Request1 url")
        nodes.append(node)

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
        headers={
            **headers,
            "Content-Type": "application/json",
            "n8n-version-id": str(vid or ""),
        },
    )
    with op.open(req, timeout=45) as r:
        print("patch", r.status)

    wf = load(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    print("new vid", vid)
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with op.open(req, timeout=45) as r:
            data = json.loads(r.read())
            data = data.get("data", data)
            print("activate", r.status, "active", data.get("active"))
    except urllib.error.HTTPError as e:
        print("activate HTTP", e.code, e.read()[:800].decode("utf-8", "replace"))
    wf = load(op, headers)
    print("final active", wf.get("active"))


if __name__ == "__main__":
    main()

"""Deactivate Mega_Workflow, activate Mega_Workflow11, print webhook path."""
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
OLD_WF = os.environ.get("N8N_OLD_WF_ID", "4xarbWK3DXLbENzC")
NEW_WF = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")


def opener():
    email = (os.environ.get("N8N_EMAIL") or "").strip()
    password = (os.environ.get("N8N_PASSWORD") or "").strip()
    if not email or not password:
        raise SystemExit("Set N8N_EMAIL and N8N_PASSWORD")
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


def load(op, headers, wid):
    req = urllib.request.Request(BASE + f"/rest/workflows/{wid}", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    return raw.get("data", raw)


def set_active(op, headers, wid, active: bool):
    wf = load(op, headers, wid)
    vid = wf.get("versionId") or wf.get("versionId")
    print("version keys", [k for k in wf.keys() if "ersion" in k.lower()], "vid", vid)
    path = f"/rest/workflows/{wid}/{'activate' if active else 'deactivate'}"
    body = json.dumps({"versionId": vid}).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with op.open(req, timeout=45) as r:
            body = json.loads(r.read())
            data = body.get("data", body)
            print(("activate" if active else "deactivate"), wid, r.status, "active", data.get("active"))
            return data
    except urllib.error.HTTPError as e:
        print(("activate" if active else "deactivate"), "HTTP", e.code, e.read()[:500].decode("utf-8", "replace"))
        wf = load(op, headers, wid)
        payload = {
            "name": wf.get("name"),
            "nodes": wf.get("nodes"),
            "connections": wf.get("connections"),
            "settings": wf.get("settings") or {},
            "staticData": wf.get("staticData"),
            "versionId": wf.get("versionId"),
            "active": active,
        }
        req = urllib.request.Request(
            BASE + f"/rest/workflows/{wid}",
            data=json.dumps(payload).encode(),
            method="PATCH",
            headers={
                **headers,
                "Content-Type": "application/json",
                "n8n-version-id": str(wf.get("versionId") or ""),
            },
        )
        with op.open(req, timeout=45) as r:
            body = json.loads(r.read())
            data = body.get("data", body)
            print("PATCH active", active, r.status, "active", data.get("active"))
            return data


def main() -> None:
    op, headers = opener()
    old = load(op, headers, OLD_WF)
    new = load(op, headers, NEW_WF)
    print("old", old.get("name"), "active", old.get("active"), "nodes", len(old.get("nodes") or []))
    print("new", new.get("name"), "active", new.get("active"), "nodes", len(new.get("nodes") or []))

    wa_phone = None
    for n in old.get("nodes") or []:
        if n.get("name") == "Send WhatsApp" and n.get("type") == "n8n-nodes-base.whatsApp":
            wa_phone = (n.get("parameters") or {}).get("phoneNumberId")
            print("source phoneNumberId", wa_phone)

    webhook_path = None
    webhook_mode = None
    patched_nodes = []
    for n in new.get("nodes") or []:
        node = dict(n)
        params = dict(node.get("parameters") or {})
        if n.get("type") == "n8n-nodes-base.webhook":
            webhook_path = params.get("path") or n.get("webhookId")
            webhook_mode = params.get("responseMode")
            if params.get("responseMode") != "onReceived":
                params["responseMode"] = "onReceived"
                node["parameters"] = params
                print("set webhook responseMode onReceived")
        if n.get("type") == "n8n-nodes-base.whatsApp" and wa_phone:
            if not params.get("phoneNumberId"):
                params["phoneNumberId"] = wa_phone
                node["parameters"] = params
                print("set phoneNumberId on", n.get("name"))
        patched_nodes.append(node)
        creds = n.get("credentials") or {}
        print("node", n.get("name"), n.get("type"), "creds" if creds else "no-creds")

    if patched_nodes != (new.get("nodes") or []):
        payload = {
            "name": new.get("name"),
            "nodes": patched_nodes,
            "connections": new.get("connections") or {},
            "settings": new.get("settings") or {},
            "staticData": new.get("staticData"),
            "versionId": new.get("versionId"),
        }
        req = urllib.request.Request(
            BASE + f"/rest/workflows/{NEW_WF}",
            data=json.dumps(payload).encode(),
            method="PATCH",
            headers={
                **headers,
                "Content-Type": "application/json",
                "n8n-version-id": str(new.get("versionId") or ""),
            },
        )
        with op.open(req, timeout=45) as r:
            print("patch graph", r.status)

    print("webhook_path", webhook_path, "mode", webhook_mode)
    print("WEBHOOK_URL", f"{BASE}/webhook/{webhook_path}" if webhook_path else "")

    if old.get("active"):
        set_active(op, headers, OLD_WF, False)
    set_active(op, headers, NEW_WF, True)
    check = load(op, headers, NEW_WF)
    old2 = load(op, headers, OLD_WF)
    print("final new active", check.get("active"), "old active", old2.get("active"))


if __name__ == "__main__":
    main()

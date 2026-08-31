"""Attach live Mega_Workflow credentials onto mega_workflow11. Env auth only."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar

BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
SOURCE_WF = os.environ.get("N8N_SOURCE_WF_ID", "4xarbWK3DXLbENzC")
TARGET_NAME = os.environ.get("N8N_TARGET_WF_NAME", "mega_workflow11")


def opener():
    email = (os.environ.get("N8N_EMAIL") or "").strip()
    password = (os.environ.get("N8N_PASSWORD") or "").strip()
    if not email or not password:
        raise SystemExit("Set N8N_EMAIL and N8N_PASSWORD in the environment.")
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


def get_json(op, headers, path):
    req = urllib.request.Request(BASE + path, headers=headers)
    with op.open(req, timeout=30) as r:
        return json.loads(r.read())


def unwrap(payload):
    if isinstance(payload, dict) and "nodes" not in payload and "data" in payload:
        return payload["data"]
    return payload


def cred_fingerprint(node: dict) -> str:
    ntype = node.get("type") or ""
    name = (node.get("name") or "").lower()
    if "whatsAppTrigger" in ntype or "trigger" in name and "whatsapp" in name:
        return "whatsapp_trigger"
    if "whatsApp" in ntype or name.startswith("send whatsapp") or name == "send template":
        return "whatsapp"
    if "gmail" in ntype.lower() or "gmail" in name or name.startswith("send email"):
        return "gmail"
    if "gemini" in ntype.lower() or "gemini" in name or "palm" in ntype.lower():
        return "gemini"
    return ntype


def collect_creds(nodes):
    by_key = {}
    for n in nodes or []:
        creds = n.get("credentials")
        if not creds:
            continue
        key = cred_fingerprint(n)
        by_key.setdefault(key, creds)
        by_key.setdefault(n.get("type"), creds)
        by_key.setdefault((n.get("name") or "").lower(), creds)
    return by_key


def main() -> None:
    op, headers = opener()
    listing = unwrap(get_json(op, headers, "/rest/workflows"))
    workflows = listing if isinstance(listing, list) else listing.get("data") or listing.get("workflows") or []
    print("workflows", len(workflows))
    target = None
    for wf in workflows:
        name = (wf.get("name") or "")
        print("-", wf.get("id"), name, "active", wf.get("active"))
        if name.lower().replace(" ", "") in {TARGET_NAME.lower(), "mega_workflow11", "megaworkflow11"}:
            target = wf
    if target is None:
        for wf in workflows:
            if "11" in (wf.get("name") or "").lower() and "mega" in (wf.get("name") or "").lower():
                target = wf
                break
    if target is None:
        raise SystemExit("Could not find mega_workflow11")
    print("target", target.get("id"), target.get("name"))

    source = unwrap(get_json(op, headers, f"/rest/workflows/{SOURCE_WF}"))
    dest = unwrap(get_json(op, headers, f"/rest/workflows/{target['id']}"))
    print("source nodes", len(source.get("nodes") or []))
    print("dest nodes", len(dest.get("nodes") or []))

    live = collect_creds(source.get("nodes") or [])
    print("source cred keys", sorted({k for k in live if isinstance(k, str)}))

    changed = 0
    new_nodes = []
    for n in dest.get("nodes") or []:
        node = dict(n)
        key = cred_fingerprint(n)
        creds = live.get(n.get("type")) or live.get((n.get("name") or "").lower()) or live.get(key)
        needs = n.get("type") in {
            "n8n-nodes-base.gmail",
            "n8n-nodes-base.whatsApp",
            "n8n-nodes-base.whatsAppTrigger",
            "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
        } or key in {"gmail", "whatsapp", "whatsapp_trigger", "gemini"}
        if creds and needs:
            if node.get("credentials") != creds:
                node["credentials"] = creds
                changed += 1
                print("set creds", n.get("name"), n.get("type"), list(creds.keys()))
        new_nodes.append(node)

    payload = {
        "name": dest.get("name"),
        "nodes": new_nodes,
        "connections": dest.get("connections") or {},
        "settings": dest.get("settings") or {},
        "staticData": dest.get("staticData"),
        "versionId": dest.get("versionId"),
    }
    body = json.dumps(payload).encode()
    hdrs = {
        **headers,
        "Content-Type": "application/json",
        "n8n-version-id": str(dest.get("versionId") or ""),
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{target['id']}",
        data=body,
        method="PATCH",
        headers=hdrs,
    )
    with op.open(req, timeout=45) as r:
        saved = json.loads(r.read())
        data = saved.get("data", saved)
        print("PATCH", r.status, "changed", changed, "version", data.get("versionId"), "active", data.get("active"))
        missing = [
            n.get("name")
            for n in (data.get("nodes") or new_nodes)
            if cred_fingerprint(n) in {"gmail", "whatsapp", "whatsapp_trigger", "gemini"}
            and not n.get("credentials")
        ]
        print("still missing creds", missing)


if __name__ == "__main__":
    main()

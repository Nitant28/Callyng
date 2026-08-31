"""Publish local Mega_Workflow JSON to n8n.bhuvisx.com, keeping live credentials.

Does not write secrets. Auth via N8N_API_KEY or N8N_EMAIL/N8N_PASSWORD in the
process environment (never committed).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

BASE = (os.getenv("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")
PATCH = ROOT / "fixtures/n8n_exports_local/Mega_Workflow__patched.json"


def _opener():
    api_key = (os.getenv("N8N_API_KEY") or "").strip()
    email = (os.getenv("N8N_EMAIL") or "").strip()
    password = (os.getenv("N8N_PASSWORD") or "").strip()
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    if api_key:
        return op, {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    if not email or not password:
        raise SystemExit(
            "BLOCKED: set N8N_API_KEY (preferred) or N8N_EMAIL+N8N_PASSWORD in the "
            "shell environment, not in git."
        )
    login = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=login,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op, {"Accept": "application/json"}


def main() -> None:
    patched = json.loads(PATCH.read_text(encoding="utf-8"))
    op, headers = _opener()
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        current = json.loads(r.read())
    if "nodes" not in current and "data" in current:
        current = current["data"]
    print("live nodes", len(current.get("nodes") or []), "version", current.get("versionId"))
    print("patched nodes", len(patched.get("nodes") or []))

    live_creds = {n.get("name"): n.get("credentials") for n in (current.get("nodes") or []) if n.get("credentials")}
    merged_nodes = []
    for n in patched.get("nodes") or []:
        node = dict(n)
        live = live_creds.get(n.get("name"))
        if live and not node.get("credentials"):
            node["credentials"] = live
            print("kept credentials on", n.get("name"))
        elif live and node.get("credentials"):
            # Prefer live IDs so we never drop working Gmail/WhatsApp/Gemini.
            node["credentials"] = live
            print("replaced patched creds with live IDs for", n.get("name"))
        merged_nodes.append(node)

    payload = {
        "name": current.get("name") or "Mega_Workflow",
        "nodes": merged_nodes,
        "connections": patched.get("connections") or current.get("connections"),
        "settings": current.get("settings") or patched.get("settings") or {},
        "staticData": current.get("staticData"),
        "versionId": current.get("versionId"),
    }
    body = json.dumps(payload).encode()
    hdrs = {
        **headers,
        "Content-Type": "application/json",
        "n8n-version-id": str(current.get("versionId") or ""),
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}",
        data=body,
        method="PATCH",
        headers=hdrs,
    )
    try:
        with op.open(req, timeout=45) as r:
            saved = json.loads(r.read())
            data = saved.get("data", saved)
            print("PUT", r.status, "version", data.get("versionId"), "active", data.get("active"))
    except urllib.error.HTTPError as e:
        print("PUT_HTTP", e.code, e.read()[:800].decode("utf-8", "replace"))
        raise


if __name__ == "__main__":
    main()

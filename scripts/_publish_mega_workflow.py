"""Publish patched Mega_Workflow to n8n.bhuvisx.com. Credentials via env only."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "https://n8n.bhuvisx.com"
WF_ID = "4xarbWK3DXLbENzC"
PATCH = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")


def main() -> None:
    email = os.environ.get("N8N_EMAIL")
    password = os.environ.get("N8N_PASSWORD")
    if not email or not password:
        raise SystemExit("Set N8N_EMAIL and N8N_PASSWORD in the environment.")
    patched = json.loads(PATCH.read_text(encoding="utf-8"))
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=login,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with opener.open(req, timeout=30) as r:
        print("login", r.status)

    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers={"Accept": "application/json"})
    with opener.open(req, timeout=30) as r:
        current = json.loads(r.read())
    if "nodes" not in current and "data" in current:
        current = current["data"]
    print("current version", current.get("versionId"), "nodes", len(current.get("nodes") or []))

    payload = {
        "name": current.get("name") or "Mega_Workflow",
        "nodes": patched["nodes"],
        "connections": patched["connections"],
        "settings": current.get("settings") or patched.get("settings") or {},
        "staticData": current.get("staticData"),
        "versionId": current.get("versionId"),
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}",
        data=body,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "n8n-version-id": str(current.get("versionId") or ""),
        },
    )
    try:
        with opener.open(req, timeout=45) as r:
            saved = json.loads(r.read())
            data = saved.get("data", saved)
            print("PUT", r.status, "new version", data.get("versionId"), "active", data.get("active"))
    except urllib.error.HTTPError as e:
        print("PUT_HTTP", e.code, e.read()[:800])
        raise


if __name__ == "__main__":
    main()

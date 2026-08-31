"""Print error details for a Mega_Workflow11 execution."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
EXEC_ID = sys.argv[1] if len(sys.argv) > 1 else "667"


def main() -> None:
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    op.open(
        urllib.request.Request(
            BASE + "/rest/login",
            data=login,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        ),
        timeout=30,
    )
    raw = json.loads(
        op.open(
            urllib.request.Request(
                BASE + f"/rest/executions/{EXEC_ID}?includeData=true",
                headers={"Accept": "application/json"},
            ),
            timeout=30,
        ).read()
    )
    data = raw.get("data", raw)
    print("status", data.get("status"), "mode", data.get("mode"))
    run = (data.get("data") or {}).get("resultData") or {}
    err = run.get("error")
    print("top error", json.dumps(err, indent=2)[:1500] if err else None)
    last = run.get("lastNodeExecuted")
    print("last node", last)
    results = run.get("runData") or {}
    for name, runs in results.items():
        print("ran", name)
        if not runs:
            continue
        e = (runs[-1] or {}).get("error")
        if e:
            print("  ERROR", name, json.dumps(e, indent=2)[:800])


if __name__ == "__main__":
    main()

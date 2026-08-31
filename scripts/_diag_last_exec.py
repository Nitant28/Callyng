"""Print last Mega_Workflow execution: nodes, last node, error, key fields."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://n8n.bhuvisx.com"
WF = "4xarbWK3DXLbENzC"


def resolve(token, table):
    seen = set()

    def inner(v):
        if isinstance(v, int) and 0 <= v < len(table):
            if v in seen:
                return None
            seen.add(v)
            return inner(table[v])
        if isinstance(v, str) and v.isdigit():
            i = int(v)
            if 0 <= i < len(table):
                if i in seen:
                    return None
                seen.add(i)
                return inner(table[i])
        if isinstance(v, dict):
            return {k: inner(x) for k, x in v.items()}
        if isinstance(v, list):
            return [inner(x) for x in v]
        return v

    return inner(token)


def main() -> None:
    email = os.environ["N8N_EMAIL"]
    password = os.environ["N8N_PASSWORD"]
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=login,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=25):
        pass
    req = urllib.request.Request(
        BASE + f"/rest/executions?workflowId={WF}&limit=5",
        headers={"Accept": "application/json"},
    )
    with op.open(req, timeout=25) as r:
        data = json.loads(r.read())
    items = data.get("data", data)
    if isinstance(items, dict):
        items = items.get("data") or items.get("results") or []
    for ex in items[:5]:
        print("EXEC", ex.get("id"), ex.get("status"), ex.get("startedAt"), "stopped", ex.get("stoppedAt"))
    eid = items[0]["id"]
    req = urllib.request.Request(
        BASE + f"/rest/executions/{eid}?includeData=true",
        headers={"Accept": "application/json"},
    )
    with op.open(req, timeout=40) as r:
        full = json.loads(r.read())
    ex = full.get("data", full)
    print("STATUS", ex.get("status"), "finished", ex.get("finished"))
    blob = ex.get("data")
    if isinstance(blob, str):
        blob = json.loads(blob)
    root = resolve(0, blob) if isinstance(blob, list) else blob
    rd = (root.get("resultData") or {}) if isinstance(root, dict) else {}
    print("lastNode", rd.get("lastNodeExecuted"))
    err = rd.get("error")
    if isinstance(err, dict):
        print("ERROR", (err.get("message") or str(err))[:500])
        desc = err.get("description") or err.get("stack")
        if desc:
            print("DESC", str(desc)[:400])
    elif err:
        print("ERROR", str(err)[:500])
    run = rd.get("runData") or {}
    print("NODES", list(run.keys()))
    watch = [
        "Lead Context",
        "Store Lead",
        "If Interested",
        "Lead Payload",
        "Generate WhatsApp Message",
        "Ensure WhatsApp Text",
        "Prepare Send",
        "If Has WhatsApp Text",
        "Send WhatsApp",
        "If Has Email",
        "Generate Follow-up Email",
        "Send Email",
        "Record in Aakashvani",
    ]
    for name in watch:
        runs = run.get(name)
        if not runs:
            print(f"-- {name}: NOT RUN")
            continue
        r0 = runs[0]
        e = r0.get("error")
        main = (r0.get("data") or {}).get("main") or []
        true_items = main[0] if main else []
        print(f"-- {name}: error={bool(e)} true_items={len(true_items or [])}")
        if e:
            print("   ERR", (e.get("message") if isinstance(e, dict) else e))
        if true_items:
            item = (true_items[0] or {}).get("json") or {}
            bits = {k: item.get(k) for k in ("name", "phone", "phone_e164", "email", "message", "flow_type", "intent_status") if k in item}
            if bits:
                print("  ", bits)
            out = item.get("output")
            if isinstance(out, dict) and out.get("message"):
                print("   output.message", str(out.get("message"))[:160])


if __name__ == "__main__":
    main()

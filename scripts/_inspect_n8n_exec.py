"""Inspect one n8n execution runData. Credentials via env."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://n8n.bhuvisx.com"
EXEC_ID = os.environ.get("N8N_EXEC_ID", "387")


def resolve(token, table):
    """Resolve n8n flattened JSON pointers (integer indexes)."""
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
    email = os.environ.get("N8N_EMAIL")
    password = os.environ.get("N8N_PASSWORD")
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
    with op.open(req, timeout=25):
        pass
    req = urllib.request.Request(
        BASE + f"/rest/executions/{EXEC_ID}?includeData=true",
        headers={"Accept": "application/json"},
    )
    with op.open(req, timeout=30) as r:
        data = json.loads(r.read())
    ex = data.get("data", data)
    print("ex_keys", list(ex.keys())[:30] if isinstance(ex, dict) else type(ex))
    print("workflowVersionId", ex.get("workflowVersionId"))
    print("workflowId", ex.get("workflowId"))
    rd = ex.get("data") if isinstance(ex, dict) else None
    print("rd_type", type(rd).__name__)
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except json.JSONDecodeError:
            print("rd is non-json string", rd[:80])
            rd = {}
    table = rd if isinstance(rd, list) else None
    if isinstance(rd, list):
        print("rd_list_len", len(rd))
        if len(rd) > 2 and isinstance(rd[2], dict):
            print("rd[2] keys", list(rd[2].keys())[:20])
            print("rd[2].lastNodeExecuted", rd[2].get("lastNodeExecuted"))
        root = resolve(0, rd) if rd else {}
        rd = rd[0] if rd and isinstance(rd[0], dict) else {}
        if isinstance(root, dict):
            rd = root
    print("rd_keys", list(rd.keys())[:20])
    rd_result = rd.get("resultData") or rd.get("runData")
    print("resultData_type", type(rd_result).__name__)
    if isinstance(rd_result, dict):
        print("resultData_keys", list(rd_result.keys())[:30])
        print("lastNodeExecuted", rd_result.get("lastNodeExecuted"))
        print("error", rd_result.get("error"))
    elif isinstance(rd_result, str):
        print("resultData_str_prefix", repr(rd_result[:400]))
        # try parse nested json
        try:
            parsed = json.loads(rd_result)
            print("parsed_result_type", type(parsed).__name__)
            if isinstance(parsed, dict):
                print("parsed_keys", list(parsed.keys())[:20])
                res = parsed.get("runData") or parsed
        except json.JSONDecodeError:
            pass
    ed = rd.get("executionData")
    print("executionData_type", type(ed).__name__)
    if isinstance(ed, dict):
        print("executionData_keys", list(ed.keys())[:20])
        print("nodeExecutionStack_len", len(ed.get("nodeExecutionStack") or []))
    if isinstance(rd_result, str):
        rd_result = json.loads(rd_result)
    if isinstance(rd_result, dict) and "runData" in rd_result:
        res = rd_result.get("runData") or {}
    elif isinstance(rd_result, dict):
        res = rd_result
    else:
        res = {}
    print("status", ex.get("status"), "finished", ex.get("finished"))
    print("nodes_in_run:")
    for name in res:
        print(" ", name)
    watch = [
        "If Interested",
        "Lead Payload",
        "Generate WhatsApp Message",
        "Prepare Send",
        "If Has WhatsApp Text",
        "Send message",
        "If Has Email",
        "Generate Follow-up Email",
        "Send a message",
        "Store Lead",
        "Lead Context",
    ]
    for name in watch:
        runs = res.get(name)
        if not runs:
            print(f"-- {name}: NOT IN RUN")
            continue
        r0 = runs[0]
        err = r0.get("error")
        print(f"-- {name}: error={bool(err)}")
        if err:
            print("   ERR", err.get("message") if isinstance(err, dict) else err)
        main = (r0.get("data") or {}).get("main") or []
        if not main:
            print("   no main")
            continue
        if not main[0]:
            print("   TRUE branch empty / FALSE taken")
            if len(main) > 1:
                print("   false_items", len(main[1] or []))
            continue
        item = main[0][0].get("json") or {}
        print("   keys", list(item.keys())[:25])
        for k in [
            "name",
            "phone",
            "phone_e164",
            "email",
            "client_id",
            "client_name",
            "flow_type",
            "message",
            "intent_status",
            "lead_type",
        ]:
            if k in item:
                print("  ", k, str(item[k])[:200])
        out = item.get("output")
        if isinstance(out, dict) and "message" in out:
            print("   output.message", str(out.get("message"))[:220])


if __name__ == "__main__":
    main()

"""Read-only diagnostic of the live Mega_Workflow graph + latest execution errors.

Prints the full connection graph (main + ai_*), AI/code node parameters, and the
error details of the most recent executions so AI sub-node failures are visible.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("N8N_BASE", "https://n8n.bhuvisx.com")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")


def login():
    email = os.environ["N8N_EMAIL"]
    password = os.environ["N8N_PASSWORD"]
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def get(op, path):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with op.open(req, timeout=60) as r:
        return json.loads(r.read())


def unwrap(payload):
    if isinstance(payload, dict) and "data" in payload and "nodes" not in payload:
        return payload["data"]
    return payload


def main() -> None:
    op = login()
    wf = unwrap(get(op, f"/rest/workflows/{WF}"))
    nodes = wf.get("nodes") or []
    conns = wf.get("connections") or {}

    print(f"== workflow {wf.get('name')} version={wf.get('versionId')} active={wf.get('active')} nodes={len(nodes)}")

    by_name = {n.get("name"): n for n in nodes}
    print("\n== NODES ==")
    for n in nodes:
        print(
            f"  {n.get('name')!r:38} type={n.get('type')} v={n.get('typeVersion')}"
            f" onError={n.get('onError')} retry={n.get('retryOnFail')} disabled={n.get('disabled', False)}"
        )

    print("\n== CONNECTIONS ==")
    for src, data in conns.items():
        for kind, branches in (data or {}).items():
            for i, branch in enumerate(branches or []):
                if not branch:
                    print(f"  {src} [{kind}:{i}] -> (EMPTY)")
                for edge in branch or []:
                    print(f"  {src} [{kind}:{i}] -> {edge.get('node')} [{edge.get('type')}:{edge.get('index')}]")

    incoming = {name: [] for name in by_name}
    for src, data in conns.items():
        for kind, branches in (data or {}).items():
            for branch in branches or []:
                for edge in branch or []:
                    incoming.setdefault(edge.get("node"), []).append((src, kind))
    print("\n== ORPHANS (no incoming) ==")
    for name, ins in incoming.items():
        if not ins:
            print(f"  {name}")

    print("\n== KEY NODE PARAMS ==")
    for name, n in by_name.items():
        t = n.get("type") or ""
        if any(k in t for k in ("agent", "chainLlm", "lmChat", "outputParser", "memoryBufferWindow", "code")):
            print(f"\n--- {name} ({t}) ---")
            print(json.dumps(n.get("parameters") or {}, indent=2)[:4000])

    print("\n== RECENT EXECUTIONS ==")
    ex = get(op, "/rest/executions?filter=" + urllib.parse.quote(json.dumps({"workflowId": WF})) + "&limit=8")
    items = ex.get("data", {}).get("results") if isinstance(ex.get("data"), dict) else ex.get("data")
    for item in (items or [])[:8]:
        print(f"  #{item.get('id')} status={item.get('status')} started={item.get('startedAt')}")
    first_failed = None
    for item in items or []:
        if item.get("status") in {"error", "crashed"}:
            first_failed = item.get("id")
            break
    target = first_failed or ((items or [{}])[0].get("id"))
    if not target:
        return
    print(f"\n== EXECUTION {target} DETAIL ==")
    detail = get(op, f"/rest/executions/{target}")
    d = detail.get("data") or detail
    raw = d.get("data")
    if isinstance(raw, str):
        raw = json.loads(raw)
    run = ((raw or {}).get("resultData") or {}).get("runData") or {}
    err = ((raw or {}).get("resultData") or {}).get("error")
    if err:
        print("TOP ERROR:", json.dumps(err, indent=2)[:3000])
    for node, runs in run.items():
        for r in runs:
            e = r.get("error")
            if e:
                print(f"\n-- {node} ERROR --")
                print(json.dumps(e, indent=2)[:3000])
            else:
                out = ((r.get("data") or {}).get("main") or [[]])
                head = out[0][0] if out and out[0] else None
                print(f"\n-- {node} ok -> {json.dumps(head)[:600]}")


if __name__ == "__main__":
    main()

"""Partial manual run of Mega_Workflow that stops BEFORE any send node.

Validates the Gemini model name, the agent, and the structured output parser without
sending an email or a WhatsApp message. Destination nodes used:
  * "Ensure WhatsApp Text" -> stops before Prepare Send / Send WhatsApp
  * "Build Email"          -> stops before Send Email

Usage: python scripts/_partial_run_ai.py ["Ensure WhatsApp Text"]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = os.environ.get("N8N_BASE", "https://n8n.bhuvisx.com")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")
FIXTURE = Path("test-webhook.json")


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def call(op, path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "browser-id": "aakashvani-cli"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with op.open(req, timeout=120) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code, "body": e.read()[:1500].decode("utf-8", "replace")}


def flatted_parse(arr):
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
    destination = sys.argv[1] if len(sys.argv) > 1 else "Ensure WhatsApp Text"
    op = login()
    wf = call(op, f"/rest/workflows/{WF}")
    wf = wf.get("data", wf)

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trigger = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook")

    run_data = {
        trigger["name"]: [
            {
                "startTime": int(time.time() * 1000),
                "executionTime": 1,
                "executionStatus": "success",
                "source": [],
                "data": {
                    "main": [
                        [
                            {
                                "json": {
                                    "headers": {"content-type": "application/json"},
                                    "params": {},
                                    "query": {},
                                    "body": payload,
                                    "webhookUrl": "manual-partial-run",
                                    "executionMode": "test",
                                }
                            }
                        ]
                    ]
                },
            }
        ]
    }

    workflow_data = {
        "id": wf.get("id"),
        "name": wf.get("name"),
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {},
        "pinData": wf.get("pinData") or {},
    }
    trigger_task = run_data[trigger["name"]][0]

    variants = [
        (
            "v2-trigger-only",
            {
                "workflowData": workflow_data,
                "runData": run_data,
                "destinationNode": destination,
                "dirtyNodeNames": [],
                "triggerToStartFrom": {"name": trigger["name"], "data": trigger_task},
            },
        ),
        (
            "v1-startnodes",
            {
                "workflowData": workflow_data,
                "runData": run_data,
                "startNodes": [
                    {
                        "name": "Lead Context",
                        "sourceData": {"previousNode": trigger["name"], "previousNodeOutput": 0},
                    }
                ],
                "destinationNode": destination,
            },
        ),
        (
            "trigger-no-rundata",
            {
                "workflowData": workflow_data,
                "destinationNode": destination,
                "triggerToStartFrom": {"name": trigger["name"], "data": trigger_task},
            },
        ),
    ]

    print(f"starting partial run -> destination {destination!r}")
    res = None
    for label, body in variants:
        res = call(op, f"/rest/workflows/{WF}/run", "POST", body)
        if not (isinstance(res, dict) and res.get("__http_error")):
            print("accepted variant:", label)
            break
        print(f"  {label} -> HTTP {res['__http_error']}: {res['body'][:300]}")
    if isinstance(res, dict) and res.get("__http_error"):
        print("all variants failed")
        return
    exec_id = (res.get("data") or {}).get("executionId") or res.get("executionId")
    print("executionId:", exec_id)
    if not exec_id:
        print(json.dumps(res, default=str)[:1500])
        return

    for _ in range(40):
        time.sleep(3)
        detail = call(op, f"/rest/executions/{exec_id}")
        d = detail.get("data", detail)
        if isinstance(d, dict) and d.get("__http_error"):
            continue
        status = d.get("status")
        if status in {"running", "new", "waiting", None}:
            print("  status:", status)
            continue
        raw = d.get("data")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list):
            raw = flatted_parse(raw)
        result = (raw or {}).get("resultData") or {}
        print("\n== status:", status)
        if result.get("error"):
            print("TOP ERROR:", json.dumps(result["error"], indent=2, default=str)[:1500])
        for node, runs in (result.get("runData") or {}).items():
            for r in runs or []:
                err = r.get("error")
                if err:
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    desc = err.get("description") if isinstance(err, dict) else ""
                    print(f"\n!! {node}: {msg} | {desc}")
                main_out = (r.get("data") or {}).get("main") or []
                head = main_out[0][0] if main_out and main_out[0] else None
                pj = (head or {}).get("json") if isinstance(head, dict) else None
                if node in {
                    "Generate WhatsApp Message",
                    "Generate Follow-up Email",
                    "Ensure WhatsApp Text",
                    "Build Email",
                }:
                    print(f"\n>> {node}:\n{json.dumps(pj, indent=2, default=str)[:2500]}")
                else:
                    print(f"-- {node}: ok")
        return
    print("timed out waiting for execution to finish")


if __name__ == "__main__":
    main()

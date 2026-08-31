"""Inspect the live n8n version, the Gemini chat-model node schema, and available models."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("N8N_BASE", "https://n8n.bhuvisx.com")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")
NODE_TYPE = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini"


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
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with op.open(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code, "body": e.read()[:1200].decode("utf-8", "replace")}


def main() -> None:
    op = login()

    settings = call(op, "/rest/settings")
    sdata = settings.get("data", settings)
    print("n8n version:", sdata.get("versionCli"), "| instanceId set:", bool(sdata.get("instanceId")))

    wf = call(op, f"/rest/workflows/{WF}")
    wf = wf.get("data", wf)
    gem = next(
        (n for n in wf.get("nodes") or [] if n.get("type") == NODE_TYPE),
        None,
    )
    cred = (gem or {}).get("credentials") or {}
    print("gemini node typeVersion:", (gem or {}).get("typeVersion"))
    print("credential types on node:", list(cred.keys()))

    nt = call(
        op,
        "/rest/node-types",
        "POST",
        {"nodeInfos": [{"name": NODE_TYPE, "version": (gem or {}).get("typeVersion") or 1.1}]},
    )
    ntdata = nt.get("data", nt)
    desc = ntdata[0] if isinstance(ntdata, list) and ntdata else ntdata
    if isinstance(desc, dict) and desc.get("properties"):
        print("\n== node properties (modelName focus) ==")
        for prop in desc.get("properties") or []:
            if prop.get("name") in {"modelName", "model", "options"}:
                print(json.dumps(prop, indent=2)[:2500])
        print("\ndefaults:", json.dumps(desc.get("defaults"), default=str)[:300])
        print("declared version(s):", desc.get("version"))
    else:
        print("node-types response:", json.dumps(desc, default=str)[:800])

    cred_key, cred_meta = next(iter(cred.items()), (None, None))
    if cred_key and cred_meta:
        for method in ("modelSearch", "getModels", "gptModelSearch"):
            res = call(
                op,
                "/rest/dynamic-node-parameters/resource-locator-results",
                "POST",
                {
                    "path": "parameters.modelName",
                    "methodName": method,
                    "nodeTypeAndVersion": {
                        "name": NODE_TYPE,
                        "version": (gem or {}).get("typeVersion") or 1.1,
                    },
                    "currentNodeParameters": {},
                    "credentials": {cred_key: {"id": cred_meta.get("id"), "name": cred_meta.get("name")}},
                },
            )
            body = res.get("data", res)
            if isinstance(body, dict) and body.get("__http_error"):
                print(f"\nRL search '{method}': HTTP {body['__http_error']}")
                continue
            print(f"\nRL search '{method}':", json.dumps(body, default=str)[:2000])
            break

        opts = call(
            op,
            "/rest/dynamic-node-parameters/options",
            "POST",
            {
                "path": "parameters.modelName",
                "nodeTypeAndVersion": {
                    "name": NODE_TYPE,
                    "version": (gem or {}).get("typeVersion") or 1.1,
                },
                "currentNodeParameters": {},
                "credentials": {cred_key: {"id": cred_meta.get("id"), "name": cred_meta.get("name")}},
            },
        )
        obody = opts.get("data", opts)
        print("\noptions endpoint:", json.dumps(obody, default=str)[:3000])


if __name__ == "__main__":
    main()

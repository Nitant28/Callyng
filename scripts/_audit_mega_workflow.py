"""Deep read-only audit of local Mega_Workflow. Strips credential IDs/secrets."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

SECRET_KEYS = {
    "accessToken",
    "apiKey",
    "token",
    "password",
    "secret",
    "oauthTokenData",
    "clientSecret",
    "privateKey",
}


def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if k in SECRET_KEYS or "secret" in kl or "token" in kl or "password" in kl or "credential" in kl:
                if isinstance(v, (dict, list)):
                    out[k] = "<redacted>"
                elif v in (None, "", []):
                    out[k] = v
                else:
                    out[k] = "<redacted>"
            elif k == "id" and "cred" in json.dumps(obj).lower() and isinstance(v, str) and len(v) > 8:
                out[k] = v  # keep node ids; credential ids handled via credentials key
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def strip_credentials(node: dict) -> dict:
    n = dict(node)
    if "credentials" in n:
        # keep credential type names only, not IDs
        creds = {}
        for ctype, meta in (n.get("credentials") or {}).items():
            creds[ctype] = {
                "name": (meta or {}).get("name"),
                "id_present": bool((meta or {}).get("id")),
            }
        n["credentials"] = creds
    return n


db = Path(os.environ["USERPROFILE"]) / ".n8n" / "database.sqlite"
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute(
    "SELECT id, name, active, nodes, connections, settings, pinData FROM workflow_entity WHERE name = ?",
    ("Mega_Workflow",),
)
row = cur.fetchone()
if not row:
    raise SystemExit("Mega_Workflow not found")

wid, name, active, nodes_s, conns_s, settings_s, pin_s = row
nodes = json.loads(nodes_s)
conns = json.loads(conns_s)
settings = json.loads(settings_s) if settings_s else {}
pin = json.loads(pin_s) if pin_s else {}

# webhooks table
cur.execute(
    "SELECT webhookPath, method, node, webhookId FROM webhook_entity WHERE workflowId = ?",
    (wid,),
)
webhooks = [
    {"path": r[0], "method": r[1], "node": r[2], "webhookId": r[3]} for r in cur.fetchall()
]

safe_nodes = []
for n in nodes:
    cleaned = strip_credentials(n)
    cleaned["parameters"] = redact(cleaned.get("parameters") or {})
    # drop binary/large unused
    for drop in ("webhookId",):
        pass
    safe_nodes.append(
        {
            "name": cleaned.get("name"),
            "type": cleaned.get("type"),
            "typeVersion": cleaned.get("typeVersion"),
            "disabled": cleaned.get("disabled", False),
            "credentials": cleaned.get("credentials"),
            "parameters": cleaned.get("parameters"),
            "position": cleaned.get("position"),
        }
    )

export = {
    "id": wid,
    "name": name,
    "active": bool(active),
    "settings": settings,
    "webhooks_registered": webhooks,
    "nodes": safe_nodes,
    "connections": conns,
}

out = Path("fixtures/n8n_exports_local/Mega_Workflow__full_redacted.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(export, indent=2), encoding="utf-8")
print("Wrote", out)
print("active=", active, "nodes=", len(safe_nodes), "webhooks=", webhooks)

# Print connection graph
print("\n=== CONNECTION GRAPH ===")
for src, data in (conns or {}).items():
    mains = (data or {}).get("main") or []
    for i, branch in enumerate(mains):
        for edge in branch or []:
            print(f"  {src} [out{i}] -> {edge.get('node')} (type={edge.get('type')})")

# AI agent / IF / WhatsApp parameter highlights
print("\n=== KEY NODE DETAILS ===")
for n in safe_nodes:
    if n["name"] in {
        "Webhook",
        "Lead Context",
        "If",
        "If1",
        "Edit Fields",
        "Edit Fields1",
        "Send message",
        "Send template",
        "HTTP Request",
        "WhatsApp Trigger",
        "Generate WhatsApp Message",
        "Generate Follow-up Email",
        "Structured Output Parser",
        "Structured Output Parser1",
    }:
        print("\n---", n["name"], n["type"], "---")
        print(json.dumps(n["parameters"], indent=2)[:4000])
        if n.get("credentials"):
            print("credentials:", n["credentials"])

conn.close()

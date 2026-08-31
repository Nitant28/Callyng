"""Inspect live Mega_Workflow JSON. No credentials printed."""
from __future__ import annotations

import json
from pathlib import Path

p = Path("fixtures/n8n_exports_local/Mega_Workflow__live_prod.json")
wf = json.loads(p.read_text(encoding="utf-8"))
print("name", wf.get("name"), "active", wf.get("active"), "id", wf.get("id"))
print("\n=== NODES ===")
for n in wf.get("nodes", []):
    creds = n.get("credentials") or {}
    cred_names = []
    if isinstance(creds, dict):
        for t, c in creds.items():
            if isinstance(c, dict):
                cred_names.append(f"{t}:{c.get('name')}")
            else:
                cred_names.append(str(t))
    print(
        f"- {n.get('name')} | {n.get('type')} v{n.get('typeVersion')} "
        f"disabled={n.get('disabled')} creds={cred_names or None}"
    )

print("\n=== CONNECTIONS ===")
for src, data in (wf.get("connections") or {}).items():
    if not isinstance(data, dict):
        print(src, data)
        continue
    for kind, branches in data.items():
        for i, branch in enumerate(branches or []):
            for edge in branch or []:
                print(f"  {src} [{kind}#{i}] -> {edge.get('node')} ({edge.get('type')})")

print("\n=== KEY PARAMS ===")
interesting = {
    "Webhook",
    "Lead Context",
    "Edit Fields",
    "Edit Fields1",
    "If",
    "If1",
    "Send message",
    "Send template",
    "Send a message",
    "Generate WhatsApp Message",
    "Generate Follow-up Email",
    "Simple Memory",
    "HTTP Request",
    "WhatsApp Trigger",
}
for n in wf.get("nodes", []):
    if n.get("name") not in interesting:
        continue
    print("\n---", n.get("name"), "---")
    print(json.dumps(n.get("parameters") or {}, indent=2)[:4000])

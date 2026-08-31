"""One-off read-only inspect of local n8n SQLite workflows. No secrets printed."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

db = Path(os.environ["USERPROFILE"]) / ".n8n" / "database.sqlite"
print("DB:", db, "exists=", db.exists())
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)

for t in tables:
    if "workflow" in t.lower():
        cur.execute(f"PRAGMA table_info({t})")
        print(f"COLS {t}:", [c[1] for c in cur.fetchall()])

# n8n v2 often uses workflow_entity
for t in ("workflow_entity", "workflow"):
    if t not in tables:
        continue
    cur.execute(f"SELECT id, name, active FROM {t}")
    rows = cur.fetchall()
    print(f"\n=== {t} workflows ({len(rows)}) ===")
    for wid, name, active in rows:
        print(f"  id={wid!r} name={name!r} active={active}")

# Prefer full export of interesting workflows
targets = []
cur.execute("SELECT id, name, active, nodes, connections FROM workflow_entity")
for wid, name, active, nodes, connections in cur.fetchall():
    targets.append((wid, name, active, nodes, connections))

out_dir = Path(__file__).resolve().parent.parent / "fixtures" / "n8n_exports_local"
out_dir.mkdir(parents=True, exist_ok=True)

for wid, name, active, nodes, connections in targets:
    try:
        nodes_j = json.loads(nodes) if isinstance(nodes, str) else nodes
        conn_j = json.loads(connections) if isinstance(connections, str) else connections
    except Exception as exc:
        print("parse fail", name, exc)
        continue
    summary = {
        "id": wid,
        "name": name,
        "active": bool(active),
        "node_count": len(nodes_j or []),
        "nodes": [
            {
                "name": n.get("name"),
                "type": n.get("type"),
                "disabled": n.get("disabled", False),
                "parameters_keys": sorted((n.get("parameters") or {}).keys()),
            }
            for n in (nodes_j or [])
        ],
        "connection_keys": list((conn_j or {}).keys()),
    }
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))[:80]
    summary_path = out_dir / f"{safe}__summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nWrote", summary_path.name)
    print("Nodes:")
    for n in summary["nodes"]:
        print(f"  - {n['name']} [{n['type']}] disabled={n['disabled']}")

conn.close()
print("\nDone.")

import json
from pathlib import Path

wf = json.loads(Path("fixtures/n8n_exports_local/Mega_Workflow__live_prod.json").read_text(encoding="utf-8"))
for n in wf["nodes"]:
    print(n.get("id"), "|", n.get("name"), "| pos", n.get("position"), "| typeVersion", n.get("typeVersion"))
print("\nWF meta keys", [k for k in wf.keys() if k not in ("nodes", "connections", "pinData")])

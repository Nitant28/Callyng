"""Patch local Mega_Workflow JSON: If Interested uses exact equals, not contains."""
from __future__ import annotations

import json
from pathlib import Path

P = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")


def main() -> None:
    wf = json.loads(P.read_text(encoding="utf-8"))
    left = "={{ ($json.intent_status || '').toLowerCase().trim() }}"
    for n in wf.get("nodes") or []:
        if n.get("name") != "If Interested":
            continue
        n["parameters"]["conditions"]["combinator"] = "or"
        n["parameters"]["conditions"]["conditions"] = [
            {
                "id": "int-flag",
                "leftValue": "={{ $json.interested }}",
                "rightValue": True,
                "operator": {"type": "boolean", "operation": "true"},
            },
            {
                "id": "int-hot-eq",
                "leftValue": left,
                "rightValue": "hot",
                "operator": {"type": "string", "operation": "equals"},
            },
            {
                "id": "int-warm-eq",
                "leftValue": left,
                "rightValue": "warm",
                "operator": {"type": "string", "operation": "equals"},
            },
            {
                "id": "int-interested-eq",
                "leftValue": left,
                "rightValue": "interested",
                "operator": {"type": "string", "operation": "equals"},
            },
        ]
        n["notes"] = 'Exact interested/hot/warm only. "not interested" does not match.'
        print("patched", P)
        break
    else:
        raise SystemExit("If Interested not found")
    P.write_text(json.dumps(wf, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

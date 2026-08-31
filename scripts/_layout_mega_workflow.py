"""Clean Mega_Workflow layout, disconnect dead nodes, fix send/reply expressions."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")
OUT = SRC

POS = {
    "Webhook": [-1120, 200],
    "Lead Context": [-800, 200],
    "Store Lead": [-480, 200],
    "If Interested": [-160, 200],
    "If Has Email": [200, 40],
    "Generate Follow-up Email": [520, 40],
    "Send Email": [880, 40],
    "Google Gemini Chat Model": [520, 240],
    "Structured Output Parser": [760, 240],
    "Lead Payload": [200, 420],
    "Generate WhatsApp Message": [560, 420],
    "Prepare Send": [900, 420],
    "If Has WhatsApp Text": [1200, 420],
    "Send WhatsApp": [1520, 420],
    "Record in Aakashvani": [1840, 420],
    "Google Gemini Chat Model1": [520, 640],
    "Structured Output Parser1": [760, 640],
    "Simple Memory": [1000, 640],
    "WhatsApp Trigger": [-1120, 920],
    "Normalize Inbound": [-800, 920],
    "If Customer Message": [-480, 920],
    "Lookup Lead": [-160, 920],
    "Edit Fields": [2200, 40],
    "If": [2480, 40],
    "Edit Fields1": [2200, 220],
    "If1": [2480, 220],
    "Send template": [2200, 400],
    "When clicking ‘Execute workflow’": [2200, 580],
}

RENAME = {
    "Send a message": "Send Email",
    "Send message": "Send WhatsApp",
    "HTTP Request": "Record in Aakashvani",
}

STICKIES = [
    {
        "name": "Lane 1 — After call",
        "content": "## After an interested call\nWebhook → context → store lead → gate.\nTRUE splits to Email (top) and WhatsApp (middle).",
        "position": [-1180, -40],
        "width": 1280,
        "height": 400,
        "color": 7,
    },
    {
        "name": "Lane 2 — Email",
        "content": "## Email follow-up\nOnly if a valid email is present.",
        "position": [160, -40],
        "width": 900,
        "height": 360,
        "color": 5,
    },
    {
        "name": "Lane 3 — WhatsApp send",
        "content": "## WhatsApp outbound + replies\nLead Payload is shared by call follow-up AND inbound lookup.\nPrepare Send always reads Lead Payload + AI message.",
        "position": [160, 340],
        "width": 1900,
        "height": 420,
        "color": 4,
    },
    {
        "name": "Lane 4 — Customer reply",
        "content": "## Incoming WhatsApp\nIgnore statuses/self messages.\nLookup original lead by phone, then reuse Lead Payload.",
        "position": [-1180, 840],
        "width": 1280,
        "height": 280,
        "color": 6,
    },
]


def sticky(spec: dict) -> dict:
    return {
        "parameters": {
            "content": spec["content"],
            "height": spec["height"],
            "width": spec["width"],
            "color": spec["color"],
        },
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": spec["position"],
        "id": f"sticky-{spec['name'][:12].lower().replace(' ', '')}",
        "name": spec["name"],
    }


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    nodes = []
    seen = set()
    for n in wf["nodes"]:
        if n.get("name") in seen:
            continue
        seen.add(n["name"])
        nodes.append(n)
    wf["nodes"] = nodes

    for n in nodes:
        old = n["name"]
        if old in RENAME:
            n["name"] = RENAME[old]
        name = n["name"]
        if name in POS:
            n["position"] = POS[name]
        n.setdefault("notes", "")

    by = {n["name"]: n for n in nodes}

    by["Webhook"]["notes"] = "Aakashvani posts lead_qualified here after an interested call."
    by["Lead Context"]["notes"] = "Flatten webhook body into a stable lead object."
    by["Store Lead"]["notes"] = "Remember this lead by phone so WhatsApp replies can find it."
    by["Lead Payload"]["notes"] = "Shared contract for outbound AND inbound. Downstream nodes must use this, not Lead Context."
    by["Prepare Send"]["notes"] = "Builds E.164 phone + AI message. Never execute this node alone."
    by["Send WhatsApp"]["notes"] = "Sends via BhuvisX WhatsApp credential. Recipient is dynamic."
    by["Record in Aakashvani"]["notes"] = "Writes the follow-up into Aakashvani Messages for that campaign/client."
    by["Lookup Lead"]["notes"] = "Match incoming WhatsApp phone to the stored original lead."
    by["If Customer Message"]["notes"] = "Drop delivery receipts, empty messages, and our own echoes."

    by["Google Gemini Chat Model1"]["parameters"]["modelName"] = "models/gemini-2.0-flash"
    by["Google Gemini Chat Model"]["parameters"]["modelName"] = "models/gemini-2.0-flash"

    by["Simple Memory"]["parameters"]["sessionKey"] = "={{ $json.phone }}"
    by["Simple Memory"]["parameters"]["contextWindowLength"] = 10

    ps = by["Prepare Send"]
    for a in ps["parameters"]["assignments"]["assignments"]:
        if a.get("name") == "message":
            a["value"] = (
                "={{ $json.output && $json.output.message "
                "? $json.output.message "
                ": ($json.message || '') }}"
            )

    rec = by["Record in Aakashvani"]
    rec["onError"] = "continueRegularOutput"
    rec["parameters"]["url"] = "={{ $('Prepare Send').first().json.record_url }}"

    send = by["Send WhatsApp"]
    send["parameters"]["recipientPhoneNumber"] = "={{ $('Prepare Send').item.json.phone_e164 }}"
    send["parameters"]["textBody"] = "={{ $('Prepare Send').item.json.message }}"

    # Disconnect unused/legacy graph
    conns = wf["connections"]
    for dead in ("Edit Fields", "If", "If1", "Edit Fields1", "Send template", "When clicking ‘Execute workflow’"):
        conns.pop(dead, None)

    # Rewrite connections that used old names
    def rewrite_target(obj):
        if isinstance(obj, dict):
            if obj.get("node") in RENAME:
                obj["node"] = RENAME[obj["node"]]
            for v in obj.values():
                rewrite_target(v)
        elif isinstance(obj, list):
            for v in obj:
                rewrite_target(v)

    new_conns = {}
    for src, val in conns.items():
        new_src = RENAME.get(src, src)
        rewrite_target(val)
        new_conns[new_src] = val
    new_conns["Send WhatsApp"] = {
        "main": [[{"node": "Record in Aakashvani", "type": "main", "index": 0}]]
    }
    new_conns["If Interested"] = {
        "main": [
            [
                {"node": "Lead Payload", "type": "main", "index": 0},
                {"node": "If Has Email", "type": "main", "index": 0},
            ],
            [],
        ]
    }
    wf["connections"] = new_conns

    existing_notes = {n["name"] for n in nodes if n.get("type") == "n8n-nodes-base.stickyNote"}
    for spec in STICKIES:
        if spec["name"] not in existing_notes:
            nodes.append(sticky(spec))

    wf["settings"] = wf.get("settings") or {}
    wf["settings"]["executionOrder"] = "v1"

    OUT.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("layout+fixes written", OUT, "nodes", len(wf["nodes"]))


if __name__ == "__main__":
    main()

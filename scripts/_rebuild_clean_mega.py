"""Rebuild Mega_Workflow: production graph only, no clutter, Gemini off send path."""
from __future__ import annotations

import copy
import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")
OUT = SRC

KEEP = [
    "Webhook",
    "Lead Context",
    "Store Lead",
    "If Interested",
    "If Has Email",
    "Build Email",
    "Send Email",
    "Lead Payload",
    "Ensure WhatsApp Text",
    "Prepare Send",
    "If Has WhatsApp Text",
    "Send WhatsApp",
    "Record in Aakashvani",
    "WhatsApp Trigger",
    "Normalize Inbound",
    "If Customer Message",
    "Lookup Lead",
]

POS = {
    "Webhook": [-980, 200],
    "Lead Context": [-700, 200],
    "Store Lead": [-400, 200],
    "If Interested": [-80, 200],
    "If Has Email": [280, 0],
    "Build Email": [560, 0],
    "Send Email": [860, 0],
    "Lead Payload": [280, 200],
    "Ensure WhatsApp Text": [560, 200],
    "Prepare Send": [840, 200],
    "If Has WhatsApp Text": [1120, 200],
    "Send WhatsApp": [1420, 200],
    "Record in Aakashvani": [1720, 200],
    "WhatsApp Trigger": [-980, 480],
    "Normalize Inbound": [-700, 480],
    "If Customer Message": [-400, 480],
    "Lookup Lead": [-80, 480],
}

PAYLOAD_JS = r"""
const j = $input.first().json || {};
if (!j.flow_type) {
  j.flow_type = j.message && !j.summary ? 'CONTINUE_CHAT' : 'INITIAL_FOLLOWUP';
}
return [{ json: j }];
"""

PREPARE_JS = r"""
const src = $('Lead Payload').first().json || {};
const ai = $input.first().json || {};
const p = String(src.phone || '').trim();
const d = p.replace(/\D/g, '');
let e164 = '';
if (p.startsWith('+')) e164 = '+' + d;
else if (d.length === 10) e164 = '+91' + d;
else if (d.length === 12 && d.startsWith('91')) e164 = '+' + d;
else if (d) e164 = '+' + d;
const message = (ai.output && ai.output.message) || ai.message || src.message || '';
return [{ json: {
  ...src,
  phone_e164: e164,
  message: String(message || '').trim(),
  customer_name: src.name || '',
} }];
"""


def sticky(name: str, content: str, pos: list[int], w: int, h: int, color: int) -> dict:
    return {
        "parameters": {"content": content, "width": w, "height": h, "color": color},
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": pos,
        "id": "note-" + name.lower().replace(" ", "-")[:24],
        "name": name,
    }


def main() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    by = {}
    for n in raw["nodes"]:
        if n.get("type") == "n8n-nodes-base.stickyNote":
            continue
        by.setdefault(n["name"], n)

    nodes = []
    for name in KEEP:
        n = copy.deepcopy(by[name])
        n["position"] = POS[name]
        n.pop("disabled", None)
        nodes.append(n)

    by2 = {n["name"]: n for n in nodes}
    by2["Lead Payload"]["type"] = "n8n-nodes-base.code"
    by2["Lead Payload"]["typeVersion"] = 2
    by2["Lead Payload"]["parameters"] = {"jsCode": PAYLOAD_JS, "mode": "runOnceForAllItems"}
    by2["Lead Payload"]["notes"] = "Pass-through contract for outbound and inbound."

    by2["Prepare Send"]["type"] = "n8n-nodes-base.code"
    by2["Prepare Send"]["typeVersion"] = 2
    by2["Prepare Send"]["parameters"] = {"jsCode": PREPARE_JS, "mode": "runOnceForAllItems"}
    by2["Prepare Send"]["notes"] = "Builds E.164 + final WhatsApp text."

    by2["Send WhatsApp"]["parameters"]["recipientPhoneNumber"] = "={{ $json.phone_e164 }}"
    by2["Send WhatsApp"]["parameters"]["textBody"] = "={{ $json.message }}"
    by2["Send Email"]["parameters"]["sendTo"] = "={{ $json.email }}"
    by2["Send Email"]["parameters"]["subject"] = "={{ $json.output.subject }}"
    by2["Send Email"]["parameters"]["message"] = "={{ $json.output.body }}"
    by2["Record in Aakashvani"]["onError"] = "continueRegularOutput"
    by2["Record in Aakashvani"]["parameters"]["url"] = "={{ $('Prepare Send').first().json.record_url }}"

    nodes.extend(
        [
            sticky("Note Call", "## 1. After interested call", [-1020, 80], 1180, 280, 7),
            sticky("Note Email", "## 2. Email", [240, -80], 820, 220, 5),
            sticky("Note WhatsApp", "## 3. WhatsApp send", [240, 80], 1680, 280, 4),
            sticky("Note Reply", "## 4. Customer WhatsApp reply", [-1020, 400], 1180, 240, 6),
        ]
    )

    connections = {
        "Webhook": {"main": [[{"node": "Lead Context", "type": "main", "index": 0}]]},
        "Lead Context": {"main": [[{"node": "Store Lead", "type": "main", "index": 0}]]},
        "Store Lead": {"main": [[{"node": "If Interested", "type": "main", "index": 0}]]},
        "If Interested": {
            "main": [
                [
                    {"node": "Lead Payload", "type": "main", "index": 0},
                    {"node": "If Has Email", "type": "main", "index": 0},
                ],
                [],
            ]
        },
        "If Has Email": {"main": [[{"node": "Build Email", "type": "main", "index": 0}], []]},
        "Build Email": {"main": [[{"node": "Send Email", "type": "main", "index": 0}]]},
        "Lead Payload": {"main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]},
        "Ensure WhatsApp Text": {"main": [[{"node": "Prepare Send", "type": "main", "index": 0}]]},
        "Prepare Send": {"main": [[{"node": "If Has WhatsApp Text", "type": "main", "index": 0}]]},
        "If Has WhatsApp Text": {"main": [[{"node": "Send WhatsApp", "type": "main", "index": 0}], []]},
        "Send WhatsApp": {"main": [[{"node": "Record in Aakashvani", "type": "main", "index": 0}]]},
        "WhatsApp Trigger": {"main": [[{"node": "Normalize Inbound", "type": "main", "index": 0}]]},
        "Normalize Inbound": {"main": [[{"node": "If Customer Message", "type": "main", "index": 0}]]},
        "If Customer Message": {"main": [[{"node": "Lookup Lead", "type": "main", "index": 0}], []]},
        "Lookup Lead": {"main": [[{"node": "Lead Payload", "type": "main", "index": 0}]]},
    }

    clean = {
        "name": "Mega_Workflow",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "binaryMode": "separate"},
    }
    OUT.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    print("clean production graph", len(nodes), "nodes")


if __name__ == "__main__":
    main()

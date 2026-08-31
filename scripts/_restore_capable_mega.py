"""Restore full Mega_Workflow capability with a clean 4-lane layout."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

GEMINI = {"__rl": True, "mode": "id", "value": "models/gemini-2.5-flash"}
CREDS = {
    "googlePalmApi": {"id": "MSan1NcJu1Xvfkc1", "name": "Google Gemini(PaLM) Api account"}
}

EMAIL_PROMPT = """=You are an email assistant for Aakashvani, writing for {{$json.client_name || "our client"}}.
Use ONLY these fields. Do not invent facts.
Name: {{$json.name}}
Email: {{$json.email}}
Summary: {{$json.summary}}
BHK: {{$json.bhk_preference}}
Location: {{$json.location_preference}}
Budget: {{$json.budget}}
City: {{$json.lead_city}}
Return ONLY JSON: {"subject":"","body":""}
"""

WA_PROMPT = """=You are a WhatsApp sales assistant for {{$json.client_name || "our client"}}.
Use ONLY provided fields. Never invent prices or inventory.
MODE={{$json.flow_type}}
Name={{$json.name}} Summary={{$json.summary}} BHK={{$json.bhk_preference}} Location={{$json.location_preference}} Budget={{$json.budget}} City={{$json.lead_city}}
If MODE is INITIAL_FOLLOWUP (or legacy initial_followup): thank them for the call, 80-150 words, max 2 emojis, clear CTA.
If MODE is CONTINUE_CHAT (or legacy inbound_reply): answer Latest message={{$json.message}} using memory, under 120 words, max 1 emoji. If lead_found is false, be generic and offer a human.
Return ONLY JSON: {"message":""}
"""

POS = {
    "Webhook": [-980, 220],
    "Lead Context": [-700, 220],
    "Store Lead": [-400, 220],
    "If Interested": [-80, 220],
    "If Has Email": [220, 0],
    "Generate Follow-up Email": [500, 0],
    "Build Email": [820, 0],
    "Send Email": [1120, 0],
    "Google Gemini Chat Model": [500, 160],
    "Structured Output Parser": [740, 160],
    "Lead Payload": [220, 220],
    "Generate WhatsApp Message": [500, 220],
    "Ensure WhatsApp Text": [820, 220],
    "Prepare Send": [1100, 220],
    "If Has WhatsApp Text": [1380, 220],
    "Send WhatsApp": [1660, 220],
    "Record in Aakashvani": [1940, 220],
    "Google Gemini Chat Model1": [500, 400],
    "Structured Output Parser1": [740, 400],
    "Simple Memory": [980, 400],
    "WhatsApp Trigger": [-980, 560],
    "Normalize Inbound": [-700, 560],
    "If Customer Message": [-400, 560],
    "Lookup Lead": [-80, 560],
}


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in wf["nodes"] if n.get("type") != "n8n-nodes-base.stickyNote"}
    extras = []

    def add(node: dict) -> None:
        extras.append(node)

    add(
        {
            "parameters": {"promptType": "define", "text": EMAIL_PROMPT, "hasOutputParser": True, "options": {}},
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": POS["Generate Follow-up Email"],
            "id": "e4c724e0-ba91-4c26-ba02-253497a84564",
            "name": "Generate Follow-up Email",
            "onError": "continueRegularOutput",
            "notes": "AI email. If it fails, Build Email still sends.",
        }
    )
    add(
        {
            "parameters": {"jsonSchemaExample": '{"subject":"Follow-up","body":"Thank you for your time."}'},
            "type": "@n8n/n8n-nodes-langchain.outputParserStructured",
            "typeVersion": 1.3,
            "position": POS["Structured Output Parser"],
            "id": "60b46b4e-46d5-402d-932b-b4663c167970",
            "name": "Structured Output Parser",
        }
    )
    add(
        {
            "parameters": {"modelName": GEMINI, "options": {}},
            "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
            "typeVersion": 1.1,
            "position": POS["Google Gemini Chat Model"],
            "id": "f4bfe156-691f-4bef-b1e6-1884dd18c0b0",
            "name": "Google Gemini Chat Model",
            "credentials": CREDS,
            "onError": "continueRegularOutput",
        }
    )
    add(
        {
            "parameters": {"promptType": "define", "text": WA_PROMPT, "hasOutputParser": True, "options": {}},
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": POS["Generate WhatsApp Message"],
            "id": "d5700b45-4338-408c-805b-a8790de8ec86",
            "name": "Generate WhatsApp Message",
            "onError": "continueRegularOutput",
            "notes": "AI WhatsApp. If it fails, Ensure WhatsApp Text still sends.",
        }
    )
    add(
        {
            "parameters": {"jsonSchemaExample": '{"message":"Thanks for speaking with us."}'},
            "type": "@n8n/n8n-nodes-langchain.outputParserStructured",
            "typeVersion": 1.3,
            "position": POS["Structured Output Parser1"],
            "id": "d7e7352f-820f-4198-8996-38f54287f635",
            "name": "Structured Output Parser1",
        }
    )
    add(
        {
            "parameters": {"modelName": GEMINI, "options": {}},
            "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
            "typeVersion": 1.1,
            "position": POS["Google Gemini Chat Model1"],
            "id": "d07824ac-eb1a-4272-81a1-447d451c83f6",
            "name": "Google Gemini Chat Model1",
            "credentials": CREDS,
            "onError": "continueRegularOutput",
        }
    )
    add(
        {
            "parameters": {"sessionIdType": "customKey", "sessionKey": "={{ $json.phone }}", "contextWindowLength": 10},
            "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
            "typeVersion": 1.4,
            "position": POS["Simple Memory"],
            "id": "7e2173cf-efcc-4ef8-bd4e-7e6cf114cc61",
            "name": "Simple Memory",
            "notes": "Per-customer memory keyed by phone.",
        }
    )

    nodes = []
    seen = set()
    for n in list(by.values()) + extras:
        if n["name"] in seen:
            continue
        if n.get("type") == "n8n-nodes-base.stickyNote":
            continue
        seen.add(n["name"])
        if n["name"] in POS:
            n["position"] = POS[n["name"]]
        nodes.append(n)

    nodes += [
        {
            "parameters": {
                "content": "## 1. After interested call",
                "width": 1180,
                "height": 300,
                "color": 7,
            },
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-1020, 100],
            "id": "note-call",
            "name": "Note Call",
        },
        {
            "parameters": {
                "content": "## 2. Email (AI then fallback)",
                "width": 1120,
                "height": 220,
                "color": 5,
            },
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [180, -80],
            "id": "note-email",
            "name": "Note Email",
        },
        {
            "parameters": {
                "content": "## 3. WhatsApp (AI then fallback + memory)",
                "width": 1960,
                "height": 340,
                "color": 4,
            },
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [180, 100],
            "id": "note-wa",
            "name": "Note WhatsApp",
        },
        {
            "parameters": {
                "content": "## 4. Customer reply → lookup original lead → same WhatsApp path",
                "width": 1180,
                "height": 220,
                "color": 6,
            },
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-1020, 480],
            "id": "note-reply",
            "name": "Note Reply",
        },
    ]

    wf["nodes"] = nodes
    wf["connections"] = {
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
        "Generate Follow-up Email": {"main": [[]]},
        "Build Email": {"main": [[{"node": "Send Email", "type": "main", "index": 0}]]},
        "Google Gemini Chat Model": {"ai_languageModel": [[{"node": "Generate Follow-up Email", "type": "ai_languageModel", "index": 0}]]},
        "Structured Output Parser": {"ai_outputParser": [[{"node": "Generate Follow-up Email", "type": "ai_outputParser", "index": 0}]]},
        "Lead Payload": {"main": [[{"node": "Generate WhatsApp Message", "type": "main", "index": 0}]]},
        "Generate WhatsApp Message": {"main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]},
        "Ensure WhatsApp Text": {"main": [[{"node": "Prepare Send", "type": "main", "index": 0}]]},
        "Prepare Send": {"main": [[{"node": "If Has WhatsApp Text", "type": "main", "index": 0}]]},
        "If Has WhatsApp Text": {"main": [[{"node": "Send WhatsApp", "type": "main", "index": 0}], []]},
        "Send WhatsApp": {"main": [[{"node": "Record in Aakashvani", "type": "main", "index": 0}]]},
        "Google Gemini Chat Model1": {"ai_languageModel": [[{"node": "Generate WhatsApp Message", "type": "ai_languageModel", "index": 0}]]},
        "Structured Output Parser1": {"ai_outputParser": [[{"node": "Generate WhatsApp Message", "type": "ai_outputParser", "index": 0}]]},
        "Simple Memory": {"ai_memory": [[{"node": "Generate WhatsApp Message", "type": "ai_memory", "index": 0}]]},
        "WhatsApp Trigger": {"main": [[{"node": "Normalize Inbound", "type": "main", "index": 0}]]},
        "Normalize Inbound": {"main": [[{"node": "If Customer Message", "type": "main", "index": 0}]]},
        "If Customer Message": {"main": [[{"node": "Lookup Lead", "type": "main", "index": 0}], []]},
        "Lookup Lead": {"main": [[{"node": "Lead Payload", "type": "main", "index": 0}]]},
    }
    wf["settings"] = {"executionOrder": "v1", "binaryMode": "separate"}
    SRC.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("restored capable clean graph", [n["name"] for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"])


if __name__ == "__main__":
    main()

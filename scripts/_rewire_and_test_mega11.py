"""Rewire Mega_Workflow11: template-first, Gemini on reply only. Then POST a live test."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
WEBHOOK = (
    os.environ.get("N8N_LEAD_WEBHOOK_URL")
    or "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)
PHONE = "+917397867643"
EMAIL = "singhnitant28@gmail.com"
NAME = "Nitant Singh"

LEAD_CONTEXT_JS = r"""
function pick() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v !== undefined && v !== null && String(v).trim() !== '') return v;
  }
  return '';
}
function unwrap(j) {
  if (!j || typeof j !== 'object') return {};
  if (j.lead) return j;
  if (j.body && j.body.lead) return j.body;
  if (typeof j.body === 'string') {
    try { return unwrap(JSON.parse(j.body)); } catch (e) {}
  }
  if (j.body && typeof j.body === 'object') return unwrap(j.body);
  return j;
}
function digits(p) { return String(p || '').replace(/\D/g, ''); }
function e164(p) {
  const raw = String(p || '').trim();
  const d = digits(p);
  if (!d) return '';
  if (raw.startsWith('+')) return '+' + d;
  if (d.length === 10) return '+91' + d;
  if (d.length === 12 && d.startsWith('91')) return '+' + d;
  return '+' + d;
}
const payload = unwrap($input.first().json || {});
const lead = payload.lead || {};
const extraction = payload.extraction || {};
const campaign = payload.campaign || {};
const client = payload.client || {};
const aak = payload.aakashvani || {};
const fallback = payload.fallback || {};
const meta = lead.metadata || {};
const intent = String(pick(extraction.intent_status, payload.qualification && payload.qualification.status, lead.lead_type)).toLowerCase().replace(/[_-]+/g, ' ').trim();
const negative = intent.startsWith('not ') || intent === 'not interested' || intent === 'uninterested';
const interested = payload.interested === true || String(payload.interested) === 'true' || (!negative && (intent === 'interested' || intent === 'hot' || intent === 'warm' || intent === 'qualified'));
const phone = e164(pick(lead.phone, payload.phone));
const email = pick(lead.email, meta.email, payload.email);
return [{ json: {
  name: pick(lead.name, payload.name),
  phone,
  email,
  intent_status: intent,
  interested,
  summary: pick(extraction.summary, extraction.summary),
  bhk_preference: pick(extraction.bhk_preference),
  location_preference: pick(extraction.location_preference),
  budget: pick(extraction.budget),
  campaign_id: pick(campaign.id, payload.campaign_id),
  campaign_name: pick(campaign.name),
  client_id: pick(client.id, payload.client_id),
  client_name: pick(client.name),
  lead_id: pick(lead.id),
  record_url: pick(aak.record_url),
  fallback_whatsapp: pick(fallback.whatsapp && fallback.whatsapp.message, fallback.whatsapp),
  fallback_email_subject: pick(fallback.email && fallback.email.subject),
  fallback_email_body: pick(fallback.email && fallback.email.body),
  flow: 'INITIAL',
} }];
"""

INBOUND_PROMPT = """=You are a WhatsApp sales assistant for {{$json.client_name || "our client"}}.

The customer already received the first WhatsApp template. This is a REPLY.

Customer name: {{$json.name}}
Customer phone: {{$json.phone}}
Latest customer message: {{$json.message}}
Call summary (if any): {{$json.summary}}

Rules:
- Answer only the latest message, using memory of this chat.
- Do not invent prices, inventory, or promises.
- Keep it under 120 words, max 1 emoji.
- If you lack facts, ask one short clarifying question or offer a human callback.
Return ONLY JSON: {"message":""}
"""


def opener():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    op.open(
        urllib.request.Request(
            BASE + "/rest/login",
            data=login,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        ),
        timeout=30,
    )
    return op, {"Accept": "application/json"}


def get_wf(op, headers):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF_ID}", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    return raw.get("data", raw)


def patch_wf(op, headers, wf, nodes, connections):
    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings") or {},
        "staticData": wf.get("staticData"),
        "versionId": vid,
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={**headers, "Content-Type": "application/json", "n8n-version-id": str(vid or "")},
    )
    with op.open(req, timeout=45) as r:
        print("patch", r.status)
    return get_wf(op, headers)


def activate(op, headers):
    wf = get_wf(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with op.open(req, timeout=45) as r:
            data = json.loads(r.read())
            data = data.get("data", data)
            print("activate", r.status, "active", data.get("active") if isinstance(data, dict) else True)
    except urllib.error.HTTPError as e:
        print("activate HTTP", e.code, e.read()[:700].decode("utf-8", "replace"))
    print("final active", get_wf(op, headers).get("active"))


def rewire(wf):
    nodes = list(wf.get("nodes") or [])
    by = {n["name"]: n for n in nodes}

    lc = by["Lead Context"]
    lc["type"] = "n8n-nodes-base.code"
    lc["typeVersion"] = 2
    lc["parameters"] = {"jsCode": LEAD_CONTEXT_JS, "mode": "runOnceForAllItems"}
    lc.pop("credentials", None)

    wa_agent = by["Generate WhatsApp Message"]
    wa_agent["parameters"] = {
        **(wa_agent.get("parameters") or {}),
        "promptType": "define",
        "text": INBOUND_PROMPT,
        "hasOutputParser": True,
    }
    wa_agent["onError"] = "continueRegularOutput"

    by["Send a message"]["onError"] = "continueRegularOutput"

    send_tpl = by["Send template"]
    tp = dict(send_tpl.get("parameters") or {})
    tp["recipientPhoneNumber"] = "={{ $json.phone }}"
    send_tpl["parameters"] = tp
    send_tpl["onError"] = "continueRegularOutput"

    send_msg = by["Send message"]
    sp = dict(send_msg.get("parameters") or {})
    sp["recipientPhoneNumber"] = "={{ $json.phone }}"
    sp["textBody"] = "={{ $json.output.message || $json.message }}"
    send_msg["parameters"] = sp

    by["Edit Fields1"]["parameters"] = {
        "assignments": {
            "assignments": [
                {"id": str(uuid.uuid4()), "name": "name", "value": "={{ $('Edit Fields').item.json.name }}", "type": "string"},
                {"id": str(uuid.uuid4()), "name": "phone", "value": "={{ $('Edit Fields').item.json.phone }}", "type": "string"},
                {
                    "id": str(uuid.uuid4()),
                    "name": "output.message",
                    "value": "={{ $json.output.message || 'Thanks for your message. Our team will continue here.' }}",
                    "type": "string",
                },
            ]
        },
        "options": {},
    }

    if "If Interested" not in by:
        nodes.append(
            {
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": False,
                            "leftValue": "",
                            "typeValidation": "loose",
                            "version": 2,
                        },
                        "conditions": [
                            {
                                "id": "int-flag",
                                "leftValue": "={{ $json.interested }}",
                                "rightValue": True,
                                "operator": {"type": "boolean", "operation": "true"},
                            },
                            {
                                "id": "int-eq",
                                "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                                "rightValue": "interested",
                                "operator": {"type": "string", "operation": "equals"},
                            },
                            {
                                "id": "int-hot",
                                "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                                "rightValue": "hot",
                                "operator": {"type": "string", "operation": "equals"},
                            },
                            {
                                "id": "int-warm",
                                "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                                "rightValue": "warm",
                                "operator": {"type": "string", "operation": "equals"},
                            },
                        ],
                        "combinator": "or",
                    },
                    "options": {},
                },
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-400, 220],
                "id": str(uuid.uuid4()),
                "name": "If Interested",
                "notes": "Exact interested/hot/warm only.",
            }
        )

    connections = {
        "Webhook": {"main": [[{"node": "Lead Context", "type": "main", "index": 0}]]},
        "Lead Context": {"main": [[{"node": "If Interested", "type": "main", "index": 0}]]},
        "If Interested": {
            "main": [
                [
                    {"node": "Add Lead", "type": "main", "index": 0},
                    {"node": "Generate Follow-up Email", "type": "main", "index": 0},
                    {"node": "Send template", "type": "main", "index": 0},
                ],
                [],
            ]
        },
        "Generate Follow-up Email": {"main": [[{"node": "Send a message", "type": "main", "index": 0}]]},
        "Google Gemini Chat Model": {
            "ai_languageModel": [[{"node": "Generate Follow-up Email", "type": "ai_languageModel", "index": 0}]]
        },
        "Structured Output Parser": {
            "ai_outputParser": [[{"node": "Generate Follow-up Email", "type": "ai_outputParser", "index": 0}]]
        },
        "WhatsApp Trigger": {"main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]},
        "Edit Fields": {"main": [[{"node": "If", "type": "main", "index": 0}]]},
        "If": {"main": [[{"node": "Generate WhatsApp Message", "type": "main", "index": 0}], []]},
        "Generate WhatsApp Message": {"main": [[{"node": "Edit Fields1", "type": "main", "index": 0}]]},
        "Google Gemini Chat Model1": {
            "ai_languageModel": [[{"node": "Generate WhatsApp Message", "type": "ai_languageModel", "index": 0}]]
        },
        "Structured Output Parser1": {
            "ai_outputParser": [[{"node": "Generate WhatsApp Message", "type": "ai_outputParser", "index": 0}]]
        },
        "Simple Memory": {
            "ai_memory": [[{"node": "Generate WhatsApp Message", "type": "ai_memory", "index": 0}]]
        },
        "Edit Fields1": {"main": [[{"node": "Send message", "type": "main", "index": 0}]]},
        "Send message": {"main": [[{"node": "HTTP Request1", "type": "main", "index": 0}]]},
        "Send template": {"main": [[{"node": "HTTP Request1", "type": "main", "index": 0}]]},
    }
    return nodes, connections


def post_test():
    payload = {
        "event": "lead_qualified",
        "event_type": "INTERESTED_LEAD",
        "interested": True,
        "event_id": f"manual-test-{int(time.time())}",
        "lead": {
            "name": NAME,
            "phone": PHONE,
            "email": EMAIL,
            "lead_type": "warm",
            "whatsapp_opt_in": True,
        },
        "extraction": {
            "intent_status": "Interested",
            "summary": "Test lead from Aakashvani. Interested after the call. Follow up on WhatsApp and email.",
        },
        "qualification": {"status": "interested", "reason": "manual workflow test"},
        "client": {"name": "BhuvisX"},
        "campaign": {"name": "Mega_Workflow11 live test"},
        "fallback": {
            "whatsapp": {"message": "Hi Nitant, thanks for speaking with us. Reply here and we will help with next steps."},
            "email": {
                "subject": "Thanks for your time",
                "body": "Hi Nitant,\n\nThanks for speaking with us. Reply on WhatsApp and we will continue there.\n",
            },
        },
    }
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("webhook", r.status, round(time.perf_counter() - t0, 3), r.read()[:200])
    except urllib.error.HTTPError as e:
        print("webhook HTTP", e.code, e.read()[:500].decode("utf-8", "replace"))


def latest_exec(op, headers):
    req = urllib.request.Request(BASE + f"/rest/executions?workflowId={WF_ID}&limit=5", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    data = raw.get("data", raw)
    rows = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
    print("execution count", len(rows) if isinstance(rows, list) else type(rows))
    if isinstance(rows, list):
        for row in rows[:5]:
            print(
                "exec",
                row.get("id"),
                "status",
                row.get("status"),
                "finished",
                row.get("finished"),
                "waitTill",
                row.get("waitTill"),
            )


def main() -> None:
    op, headers = opener()
    wf = get_wf(op, headers)
    print("loaded", wf.get("name"), "active", wf.get("active"))
    nodes, connections = rewire(wf)
    wf = patch_wf(op, headers, wf, nodes, connections)
    activate(op, headers)
    print("POST test to", WEBHOOK)
    print("phone", PHONE, "email", EMAIL)
    post_test()
    time.sleep(10)
    latest_exec(op, headers)


if __name__ == "__main__":
    main()

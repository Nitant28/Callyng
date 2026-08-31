"""Patch production Mega_Workflow JSON (no credential secrets)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__live_prod.json")
OUT = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")


def uid() -> str:
    return str(uuid.uuid4())


def assign(name: str, value: str, typ: str = "string") -> dict:
    return {"id": uid(), "name": name, "value": value, "type": typ}


def code_node(name: str, js: str, pos: list[int]) -> dict:
    return {
        "parameters": {"jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def if_node(name: str, conditions: list[dict], combinator: str, pos: list[int]) -> dict:
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": False,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 2,
                },
                "conditions": conditions,
                "combinator": combinator,
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def str_cond(left: str, right: str, op: str) -> dict:
    return {
        "id": uid(),
        "leftValue": left,
        "rightValue": right,
        "operator": {"type": "string", "operation": op},
    }


STORE_JS = r"""
const staticData = $getWorkflowStaticData('global');
staticData.leads = staticData.leads || {};

function digits(p) {
  return String(p || '').replace(/\D/g, '');
}
function keysFor(p) {
  const d = digits(p);
  const out = new Set();
  if (!d) return out;
  out.add(d);
  if (d.length === 10) out.add('91' + d);
  if (d.startsWith('91') && d.length === 12) out.add(d.slice(2));
  if (d.startsWith('0') && d.length === 11) {
    out.add(d.slice(1));
    out.add('91' + d.slice(1));
  }
  return out;
}

const item = $input.first().json;
const ks = keysFor(item.phone);
const record = {
  ...item,
  flow_type: item.flow_type || 'INITIAL_FOLLOWUP',
  lead_found: true,
  stored_at: new Date().toISOString(),
};
for (const k of ks) staticData.leads[k] = record;
return [{ json: { ...record, phone_keys: [...ks] } }];
"""

LOOKUP_JS = r"""
const staticData = $getWorkflowStaticData('global');
const leads = staticData.leads || {};

function digits(p) {
  return String(p || '').replace(/\D/g, '');
}
function candidates(p) {
  const d = digits(p);
  const out = [];
  if (!d) return out;
  out.push(d);
  if (d.length === 10) out.push('91' + d);
  if (d.startsWith('91') && d.length === 12) out.push(d.slice(2));
  if (d.startsWith('0') && d.length === 11) {
    out.push(d.slice(1));
    out.push('91' + d.slice(1));
  }
  return out;
}

const incoming = $input.first().json;
const phone = incoming.phone;
let lead = null;
for (const k of candidates(phone)) {
  if (leads[k]) { lead = leads[k]; break; }
}

if (!lead) {
  return [{ json: {
    ...incoming,
    flow_type: 'CONTINUE_CHAT',
    lead_found: false,
    client_name: incoming.client_name || '',
    summary: '',
  } }];
}

return [{ json: {
  ...lead,
  name: lead.name || incoming.name || '',
  phone: lead.phone || incoming.phone,
  email: lead.email || '',
  message: incoming.message,
  inbound_name: incoming.name || '',
  message_id: incoming.message_id || '',
  flow_type: 'CONTINUE_CHAT',
  lead_found: true,
} }];
"""

NORMALIZE_JS = r"""
function first(v) { return Array.isArray(v) ? v[0] : v; }
const j = $input.first().json;
const value = (j.messages ? j : (j.entry && j.entry[0] && j.entry[0].changes && j.entry[0].changes[0] && j.entry[0].changes[0].value)) || j;
const messages = value.messages || j.messages || [];
const contacts = value.contacts || j.contacts || [];
const statuses = value.statuses || j.statuses || [];
const metadata = value.metadata || j.metadata || {};
const msg = first(messages) || {};
const contact = first(contacts) || {};
const from = msg.from || contact.wa_id || '';
const text = (msg.text && msg.text.body) || (msg.button && msg.button.text) || '';
const display = String(metadata.display_phone_number || '').replace(/\D/g, '');
const fromDigits = String(from).replace(/\D/g, '');
const isStatusOnly = !messages.length && statuses.length;
const isSelf = Boolean(display && fromDigits && (fromDigits === display || fromDigits.endsWith(display) || display.endsWith(fromDigits)));
const skip = Boolean(isStatusOnly || isSelf || !from || !text);
return [{ json: {
  name: (contact.profile && contact.profile.name) || '',
  phone: from,
  message: text,
  message_id: msg.id || '',
  message_type: msg.type || '',
  display_phone_number: metadata.display_phone_number || '',
  is_status_only: Boolean(isStatusOnly),
  is_self: Boolean(isSelf),
  skip,
} }];
"""

WA_PROMPT = """=You are an AI Sales Assistant for Aakashvani.

You communicate with leads on behalf of {{$json.client_name || "our client"}}.

Use ONLY information present in the incoming JSON.
Never invent, assume, or fabricate lead, property, price, or availability details.
Never mention n8n, workflows, memory, JSON, automation, or internal IDs.

MODE is: {{$json.flow_type}}

----------------------------------------
MODE 1: INITIAL FOLLOW-UP
----------------------------------------
If flow_type is "INITIAL_FOLLOWUP" (or legacy "initial_followup"):

This is the first WhatsApp message after an AI voice call.

Available information:
Name: {{$json.name || ""}}
Summary: {{$json.summary || ""}}
Client: {{$json.client_name || ""}}
Industry: {{$json.client_industry || ""}}
BHK: {{$json.bhk_preference || ""}}
Location: {{$json.location_preference || ""}}
Budget: {{$json.budget || ""}}
City: {{$json.lead_city || ""}}

Write a personalized WhatsApp message that:
- thanks them for speaking with the AI assistant
- mentions only information that is actually available
- sounds natural and human
- is 80-150 words
- uses at most 2 emojis
- ends with a clear call-to-action

----------------------------------------
MODE 2: CONTINUE CHAT
----------------------------------------
If flow_type is "CONTINUE_CHAT" (or legacy "inbound_reply"):

This is an inbound WhatsApp reply.
Customer WhatsApp name: {{$json.inbound_name || $json.name || ""}}
Latest customer message: {{$json.message || ""}}

Known lead context (do not ask them to repeat this if present):
Name: {{$json.name || ""}}
Email: {{$json.email || ""}}
City: {{$json.lead_city || ""}}
BHK: {{$json.bhk_preference || ""}}
Location preference: {{$json.location_preference || ""}}
Budget: {{$json.budget || ""}}
Call summary: {{$json.summary || ""}}
Lead found: {{$json.lead_found}}

If lead_found is false, reply professionally and generically. Do not invent a property pitch. Offer human help.

Otherwise continue the conversation using memory plus this context.
- answer the latest message
- do not ask for information already known
- under 120 words
- at most 1 emoji
- if you do not know something, say a human representative can assist

----------------------------------------
OUTPUT
----------------------------------------
Return ONLY valid JSON:
{"message": "your WhatsApp reply"}
"""


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    seen: set[str] = set()
    nodes = []
    for n in wf["nodes"]:
        if n.get("name") in seen:
            continue
        seen.add(n.get("name"))
        nodes.append(n)
    wf["nodes"] = nodes
    by_name = {n["name"]: n for n in nodes}

    lc = by_name["Lead Context"]
    assigns = lc["parameters"]["assignments"]["assignments"]
    fallbacks = {
        "name": "={{ $json.body?.lead?.name ?? $json.lead?.name }}",
        "phone": "={{ $json.body?.lead?.phone ?? $json.lead?.phone }}",
        "lead_type": "={{ $json.body?.lead?.lead_type ?? $json.lead?.lead_type }}",
        "intent_status": "={{ $json.body?.extraction?.intent_status ?? $json.extraction?.intent_status ?? $json.body?.qualification?.status }}",
        "bhk_preference": "={{ $json.body?.extraction?.bhk_preference ?? $json.extraction?.bhk_preference }}",
        "location_preference": "={{ $json.body?.extraction?.location_preference ?? $json.extraction?.location_preference }}",
        "budget": "={{ $json.body?.extraction?.budget ?? $json.extraction?.budget }}",
        "callback_time": "={{ $json.body?.extraction?.callback_time ?? $json.extraction?.callback_time }}",
        "summary": "={{ $json.body?.extraction?.summary ?? $json.extraction?.summary }}",
        "campaign_id": "={{ $json.body?.campaign?.id ?? $json.campaign?.id }}",
        "campaign_name": "={{ $json.body?.campaign?.name ?? $json.campaign?.name }}",
        "client_id": "={{ $json.body?.client?.id ?? $json.client?.id }}",
        "client_name": "={{ $json.body?.client?.name ?? $json.client?.name }}",
        "client_industry": "={{ $json.body?.client?.industry ?? $json.client?.industry }}",
        "recording_url": "={{ $json.body?.call?.recording_url ?? $json.call?.recording_url }}",
        "session_call_id": "={{ $json.body?.call?.session_call_id ?? $json.call?.session_call_id }}",
        "lead_city": "={{ $json.body?.lead?.metadata?.lead_city ?? $json.lead?.metadata?.lead_city }}",
        "email": "={{ $json.body?.lead?.email ?? $json.lead?.email }}",
    }
    for a in assigns:
        if a.get("name") in fallbacks:
            a["value"] = fallbacks[a["name"]]
    have = {a["name"] for a in assigns}
    if "lead_id" not in have:
        assigns.append(assign("lead_id", "={{ $json.body?.lead?.id ?? $json.lead?.id }}"))
    if "event" not in have:
        assigns.append(assign("event", "={{ $json.body?.event ?? $json.event }}"))

    by_name["Generate WhatsApp Message"]["parameters"]["text"] = WA_PROMPT
    by_name["Simple Memory"]["parameters"]["sessionKey"] = "={{ $('Lead Payload').item.json.phone }}"

    gmail = by_name["Send a message"]
    gmail["parameters"]["sendTo"] = "={{ $('Store Lead').item.json.email }}"

    send = by_name["Send message"]
    send["parameters"]["recipientPhoneNumber"] = "={{ $('Prepare Send').item.json.phone_e164 }}"
    send["parameters"]["textBody"] = "={{ $('Prepare Send').item.json.message }}"

    tmpl = by_name["Send template"]
    tmpl["disabled"] = True
    tmpl["parameters"]["recipientPhoneNumber"] = "={{ $('Prepare Send').item.json.phone_e164 }}"

    http = by_name["HTTP Request"]
    http["disabled"] = True

    for obsolete in ("Edit Fields", "If", "Edit Fields1", "If1"):
        by_name[obsolete]["disabled"] = True

    payload_fields = [
        "name", "phone", "email", "lead_id", "lead_type", "intent_status",
        "bhk_preference", "location_preference", "budget", "callback_time",
        "summary", "campaign_id", "campaign_name", "client_id", "client_name",
        "client_industry", "lead_city", "session_call_id", "recording_url",
        "message", "inbound_name", "lead_found", "flow_type",
    ]

    store = code_node("Store Lead", STORE_JS, [-160, 448])
    lookup = code_node("Lookup Lead", LOOKUP_JS, [48, 896])
    normalize = code_node("Normalize Inbound", NORMALIZE_JS, [-560, 896])
    if_interested = if_node(
        "If Interested",
        [
            str_cond("={{ ($json.intent_status || '').toLowerCase() }}", "interested", "contains"),
            str_cond("={{ ($json.intent_status || '').toLowerCase() }}", "hot", "contains"),
            str_cond("={{ ($json.lead_type || '').toLowerCase() }}", "interested", "contains"),
        ],
        "or",
        [32, 448],
    )
    if_email = if_node(
        "If Has Email",
        [str_cond("={{ $json.email }}", "@", "contains")],
        "and",
        [200, 0],
    )
    if_inbound = if_node(
        "If Customer Message",
        [{
            "id": uid(),
            "leftValue": "={{ $json.skip }}",
            "rightValue": True,
            "operator": {"type": "boolean", "operation": "false"},
        }],
        "and",
        [-368, 896],
    )
    lead_payload = {
        "parameters": {
            "assignments": {"assignments": [assign(f, f"={{ $json.{f} }}") for f in payload_fields]},
            "options": {},
        },
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [-64, 640],
        "id": uid(),
        "name": "Lead Payload",
    }
    prepare = {
        "parameters": {
            "assignments": {
                "assignments": [
                    assign("name", "={{ $('Lead Payload').item.json.name }}"),
                    assign("phone", "={{ $('Lead Payload').item.json.phone }}"),
                    assign(
                        "phone_e164",
                        "={{ (()=>{ const p=String($('Lead Payload').item.json.phone||'').trim(); if(!p) return ''; const d=p.replace(/\\D/g,''); if(p.startsWith('+')) return '+'+d; if(d.length===10) return '+91'+d; if(d.length===12 && d.startsWith('91')) return '+'+d; return d? '+'+d : ''; })() }}",
                    ),
                    assign("email", "={{ $('Lead Payload').item.json.email }}"),
                    assign("client_id", "={{ $('Lead Payload').item.json.client_id }}"),
                    assign("flow_type", "={{ $('Lead Payload').item.json.flow_type }}"),
                    assign("message", "={{ $json.output?.message || $json.message || '' }}"),
                ]
            },
            "options": {},
        },
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [320, 784],
        "id": uid(),
        "name": "Prepare Send",
    }
    if_has_msg = if_node(
        "If Has WhatsApp Text",
        [
            str_cond("={{ $json.message }}", "", "notEmpty"),
            str_cond("={{ $json.phone_e164 }}", "", "notEmpty"),
        ],
        "and",
        [544, 784],
    )

    nodes.extend([
        store, lookup, normalize, if_interested, if_email, if_inbound,
        lead_payload, prepare, if_has_msg,
    ])
    wf["nodes"] = nodes

    c = wf["connections"]
    c["Lead Context"] = {"main": [[{"node": "Store Lead", "type": "main", "index": 0}]]}
    c["Store Lead"] = {"main": [[{"node": "If Interested", "type": "main", "index": 0}]]}
    c["If Interested"] = {
        "main": [
            [
                {"node": "Lead Payload", "type": "main", "index": 0},
                {"node": "If Has Email", "type": "main", "index": 0},
            ],
            [],
        ]
    }
    c["If Has Email"] = {
        "main": [[{"node": "Generate Follow-up Email", "type": "main", "index": 0}], []]
    }
    c["WhatsApp Trigger"] = {"main": [[{"node": "Normalize Inbound", "type": "main", "index": 0}]]}
    c["Normalize Inbound"] = {"main": [[{"node": "If Customer Message", "type": "main", "index": 0}]]}
    c["If Customer Message"] = {"main": [[{"node": "Lookup Lead", "type": "main", "index": 0}], []]}
    c["Lookup Lead"] = {"main": [[{"node": "Lead Payload", "type": "main", "index": 0}]]}
    c["Lead Payload"] = {"main": [[{"node": "Generate WhatsApp Message", "type": "main", "index": 0}]]}
    c["Generate WhatsApp Message"] = {"main": [[{"node": "Prepare Send", "type": "main", "index": 0}]]}
    c["Prepare Send"] = {"main": [[{"node": "If Has WhatsApp Text", "type": "main", "index": 0}]]}
    c["If Has WhatsApp Text"] = {
        "main": [[{"node": "Send message", "type": "main", "index": 0}], []]
    }
    c["Send message"] = {"main": [[]]}
    c["Send template"] = {"main": [[]]}

    OUT.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("wrote", OUT, "nodes", len(wf["nodes"]))


if __name__ == "__main__":
    main()

"""Patch Mega_Workflow11: store call requirements, Gemini uses them on reply."""
from __future__ import annotations

import json
import os
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")

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
  if (typeof j.body === 'string') { try { return unwrap(JSON.parse(j.body)); } catch (e) {} }
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
const req = payload.requirements || {};
const campaign = payload.campaign || {};
const client = payload.client || {};
const aak = payload.aakashvani || {};
const fallback = payload.fallback || {};
const fc = payload.first_contact || {};
const meta = lead.metadata || {};
const intent = String(pick(extraction.intent_status, payload.qualification && payload.qualification.status)).toLowerCase().replace(/[_-]+/g, ' ').trim();
const negative = intent.startsWith('not ') || intent === 'not interested';
const interested = payload.interested === true || String(payload.interested) === 'true' || (!negative && (intent === 'interested' || intent === 'hot' || intent === 'warm' || intent === 'qualified'));
const phone = e164(pick(lead.phone, payload.phone));
const bhk = pick(req.bhk, extraction.bhk_preference, extraction.bhk_preference);
const location = pick(req.location, extraction.location_preference, extraction.location_preference, meta.lead_city);
const budget = pick(req.budget, extraction.budget);
const summary = pick(req.summary, extraction.summary, extraction.summary);
const clientName = pick(client.name, payload.client_name);
const requirements_text = pick(req.text, [bhk, location, budget ? ('budget ' + budget) : ''].filter(Boolean).join(', '));
const templateName = pick(fc.template_name, 'hello_world');
const templateLang = pick(fc.language_code, fc.language, 'en');
const params = Array.isArray(fc.parameters) ? fc.parameters.map((x) => String(x || '').trim()).filter(Boolean) : [];
const components = {};
if (params.length) {
  components.component = [{ type: 'body', bodyParameters: { parameter: params.map((text) => ({ type: 'text', text })) } }];
}
return [{ json: {
  name: pick(lead.name, payload.name),
  phone,
  email: pick(lead.email, meta.email, payload.email),
  intent_status: intent,
  interested,
  summary,
  bhk_preference: bhk,
  location_preference: location,
  budget,
  requirements_text,
  campaign_id: pick(campaign.id, payload.campaign_id),
  campaign_name: pick(campaign.name),
  client_id: pick(client.id, payload.client_id),
  client_name: clientName,
  lead_id: pick(lead.id),
  record_url: pick(aak.record_url),
  fallback_whatsapp: pick(fallback.whatsapp && fallback.whatsapp.message, fallback.whatsapp),
  template_name: templateName,
  template_language: templateLang,
  n8n_template_components: components,
  flow: 'INITIAL',
} }];
"""

STORE_JS = r"""
const staticData = $getWorkflowStaticData('global');
staticData.leads = staticData.leads || {};
function digits(p) { return String(p || '').replace(/\D/g, ''); }
function keysFor(p) {
  const d = digits(p);
  const out = new Set();
  if (!d) return out;
  out.add(d);
  if (d.length >= 10) out.add(d.slice(-10));
  if (d.length === 10) out.add('91' + d);
  if (d.startsWith('91') && d.length === 12) out.add(d.slice(2));
  return out;
}
const item = $input.first().json;
const record = { ...item, stored_at: new Date().toISOString() };
for (const k of keysFor(item.phone)) staticData.leads[k] = record;
return [{ json: record }];
"""

LOOKUP_JS = r"""
const staticData = $getWorkflowStaticData('global');
staticData.leads = staticData.leads || {};
function digits(p) { return String(p || '').replace(/\D/g, ''); }
function keysFor(p) {
  const d = digits(p);
  const out = [];
  if (!d) return out;
  out.push(d);
  if (d.length >= 10) out.push(d.slice(-10));
  if (d.length === 10) out.push('91' + d);
  if (d.startsWith('91') && d.length === 12) out.push(d.slice(2));
  return out;
}
const incoming = $input.first().json || {};
let stored = null;
for (const k of keysFor(incoming.phone)) {
  if (staticData.leads[k]) { stored = staticData.leads[k]; break; }
}
return [{ json: { ...(stored || {}), ...incoming, lead_found: Boolean(stored), flow: 'CONTINUE' } }];
"""

INBOUND_PROMPT = """=You are a professional WhatsApp assistant for {{$json.client_name || "our client"}}.
The customer already received the first WhatsApp template after an interested call.

Known requirements from the call (use only these; never invent missing facts):
- Name: {{$json.name}}
- BHK / configuration: {{$json.bhk_preference}}
- Area / location: {{$json.location_preference}}
- Budget: {{$json.budget}}
- Call summary: {{$json.summary}}
- Combined: {{$json.requirements_text}}

Latest customer message:
{{$json.message}}

Rules:
- Answer their latest message using the known requirements.
- You may also help with site visits, callbacks, documents, and general questions.
- Do not invent prices, inventory, project names, or availability.
- If you do not have a fact, say you will confirm with the team.
- Keep it under 120 words, professional, max 1 emoji.
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


def main() -> None:
    op, headers = opener()
    wf = get_wf(op, headers)
    nodes = list(wf.get("nodes") or [])
    by = {n["name"]: n for n in nodes}

    by["Lead Context"]["type"] = "n8n-nodes-base.code"
    by["Lead Context"]["typeVersion"] = 2
    by["Lead Context"]["parameters"] = {"jsCode": LEAD_CONTEXT_JS, "mode": "runOnceForAllItems"}

    by["Generate WhatsApp Message"]["parameters"] = {
        **(by["Generate WhatsApp Message"].get("parameters") or {}),
        "promptType": "define",
        "text": INBOUND_PROMPT,
        "hasOutputParser": True,
    }
    by["Generate WhatsApp Message"]["onError"] = "continueRegularOutput"

    send_tpl = by["Send template"]
    tp = dict(send_tpl.get("parameters") or {})
    tp["recipientPhoneNumber"] = "={{ $json.phone }}"
    tp["template"] = "={{ $json.template_name }}|{{ $json.template_language }}"
    tp["components"] = "={{ $json.n8n_template_components }}"
    send_tpl["parameters"] = tp

    mem = by.get("Simple Memory")
    if mem:
        mp = dict(mem.get("parameters") or {})
        mp["sessionIdType"] = "customKey"
        mp["sessionKey"] = "={{ $json.phone }}"
        mem["parameters"] = mp

    if "Store Lead" not in by:
        nodes.append(
            {
                "parameters": {"jsCode": STORE_JS, "mode": "runOnceForAllItems"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-200, 220],
                "id": str(uuid.uuid4()),
                "name": "Store Lead",
            }
        )
    else:
        by["Store Lead"]["parameters"] = {"jsCode": STORE_JS, "mode": "runOnceForAllItems"}

    if "Lookup Stored Lead" not in by:
        nodes.append(
            {
                "parameters": {"jsCode": LOOKUP_JS, "mode": "runOnceForAllItems"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-200, 560],
                "id": str(uuid.uuid4()),
                "name": "Lookup Stored Lead",
            }
        )
    else:
        by["Lookup Stored Lead"]["parameters"] = {"jsCode": LOOKUP_JS, "mode": "runOnceForAllItems"}

    connections = wf.get("connections") or {}
    connections["Lead Context"] = {"main": [[{"node": "If Interested", "type": "main", "index": 0}]]}
    connections["If Interested"] = {
        "main": [[{"node": "Store Lead", "type": "main", "index": 0}], []]
    }
    connections["Store Lead"] = {
        "main": [
            [
                {"node": "Send template", "type": "main", "index": 0},
                {"node": "Generate Follow-up Email", "type": "main", "index": 0},
            ]
        ]
    }
    connections["WhatsApp Trigger"] = {"main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]}
    connections["Edit Fields"] = {"main": [[{"node": "Lookup Stored Lead", "type": "main", "index": 0}]]}
    connections["Lookup Stored Lead"] = {"main": [[{"node": "If", "type": "main", "index": 0}]]}
    connections["If"] = {"main": [[{"node": "Generate WhatsApp Message", "type": "main", "index": 0}], []]}

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
    wf = get_wf(op, headers)
    vid = wf.get("versionId") or wf.get("versionId")
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF_ID}/activate",
        data=json.dumps({"versionId": vid}).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    with op.open(req, timeout=45) as r:
        print("activate", r.status)
    print("active", get_wf(op, headers).get("active"))
    print("nodes", [n.get("name") for n in get_wf(op, headers).get("nodes") or []])


if __name__ == "__main__":
    main()

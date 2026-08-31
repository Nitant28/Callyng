"""Make Mega_Workflow fast: skip Gemini on first follow-up; webhook returns immediately.

Live timings (#583 / #589):
  Generate WhatsApp Message  180s / 32s
  Gemini Chat Model1 retries 113s + 64s / 22s + 7s
  Generate Follow-up Email    27s / 9s
  Send WhatsApp / Email      <1s each

Those AI nodes are not needed for the first outbound message — backend already
puts deterministic copy on the payload.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)

BASE = os.environ.get("N8N_BASE_URL", "https://n8n.bhuvisx.com").rstrip("/")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")
BACKUP_DIR = Path("fixtures/n8n_exports_local")

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
if (item.public_url) staticData.backend_base = String(item.public_url).replace(/\/$/, '');
if (item.context_url) staticData.context_url = item.context_url;
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
const incoming = $input.first().json || {};
const staticData = $getWorkflowStaticData('global');
staticData.leads = staticData.leads || {};

function digits(p) { return String(p || '').replace(/\D/g, ''); }
function keysFor(p) {
  const d = digits(p);
  const out = new Set();
  if (!d) return out;
  out.add(d);
  if (d.length === 10) out.add('91' + d);
  if (d.startsWith('91') && d.length === 12) out.add(d.slice(2));
  return out;
}
function unmatched(reason) {
  return [{ json: {
    ...incoming,
    flow_type: 'CONTINUE_CHAT',
    lead_found: false,
    lookup_error: reason,
    fallback_whatsapp: incoming.fallback_whatsapp || '',
  } }];
}

const ks = [...keysFor(incoming.phone)];
let cached = null;
for (const k of ks) {
  if (staticData.leads[k]) { cached = staticData.leads[k]; break; }
}

const base = String(staticData.backend_base || incoming.public_url || '').replace(/\/$/, '');
const contextUrl = String(incoming.context_url || staticData.context_url || '');
let resp = null;
if (base || contextUrl) {
  const phone = encodeURIComponent(String(incoming.phone || ''));
  const msg = encodeURIComponent(String(incoming.message || ''));
  let url = contextUrl;
  if (!url && base) {
    url = `${base}/internal/leads/context?phone=${phone}&flow_type=CONTINUE_CHAT&inbound_message=${msg}`;
  } else if (url) {
    const sep = url.includes('?') ? '&' : '?';
    url = `${url}${sep}phone=${phone}&flow_type=CONTINUE_CHAT&inbound_message=${msg}`;
  }
  try {
    resp = await this.helpers.httpRequest({
      method: 'GET',
      url,
      headers: { Accept: 'application/json' },
      json: true,
      timeout: 8000,
    });
  } catch (e) {
    if (cached) {
      return [{ json: { ...cached, ...incoming, flow_type: 'CONTINUE_CHAT', lead_found: true, lookup_error: String(e.message || e) } }];
    }
    return unmatched(String(e.message || e));
  }
}

if (resp && resp.ok && resp.payload) {
  const p = resp.payload;
  const lead = p.lead || {};
  const ext = p.extraction || {};
  const meta = lead.metadata || {};
  const fb = p.fallback || {};
  const aak = p.aakashvani || {};
  if (aak.public_url) staticData.backend_base = String(aak.public_url).replace(/\/$/, '');
  const merged = {
    ...incoming,
    ...p,
    name: lead.name || incoming.name || '',
    phone: lead.phone || incoming.phone,
    email: lead.email || meta.email || '',
    client_id: p.client_id || (p.client && p.client.id),
    client_name: (p.client && p.client.name) || '',
    summary: ext.summary || '',
    bhk_preference: ext.bhk_preference || meta.bhk_preference || '',
    location_preference: ext.location_preference || meta.location_preference || '',
    budget: ext.budget || meta.budget || '',
    lead_city: meta.lead_city || '',
    campaign_id: (p.campaign && p.campaign.id),
    campaign_name: (p.campaign && p.campaign.name) || '',
    lead_id: lead.id,
    flow_type: 'CONTINUE_CHAT',
    lead_found: true,
    message: incoming.message,
    record_url: aak.record_url || '',
    public_url: aak.public_url || '',
    fallback_whatsapp: (fb.reply && fb.reply.message) || (fb.whatsapp && fb.whatsapp.message) || '',
    fallback_email_subject: (fb.email && fb.email.subject) || '',
    fallback_email_body: (fb.email && fb.email.body) || '',
  };
  for (const k of ks) staticData.leads[k] = merged;
  return [{ json: merged }];
}

if (cached) {
  return [{ json: { ...cached, ...incoming, flow_type: 'CONTINUE_CHAT', lead_found: true } }];
}
return unmatched((resp && resp.error) || 'lead_not_found');
"""

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
  if (j.json && typeof j.json === 'object') return unwrap(j.json);
  return j;
}
const payload = unwrap($input.first().json || {});
const lead = payload.lead || {};
const extraction = payload.extraction || {};
const campaign = payload.campaign || {};
const client = payload.client || {};
const call = payload.call || {};
const meta = lead.metadata || {};
const aak = payload.aakashvani || {};
const follow = payload.follow_up || {};
const qualification = payload.qualification || {};
const fb = payload.fallback || {};
const rawIntent = String(pick(extraction.intent_status, extraction.intent_status, qualification.status, lead.lead_type)).toLowerCase();
const negative = /not[\s_]?interest|unqualified|\bcold\b/.test(rawIntent);
const interested = payload.interested === true
  || String(payload.interested) === 'true'
  || (!negative && /\b(hot|warm|qualified|interested)\b/.test(rawIntent));
return [{ json: {
  name: pick(lead.name),
  phone: pick(lead.phone),
  email: pick(lead.email, meta.email),
  lead_type: pick(lead.lead_type),
  intent_status: pick(extraction.intent_status, qualification.status),
  bhk_preference: pick(extraction.bhk_preference),
  location_preference: pick(extraction.location_preference),
  budget: pick(extraction.budget),
  callback_time: pick(extraction.callback_time),
  summary: pick(extraction.summary),
  campaign_id: pick(campaign.id, payload.campaign_id),
  campaign_name: pick(campaign.name),
  client_id: pick(client.id, payload.client_id),
  client_name: pick(client.name),
  client_industry: pick(client.industry),
  recording_url: pick(call.recording_url),
  session_call_id: pick(call.session_call_id),
  lead_city: pick(meta.lead_city, lead.lead_city),
  lead_id: pick(lead.id),
  event: pick(payload.event),
  event_type: pick(payload.event_type),
  flow_type: pick(payload.flow_type, 'INITIAL_FOLLOWUP'),
  record_url: pick(aak.record_url),
  context_url: pick(aak.context_url),
  public_url: pick(aak.public_url),
  idempotency_key: pick(follow.idempotency_key),
  interested: Boolean(interested),
  fallback_whatsapp: pick(fb.whatsapp && fb.whatsapp.message, fb.whatsapp),
  fallback_email_subject: pick(fb.email && fb.email.subject, fb.email_subject),
  fallback_email_body: pick(fb.email && fb.email.body, fb.email_body),
  fallback_inbound_whatsapp: pick(fb.reply && fb.reply.message, fb.inbound_whatsapp),
} }];
"""

ENSURE_WA_JS = r"""
function parseOut(v) {
  if (v === undefined || v === null) return {};
  if (typeof v === 'object') return v;
  if (typeof v === 'string') {
    const s = v.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
    try { return JSON.parse(s); } catch (e) { return { message: v }; }
  }
  return {};
}
function from(name) {
  try { return $(name).first().json || {}; } catch (e) { return {}; }
}
const ai = $input.first().json || {};
const src = Object.assign({}, from('Lead Payload'), from('Lead Payload'), from('If Continue Chat'), from('If Continue Chat'));
const mode = String(src.flow_type || '').trim().toUpperCase();
const isContinue = mode === 'CONTINUE_CHAT' || mode === 'INBOUND_REPLY';
const parsed = parseOut(ai.output !== undefined ? ai.output : (ai.text !== undefined ? ai.text : ai.response));
let raw = String((parsed && parsed.message) || '').trim();
const inbound = String(src.message || '').trim();
if (raw && inbound && raw === inbound) raw = '';
if (/gemini|n8n|quota|traceback|undefined|api key|service unavailable/i.test(raw)) raw = '';
const fb = String((isContinue ? src.fallback_inbound_whatsapp : src.fallback_whatsapp) || src.fallback_whatsapp || '').trim();
const name = src.name || 'there';
const client = src.client_name || 'our team';
const about = [src.bhk_preference, src.location_preference || src.lead_city].filter(Boolean).join(' in ');
let message = raw || fb;
if (!message && isContinue) {
  message = 'Hi ' + name + ', thanks for your message. A specialist from ' + client + ' will continue here shortly.';
}
if (!message) {
  message = 'Hi ' + name + '! Thanks for speaking with ' + client + (about ? ' about ' + about : '') + '. Reply here and we will help with the next steps.';
}
return [{ json: { ...src, ...ai, output: { message }, message, ai_generated: Boolean(raw) } }];
"""

BUILD_EMAIL_JS = r"""
function parseOut(v) {
  if (v === undefined || v === null) return {};
  if (typeof v === 'object') return v;
  if (typeof v === 'string') {
    const s = v.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
    try { return JSON.parse(s); } catch (e) { return { body: v }; }
  }
  return {};
}
const incoming = $input.first().json || {};
let src = {};
try { src = $('If Has Email').first().json || {}; } catch (e) { src = incoming; }
const base = { ...src, ...incoming };
const aiOut = parseOut(incoming.output !== undefined ? incoming.output : incoming);
const name = base.name || 'there';
const client = base.client_name || 'our team';
const summary = base.summary || '';
const about = [base.bhk_preference, base.location_preference || base.lead_city, base.budget ? ('budget ' + base.budget) : ''].filter(Boolean).join(', ');
let subject = String((aiOut && aiOut.subject) || '').trim();
let body = String((aiOut && aiOut.body) || '').trim();
if (/gemini|n8n|quota|traceback|undefined|api key/i.test(subject + body)) { subject = ''; body = ''; }
subject = subject || String(base.fallback_email_subject || '').trim() || ('Follow-up from ' + client);
body = body || String(base.fallback_email_body || '').trim() || [
  'Hi ' + name + ',',
  '',
  'Thank you for speaking with us' + (about ? ' about ' + about : '') + '.',
  summary ? ('Call summary: ' + summary) : '',
  'A representative will contact you shortly. You can also reply to our WhatsApp message.',
  '',
  'Regards,',
  client,
].filter(Boolean).join('\n');
return [{ json: { ...base, output: { subject, body }, email: base.email, ai_generated: false } }];
"""


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def get_workflow(op):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF}", headers={"Accept": "application/json"})
    with op.open(req, timeout=60) as r:
        wf = json.loads(r.read())
    return wf.get("data", wf)


def patch_workflow(op, wf, nodes, connections):
    payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings") or {},
        "staticData": wf.get("staticData"),
        "versionId": wf.get("versionId"),
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "n8n-version-id": str(wf.get("versionId") or ""),
        },
    )
    with op.open(req, timeout=60) as r:
        saved = json.loads(r.read())
        return saved.get("data", saved)


def set_code(node, js):
    node["type"] = "n8n-nodes-base.code"
    node["typeVersion"] = 2
    node["parameters"] = {"jsCode": js.strip() + "\n", "mode": "runOnceForAllItems"}
    node["onError"] = "continueRegularOutput"
    node["alwaysOutputData"] = True


def main() -> None:
    op = login()
    wf = get_workflow(op)
    nodes = wf["nodes"]
    conns = wf["connections"]
    by = {n["name"]: n for n in nodes}

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"Mega_Workflow__backup_{stamp}.json"
    backup.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("backup ->", backup)

    # Webhook must ACK immediately so the call system never waits on Gemini/Gmail/WA.
    wh = by["Webhook"]
    opts = wh.setdefault("parameters", {}).setdefault("options", {})
    opts["responseMode"] = "onReceived"

    def name(*cands):
        for n in cands:
            if n in by:
                return n
        raise KeyError(f"none of {cands} in {sorted(by)}")

    set_code(by[name("Lead Context", "Lead Context")], LEAD_CONTEXT_JS)
    set_code(by[name("Store Lead", "Store Lead")], STORE_JS)
    set_code(by[name("Lookup Lead", "Lookup Lead")], LOOKUP_JS)
    set_code(by[name("Ensure WhatsApp Text", "Ensure WhatsApp Text")], ENSURE_WA_JS)
    set_code(by[name("Build Email", "Build Email")], BUILD_EMAIL_JS)

    if "If Continue Chat" not in by:
        pos = by["Lead Payload"].get("position") or [224, 224]
        cont = {
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
                            "id": "continue-chat",
                            "leftValue": "={{ ($json.flow_type || '').toUpperCase() }}",
                            "rightValue": "CONTINUE_CHAT",
                            "operator": {"type": "string", "operation": "contains"},
                        }
                    ],
                    "combinator": "or",
                },
                "options": {},
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [pos[0] + 220, pos[1]],
            "id": str(uuid.uuid4()),
            "name": "If Continue Chat",
            "notes": "true = inbound reply (Gemini). false = first follow-up (deterministic, no Gemini).",
        }
        nodes.append(cont)
        by["If Continue Chat"] = cont
        print("added If Continue Chat")

    payload_name = name("Lead Payload", "Lead Payload")
    wa_agent = name("Generate WhatsApp Message", "Generate WhatsApp Message")
    ensure_name = name("Ensure WhatsApp Text", "Ensure WhatsApp Text")
    if_email = name("If Has Email", "If Has Email")
    email_agent = name("Generate Follow-up Email", "Generate Follow-up Email")

    # First follow-up: skip both Gemini agents.
    conns[payload_name]["main"] = [[{"node": "If Continue Chat", "type": "main", "index": 0}]]
    conns["If Continue Chat"] = {
        "main": [
            [{"node": wa_agent, "type": "main", "index": 0}],
            [{"node": ensure_name, "type": "main", "index": 0}],
        ]
    }
    conns[if_email]["main"][0] = [{"node": "Build Email", "type": "main", "index": 0}]

    by[email_agent]["disabled"] = True
    if "Google Gemini Chat Model" in by:
        by["Google Gemini Chat Model"]["disabled"] = True

    for n in (wa_agent, "Google Gemini Chat Model1"):
        if n not in by:
            continue
        node = by[n]
        node["retryOnFail"] = False
        node["maxTries"] = 1
        node["onError"] = "continueRegularOutput"
        node["alwaysOutputData"] = True

    saved = patch_workflow(op, wf, nodes, conns)
    print("published", saved.get("versionId"), "active", saved.get("active"))
    print("webhook responseMode=onReceived")
    print("INITIAL: Lead Payload -> If Continue Chat [false] -> Ensure WhatsApp Text (no Gemini)")
    print("INBOUND: If Continue Chat [true] -> Generate WhatsApp Message -> Ensure WhatsApp Text")
    print("email: If Has Email -> Build Email (Gemini email agent disabled)")


if __name__ == "__main__":
    main()

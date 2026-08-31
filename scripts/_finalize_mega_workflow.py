"""Publish the production Mega_Workflow follow-up graph.

Fixes:
  * Email AI is wired: If Has Email → Generate Follow-up Email → Build Email → Send Email
  * WhatsApp AI uses backend fallback when Gemini fails
  * Lookup Lead never reads $env (n8n task runner blocks it)
  * Gemini model is a plain string n8n 1.1 can call
  * Record URL comes from the Aakashvani payload
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

BASE = os.environ.get("N8N_BASE_URL", "https://n8n.bhuvisx.com").rstrip("/")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")
MODEL = os.environ.get("N8N_GEMINI_MODEL", "models/gemini-3.7-flash")
BACKUP_DIR = Path("fixtures/n8n_exports_local")


def _backend_base() -> str:
    return (
        (os.getenv("AAKASHVANI_PUBLIC_URL") or "").strip().rstrip("/")
        or (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    )


def _record_token() -> str:
    secret = (
        (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
        or (os.getenv("ADMIN_API_KEY") or "").strip()
    )
    if not secret:
        return ""
    return hashlib.sha256(f"record::{secret}".encode("utf-8")).hexdigest()


_record_token = _record_token


LOOKUP_JS = r"""
const incoming = $input.first().json || {};
const BACKEND_BASE = __BACKEND_BASE__;
const TOKEN = __TOKEN__;

function fallback(reason) {
  return [{ json: {
    ...incoming,
    flow_type: 'CONTINUE_CHAT',
    lead_found: false,
    lookup_error: reason,
    message: incoming.message,
    phone: incoming.phone,
    name: incoming.name || '',
    fallback_whatsapp: incoming.fallback_whatsapp || incoming.fallback_inbound_whatsapp || '',
  } }];
}

if (!BACKEND_BASE) {
  return fallback('backend_url_not_configured');
}

const phone = encodeURIComponent(String(incoming.phone || ''));
const msg = encodeURIComponent(String(incoming.message || ''));
const qs = [`phone=${phone}`, 'flow_type=CONTINUE_CHAT', `inbound_message=${msg}`];
if (TOKEN) qs.push('token=' + encodeURIComponent(TOKEN));
const url = `${BACKEND_BASE}/internal/leads/context?${qs.join('&')}`;

let resp;
try {
  resp = await this.helpers.httpRequest({
    method: 'GET',
    url,
    headers: { Accept: 'application/json' },
    json: true,
    timeout: 15000,
  });
} catch (e) {
  return fallback(String(e.message || e));
}

if (!resp || !resp.ok || !resp.payload) {
  return fallback((resp && resp.error) || 'lead_not_found');
}

const p = resp.payload;
const lead = p.lead || {};
const ext = p.extraction || {};
const meta = lead.metadata || {};
const fb = p.fallback || {};
const aak = p.aakashvani || {};

return [{ json: {
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
  campaign_id: (p.campaign && p.campaign.id) || (p.metadata && p.metadata.campaign_id),
  campaign_name: (p.campaign && p.campaign.name) || '',
  lead_id: lead.id,
  flow_type: 'CONTINUE_CHAT',
  lead_found: true,
  message: incoming.message,
  inbound_name: incoming.name || '',
  message_id: incoming.message_id || '',
  record_url: aak.record_url || incoming.record_url || '',
  fallback_whatsapp: (fb.reply && fb.reply.message) || (fb.whatsapp && fb.whatsapp.message) || incoming.fallback_whatsapp || '',
  fallback_email_subject: (fb.email && fb.email.subject) || '',
  fallback_email_body: (fb.email && fb.email.body) || '',
} }];
""".replace("__BACKEND_BASE__", json.dumps(_backend_base())).replace("__TOKEN__", json.dumps(_record_token()))


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
const interested = payload.interested === true
  || String(payload.interested) === 'true'
  || String(pick(extraction.intent_status, qualification.status, lead.lead_type, payload.event_type)).toLowerCase().match(/interest|hot|warm|qualified/);
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
  idempotency_key: pick(follow.idempotency_key),
  interested: Boolean(interested),
  first_contact: payload.first_contact || {},
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
const ai = $input.first().json || {};
const src = $('Lead Payload').first().json || {};
const mode = String(src.flow_type || src.flow_type || '').trim().toUpperCase();
const isContinue = mode === 'CONTINUE_CHAT' || mode === 'INBOUND_REPLY';
const parsed = parseOut(ai.output !== undefined ? ai.output : (ai.text !== undefined ? ai.text : ai.response));
let raw = String((parsed && parsed.message) || '').trim();
const inbound = String(src.message || '').trim();
if (raw && inbound && raw === inbound) raw = '';
const banned = /gemini|n8n|quota|traceback|undefined|null|api key/i;
if (banned.test(raw)) raw = '';
const fb = String(
  (isContinue ? src.fallback_inbound_whatsapp : src.fallback_whatsapp)
  || src.fallback_whatsapp
  || ''
).trim();
const name = src.name || 'there';
const client = src.client_name || 'our team';
const bhk = src.bhk_preference || '';
const loc = src.location_preference || src.lead_city || '';
const about = [bhk, loc].filter(Boolean).join(' in ');
let message = raw || fb;
if (!message && isContinue) {
  message = 'Hi ' + name + ', thanks for your message. A specialist from ' + client + ' will continue this conversation here shortly.';
}
if (!message) {
  message = 'Hi ' + name + '! Thanks for speaking with ' + client + (about ? ' about ' + about : '') + '. Reply on this WhatsApp chat and we will help with the next steps.';
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
const ai = $input.first().json || {};
let src = {};
try { src = $('If Has Email').first().json || {}; } catch (e) { src = {}; }
const base = { ...src, ...ai };
const aiOut = parseOut(ai.output !== undefined ? ai.output : (ai.text !== undefined ? ai.text : ai.response));
const name = base.name || 'there';
const client = base.client_name || 'our team';
const summary = base.summary || '';
const about = [base.bhk_preference, base.location_preference || base.lead_city, base.budget ? ('budget ' + base.budget) : ''].filter(Boolean).join(', ');
const banned = /gemini|n8n|quota|traceback|undefined|api key/i;
let subject = String((aiOut && aiOut.subject) || '').trim();
let body = String((aiOut && aiOut.body) || '').trim();
if (banned.test(subject) || banned.test(body)) { subject = ''; body = ''; }
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
return [{ json: { ...base, output: { subject, body }, email: base.email, ai_generated: Boolean(aiOut.subject && aiOut.body) } }];
"""

PREPARE_SEND_JS = r"""
const src = $('Lead Payload').first().json || {};
const upstream = $input.first().json || {};
const p = String(src.phone || upstream.phone || '').trim();
const d = p.replace(/\D/g, '');
let e164 = '';
if (p.startsWith('+')) e164 = '+' + d;
else if (d.length === 10) e164 = '+91' + d;
else if (d.length === 12 && d.startsWith('91')) e164 = '+' + d;
else if (d) e164 = '+' + d;
const message = String((upstream.output && upstream.output.message) || upstream.message || '').trim();
return [{ json: {
  ...src,
  phone_e164: e164,
  message,
  customer_name: src.name || '',
  record_url: src.record_url || '',
  ai_generated: Boolean(upstream.ai_generated),
} }];
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
    try:
        with op.open(req, timeout=60) as r:
            saved = json.loads(r.read())
            return saved.get("data", saved)
    except urllib.error.HTTPError as e:
        print("PATCH failed:", e.code, e.read()[:1500].decode("utf-8", "replace"))
        raise


def _set_code(node, js, mode="runOnceForAllItems"):
    node["type"] = "n8n-nodes-base.code"
    node["typeVersion"] = 2
    node["parameters"] = {
        "jsCode": js.strip() + "\n",
        "jsCode": js.strip() + "\n",
        "mode": mode,
    }
    node["onError"] = "continueRegularOutput"
    node["alwaysOutputData"] = True


def _gemini(node):
    params = node.setdefault("parameters", {})
    params["modelName"] = MODEL
    params["options"] = {"temperature": 0.4, "maxOutputTokens": 8192}
    node["retryOnFail"] = True
    node["maxTries"] = 3
    node["waitBetweenTries"] = 2000
    node.pop("onError", None)


def _node(by, *names):
    for name in names:
        if name in by:
            return by[name]
    raise KeyError(f"none of {names} exist; have {sorted(by)}")


def main() -> None:
    print("backend_base:", _backend_base() or "(empty — inbound lookup will fallback)")
    op = login()
    wf = get_workflow(op)
    nodes = wf["nodes"]
    conns = wf["connections"]
    by = {n["name"]: n for n in nodes}
    print("nodes:", sorted(by))

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"Mega_Workflow__backup_{stamp}.json"
    backup.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("backup ->", backup)

    _set_code(_node(by, "Lead Context", "Lead Context"), LEAD_CONTEXT_JS)
    _set_code(_node(by, "Lookup Lead", "Lookup Lead"), LOOKUP_JS)
    _set_code(_node(by, "Ensure WhatsApp Text", "Ensure WhatsApp Text"), ENSURE_WA_JS)
    _set_code(_node(by, "Build Email", "Build Email"), BUILD_EMAIL_JS)
    _set_code(_node(by, "Prepare Send", "Prepare Send"), PREPARE_SEND_JS)

    for name in list(by):
        if "Gemini" in name or "gemini" in (by[name].get("type") or ""):
            _gemini(by[name])

    email_agent = _node(by, "Generate Follow-up Email", "Generate Follow-up Email")
    wa_agent = _node(by, "Generate WhatsApp Message", "Generate WhatsApp Message")
    email_agent.setdefault("parameters", {}).setdefault("options", {})["systemMessage"] = (
        "You write short, warm, factual follow-up emails. Use only provided facts. Never invent prices. JSON only."
    )
    wa_agent.setdefault("parameters", {}).setdefault("options", {})["systemMessage"] = (
        "You write concise WhatsApp messages. Use only provided facts. Never invent prices. JSON only."
    )
    for agent in (email_agent, wa_agent):
        agent["parameters"]["hasOutputParser"] = True
        agent["onError"] = "continueRegularOutput"
        agent["retryOnFail"] = True
        agent["maxTries"] = 2
        agent["waitBetweenTries"] = 2000
        agent["alwaysOutputData"] = True

    rec = by.get("Record in Aakashvani") or by.get("Record in Aakashvani")
    if rec:
        rec["onError"] = "continueRegularOutput"
        rec["alwaysOutputData"] = True

    if_email = "If Has Email" if "If Has Email" in by else "If Has Email"
    email_name = email_agent["name"]
    conns[if_email]["main"][0] = [{"node": email_name, "type": "main", "index": 0}]
    conns.setdefault(email_name, {})["main"] = [[{"node": "Build Email", "type": "main", "index": 0}]]

    saved = patch_workflow(op, wf, nodes, conns)
    print("published", saved.get("versionId"), "active", saved.get("active"))
    print(f"email path: {if_email} -> {email_name} -> Build Email")
    print("lookup: baked backend URL, no $env")


if __name__ == "__main__":
    main()

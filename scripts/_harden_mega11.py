"""Make Mega_Workflow11 fail-open: always finish, always attempt WhatsApp + email."""
from __future__ import annotations

import json
import os
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
PHONE_ID = "1184950391375570"

LEAD_JS = r"""
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
function e164(p) {
  const raw = String(p || '').trim();
  const d = String(p || '').replace(/\D/g, '');
  if (!d) return '';
  if (raw.startsWith('+')) return '+' + d;
  if (d.length === 10) return '+91' + d;
  if (d.length === 12 && d.startsWith('91')) return '+' + d;
  return '+' + d;
}
try {
  const payload = unwrap($input.first().json || {});
  const lead = payload.lead || {};
  const extraction = payload.extraction || {};
  const req = payload.requirements || {};
  const campaign = payload.campaign || {};
  const client = payload.client || {};
  const fallback = payload.fallback || {};
  const fc = payload.first_contact || {};
  const meta = lead.metadata || {};
  const intent = String(pick(
    extraction.intent_status, extraction.intent_status,
    payload.qualification && payload.qualification.status, lead.lead_type
  )).toLowerCase().replace(/[_-]+/g, ' ').trim();
  const negative = intent.startsWith('not ') || intent === 'not interested';
  const interested = payload.interested === true || payload.interested === true
    || String(payload.interested) === 'true' || String(payload.interested) === 'true'
    || (!negative && (intent === 'interested' || intent === 'hot' || intent === 'warm' || intent === 'qualified'));
  const name = pick(lead.name, payload.name, 'there');
  const first = name.split(' ')[0] || 'there';
  const clientName = pick(client.name, payload.client_name, 'our team');
  const phone = e164(pick(lead.phone, payload.phone));
  const bhk = pick(req.bhk, extraction.bhk_preference, extraction.bhk_preference);
  const location = pick(req.location, extraction.location_preference, extraction.location_preference, meta.lead_city);
  const budget = pick(req.budget, extraction.budget);
  const bits = [bhk, location, budget ? ('budget ' + budget) : ''].filter(Boolean).join(', ');
  const professional = pick(
    fallback.whatsapp && fallback.whatsapp.message, fallback.whatsapp,
    bits
      ? ('Hi ' + first + ', thank you for speaking with ' + clientName + '. We noted your interest in ' + bits + '. Reply here and we will help with the next step.')
      : ('Hi ' + first + ', thank you for speaking with ' + clientName + '. We are following up on your call. Reply here with any questions.')
  );
  return [{ json: {
    name, phone, email: pick(lead.email, meta.email, payload.email),
    intent_status: intent, interested,
    summary: pick(req.summary, extraction.summary, extraction.summary),
    bhk_preference: bhk, location_preference: location, budget,
    requirements_text: pick(req.text, bits),
    campaign_id: pick(campaign.id, payload.campaign_id),
    campaign_name: pick(campaign.name),
    client_id: pick(client.id, payload.client_id),
    client_name: clientName,
    lead_id: pick(lead.id),
    message: professional,
    output: { message: professional },
    fallback_whatsapp: professional,
    template_name: 'hello_world',
    template_language: 'en',
    record_url: pick(payload.aakashvani && payload.aakashvani.record_url),
    flow: 'INITIAL',
  } }];
} catch (e) {
  return [{ json: { interested: false, phone: '', message: '', error: String(e) } }];
}
"""

STORE_JS = r"""
try {
  const staticData = $getWorkflowStaticData('global');
  staticData.leads = staticData.leads || {};
  const item = $input.first().json || {};
  const d = String(item.phone || '').replace(/\D/g, '');
  if (d) {
    const rec = { ...item, stored_at: new Date().toISOString() };
    staticData.leads[d] = rec;
    if (d.length >= 10) staticData.leads[d.slice(-10)] = rec;
    if (d.length === 10) staticData.leads['91' + d] = rec;
  }
  return [{ json: item }];
} catch (e) {
  return [{ json: $input.first().json || {} }];
}
"""

LOOKUP_JS = r"""
try {
  const staticData = $getWorkflowStaticData('global');
  staticData.leads = staticData.leads || {};
  const incoming = $input.first().json || {};
  const d = String(incoming.phone || '').replace(/\D/g, '');
  const keys = [d, d.slice(-10), d.length === 10 ? '91' + d : '', (d.startsWith('91') && d.length === 12) ? d.slice(2) : ''].filter(Boolean);
  let stored = null;
  for (const k of keys) { if (staticData.leads[k]) { stored = staticData.leads[k]; break; } }
  return [{ json: { ...(stored || {}), ...incoming, lead_found: Boolean(stored), flow: 'CONTINUE' } }];
} catch (e) {
  return [{ json: { ...($input.first().json || {}), lead_found: false } }];
}
"""

ENSURE_JS = r"""
const j = $input.first().json || {};
const inbound = $('Edit Fields').isExecuted ? ($('Edit Fields').item.json || {}) : {};
const phone = j.phone || inbound.phone || '';
const name = j.name || inbound.name || '';
const msg = (j.output && j.output.message) || j.message || j.fallback_whatsapp
  || ('Hi ' + (name.split(' ')[0] || 'there') + ', thanks for your message. We will help you from here.');
return [{ json: { ...j, name, phone, message: msg, output: { message: msg } } }];
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


def fail_open(node: dict) -> None:
    node["onError"] = "continueRegularOutput"
    node["continueOnFail"] = True
    node["retryOnFail"] = True
    node["maxTries"] = 2
    node["waitBetweenTries"] = 1000


def main() -> None:
    op, headers = opener()
    wf = get_wf(op, headers)
    by = {n["name"]: n for n in wf.get("nodes") or []}

    by["Lead Context"]["type"] = "n8n-nodes-base.code"
    by["Lead Context"]["typeVersion"] = 2
    by["Lead Context"]["parameters"] = {"jsCode": LEAD_JS, "mode": "runOnceForAllItems"}

    by["Store Lead"]["parameters"] = {"jsCode": STORE_JS, "mode": "runOnceForAllItems"}
    by["Lookup Stored Lead"]["parameters"] = {"jsCode": LOOKUP_JS, "mode": "runOnceForAllItems"}

    by["Edit Fields1"]["type"] = "n8n-nodes-base.code"
    by["Edit Fields1"]["typeVersion"] = 2
    by["Edit Fields1"]["parameters"] = {"jsCode": ENSURE_JS, "mode": "runOnceForAllItems"}
    by["Edit Fields1"]["onError"] = "continueRegularOutput"

    send_msg = by["Send message"]
    send_msg["parameters"] = {
        "operation": "send",
        "phoneNumberId": PHONE_ID,
        "recipientPhoneNumber": "={{ $json.phone }}",
        "textBody": "={{ $json.message || $json.output.message || $json.fallback_whatsapp }}",
        "additionalFields": {},
    }
    fail_open(send_msg)

    send_tpl = by["Send template"]
    send_tpl["parameters"] = {
        "phoneNumberId": PHONE_ID,
        "recipientPhoneNumber": "={{ $json.phone }}",
        "template": "hello_world|en",
    }
    fail_open(send_tpl)

    fail_open(by["Send a message"])
    gp = dict(by["Send a message"].get("parameters") or {})
    gp["sendTo"] = "={{ $('Lead Context').item.json.email }}"
    by["Send a message"]["parameters"] = gp

    fail_open(by["Generate Follow-up Email"])
    fail_open(by["Generate WhatsApp Message"])
    fail_open(by["HTTP Request1"])
    http = dict(by["HTTP Request1"].get("parameters") or {})
    http["url"] = "={{ $json.record_url || $('Lead Context').item.json.record_url || 'https://httpbin.org/status/204' }}"
    http["method"] = "POST"
    http["sendBody"] = True
    http["specifyBody"] = "json"
    http["onError"] = "continueRegularOutput"
    by["HTTP Request1"]["parameters"] = http

    wa = by["Generate WhatsApp Message"]
    wp = dict(wa.get("parameters") or {})
    wp["promptType"] = "define"
    wp["text"] = (
        "=You are a professional WhatsApp assistant for {{$json.client_name || \"our client\"}}.\n"
        "Known call requirements (do not invent missing facts):\n"
        "- Name: {{$json.name}}\n- BHK: {{$json.bhk_preference}}\n- Area: {{$json.location_preference}}\n"
        "- Budget: {{$json.budget}}\n- Summary: {{$json.summary}}\n"
        "Latest customer message: {{$json.message}}\n"
        "Answer using those requirements. No invented prices. Under 120 words.\n"
        "Return ONLY JSON: {\"message\":\"\"}"
    )
    wp["hasOutputParser"] = True
    wa["parameters"] = wp

    settings = dict(wf.get("settings") or {})
    settings["executionOrder"] = "v1"
    settings["saveDataErrorExecution"] = "all"
    settings["saveDataSuccessExecution"] = "all"
    settings["saveManualExecutions"] = True

    con = wf.get("connections") or {}
    con["Store Lead"] = {
        "main": [
            [
                {"node": "Send template", "type": "main", "index": 0},
                {"node": "Send message", "type": "main", "index": 0},
                {"node": "Generate Follow-up Email", "type": "main", "index": 0},
            ]
        ]
    }
    con["Send template"] = {"main": [[{"node": "HTTP Request1", "type": "main", "index": 0}]]}
    con["Send message"] = {"main": [[{"node": "HTTP Request1", "type": "main", "index": 0}]]}

    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": con,
        "settings": settings,
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
    wf = get_wf(op, headers)
    print("active", wf.get("active"))
    tpl = next(n for n in wf["nodes"] if n["name"] == "Send template")
    print("template", (tpl.get("parameters") or {}).get("template"), "onError", tpl.get("onError"))
    print("store fans out", (wf.get("connections") or {}).get("Store Lead"))


if __name__ == "__main__":
    main()

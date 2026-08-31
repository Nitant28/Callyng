"""Fix Mega_Workflow11 WhatsApp delivery: professional text, then working template."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BASE = (os.environ.get("N8N_BASE_URL") or "https://n8n.bhuvisx.com").rstrip("/")
WF_ID = os.environ.get("N8N_WF_ID", "eaiNw08OYt6Y7cJD")
WEBHOOK = os.environ.get("N8N_LEAD_WEBHOOK_URL") or (
    BASE + "/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)

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
const fallback = payload.fallback || {};
const fc = payload.first_contact || {};
const meta = lead.metadata || {};
const intent = String(pick(
  extraction.intent_status, extraction.intent_status,
  payload.qualification && payload.qualification.status
)).toLowerCase().replace(/[_-]+/g, ' ').trim();
const negative = intent.startsWith('not ') || intent === 'not interested';
const interested = payload.interested === true || payload.interested === true
  || String(payload.interested) === 'true' || String(payload.interested) === 'true'
  || (!negative && (intent === 'interested' || intent === 'hot' || intent === 'warm' || intent === 'qualified'));
const phone = e164(pick(lead.phone, payload.phone));
const name = pick(lead.name, payload.name);
const first = (name || 'there').split(' ')[0];
const clientName = pick(client.name, payload.client_name, 'our team');
const bhk = pick(req.bhk, extraction.bhk_preference, extraction.bhk_preference);
const location = pick(req.location, extraction.location_preference, extraction.location_preference, meta.lead_city, meta.city);
const budget = pick(req.budget, extraction.budget);
const summary = pick(req.summary, extraction.summary, extraction.summary);
const bits = [bhk, location, budget ? ('budget ' + budget) : ''].filter(Boolean).join(', ');
const professional = pick(
  fallback.whatsapp && fallback.whatsapp.message,
  fallback.whatsapp,
  bits
    ? ('Hi ' + first + ', thank you for speaking with ' + clientName + '. We noted your interest in ' + bits + '. Reply here and we will help with the next step.')
    : ('Hi ' + first + ', thank you for speaking with ' + clientName + '. We are following up on your call. Reply here with any questions.')
);
const templateName = pick(fc.template_name, 'hello_world');
const customTemplate = Boolean(fc.template_name) && String(fc.template_name) !== 'hello_world';
return [{ json: {
  name, phone,
  email: pick(lead.email, meta.email, payload.email),
  intent_status: intent,
  interested,
  summary, bhk_preference: bhk, location_preference: location, budget,
  requirements_text: pick(req.text, bits),
  campaign_id: pick(campaign.id, payload.campaign_id),
  campaign_name: pick(campaign.name),
  client_id: pick(client.id, payload.client_id),
  client_name: clientName,
  lead_id: pick(lead.id),
  message: professional,
  output: { message: professional },
  fallback_whatsapp: professional,
  template_name: templateName,
  template_language: pick(fc.language_code, fc.language, 'en'),
  use_custom_template: customTemplate,
  record_url: pick(payload.aakashvani && payload.aakashvani.record_url),
  flow: 'INITIAL',
} }];
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
    by = {n["name"]: n for n in wf.get("nodes") or []}

    by["Lead Context"]["type"] = "n8n-nodes-base.code"
    by["Lead Context"]["typeVersion"] = 2
    by["Lead Context"]["parameters"] = {"jsCode": LEAD_CONTEXT_JS, "mode": "runOnceForAllItems"}

    send_msg = by["Send message"]
    sp = dict(send_msg.get("parameters") or {})
    sp["operation"] = "send"
    sp["recipientPhoneNumber"] = "={{ $json.phone }}"
    sp["textBody"] = "={{ $json.message || $json.output.message || $json.fallback_whatsapp }}"
    send_msg["parameters"] = sp
    send_msg.pop("onError", None)

    send_tpl = by["Send template"]
    tp = {
        "phoneNumberId": (send_tpl.get("parameters") or {}).get("phoneNumberId") or "1184950391375570",
        "recipientPhoneNumber": "={{ $json.phone }}",
        "template": "hello_world|en",
    }
    send_tpl["parameters"] = tp
    send_tpl["onError"] = "continueRegularOutput"

    gmail = by["Send a message"]
    gp = dict(gmail.get("parameters") or {})
    gp["sendTo"] = "={{ $('Lead Context').item.json.email }}"
    gmail["parameters"] = gp

    con = wf.get("connections") or {}
    con["Store Lead"] = {
        "main": [
            [
                {"node": "Send message", "type": "main", "index": 0},
                {"node": "Generate Follow-up Email", "type": "main", "index": 0},
                {"node": "Send template", "type": "main", "index": 0},
            ]
        ]
    }
    # Inbound replies still go Generate WhatsApp -> Edit Fields1 -> Send message.
    # First contact also hits Send message with professional copy already on the item.

    vid = wf.get("versionId") or wf.get("versionId")
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": con,
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
        print("activate", r.status, "active", get_wf(op, headers).get("active"))

    body = Path(__file__).resolve().parents[1].joinpath("test-webhook.json").read_bytes()
    req = urllib.request.Request(
        WEBHOOK, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        print("webhook", r.status, r.read()[:160])
    time.sleep(10)
    req = urllib.request.Request(BASE + f"/rest/executions?workflowId={WF_ID}&limit=1", headers=headers)
    with op.open(req, timeout=30) as r:
        raw = json.loads(r.read())
    data = raw.get("data", raw)
    rows = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
    eid = str((rows[0] or {}).get("id")) if rows else ""
    print("latest", eid, (rows[0] or {}).get("status") if rows else None)
    if eid:
        det = json.loads(
            op.open(
                urllib.request.Request(
                    BASE + f"/rest/executions/{eid}?includeData=true",
                    headers={"Accept": "application/json"},
                ),
                timeout=30,
            ).read()
        ).get("data", {})
        blob = det.get("data") if isinstance(det.get("data"), str) else json.dumps(det.get("data"))
        print("132001" in blob, "template error" if "(#132001)" in blob else "no template error")
        import re
        rd = re.search(r'\{(\"(?:Webhook|WhatsApp Trigger)\"[^}]{0,900})\}', blob)
        print("nodes", rd.group(1) if rd else "n/a")


if __name__ == "__main__":
    main()

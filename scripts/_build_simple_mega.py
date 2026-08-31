"""Build a simplified Mega_Workflow: template on first contact, text on reply."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures/n8n_exports_local/Mega_Workflow__patched.json"

WA_CRED = {"whatsAppApi": {"id": "rVE6HlTGG4Q5kSJT", "name": "WhatsApp account"}}
WA_TRIGGER_CRED = {
    "whatsAppTriggerApi": {"id": "xqkpxxwjQWPnJSKP", "name": "WhatsApp OAuth account"}
}
PHONE_NUMBER_ID = "1184950391375570"
WEBHOOK_ID = "5879f520-d9b9-4dc9-ba95-3392c2f30792"

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
const fc = payload.first_contact || {};
const fallback = payload.fallback || {};
return [{
  json: {
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
    lead_city: pick(meta.lead_city),
    lead_id: pick(lead.id),
    event: pick(payload.event),
    record_url: pick(aak.record_url),
    context_url: pick(aak.context_url),
    fallback_whatsapp: pick(fallback.whatsapp && fallback.whatsapp.message, fallback.whatsapp),
    fallback_inbound_whatsapp: pick(fallback.reply && fallback.reply.message, fallback.inbound_whatsapp),
    conversation_text: pick(payload.conversation_text),
    idempotency_key: pick(follow.idempotency_key),
    interested: payload.interested === true || String(payload.interested) === 'true',
    first_contact_mode: pick(fc.mode),
    template_name: pick(fc.template_name),
    template_language: pick(fc.language_code, 'en'),
    template_parameters: Array.isArray(fc.parameters) ? fc.parameters : [],
    template_phone_number_id: pick(fc.phone_number_id),
    first_contact_can_send: fc.can_send === true,
    flow_type: 'INITIAL_FOLLOWUP',
  }
}];
"""

STORE_LEAD_JS = r"""
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
  if (d.startsWith('0') && d.length === 11) {
    out.add(d.slice(1));
    out.add('91' + d.slice(1));
  }
  return out;
}
const item = $input.first().json;
const record = { ...item, stored_at: new Date().toISOString() };
for (const k of keysFor(item.phone)) staticData.leads[k] = record;
return [{ json: record }];
"""

PREPARE_OUTBOUND_JS = r"""
const j = $input.first().json || {};
const p = String(j.phone || '').trim();
const d = p.replace(/\D/g, '');
let e164 = '';
if (p.startsWith('+')) e164 = '+' + d;
else if (d.length === 10) e164 = '+91' + d;
else if (d.length === 12 && d.startsWith('91')) e164 = '+' + d;
else if (d) e164 = '+' + d;
const templateName = String(j.template_name || '').trim();
const lang = String(j.template_language || 'en').trim() || 'en';
const params = Array.isArray(j.template_parameters)
  ? j.template_parameters.map((x) => String(x || '').trim()).filter(Boolean)
  : [];
const useTemplate = Boolean(templateName);
const message = String(j.fallback_whatsapp || '').trim();
const useText = !useTemplate && Boolean(message);
const components = {};
if (params.length) {
  components.component = [{
    type: 'body',
    bodyParameters: {
      parameter: params.map((text) => ({ type: 'text', text })),
    },
  }];
}
return [{ json: {
  ...j,
  phone_e164: e164,
  message,
  use_template: Boolean(useTemplate && e164),
  use_text: Boolean(useText && e164),
  template: templateName ? (templateName + '|' + lang) : '',
  template_name: templateName,
  template_language: lang,
  phone_number_id: j.template_phone_number_id || '1184950391375570',
  n8n_template_components: components,
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
  flow_type: 'CONTINUE_CHAT',
} }];
"""

LOOKUP_STORED_JS = r"""
const staticData = $getWorkflowStaticData('global');
staticData.leads = staticData.leads || {};
function digits(p) { return String(p || '').replace(/\D/g, ''); }
function keysFor(p) {
  const d = digits(p);
  const out = [];
  if (!d) return out;
  out.push(d);
  if (d.length === 10) out.push('91' + d);
  if (d.startsWith('91') && d.length === 12) out.push(d.slice(2));
  return out;
}
const incoming = $input.first().json || {};
let stored = null;
for (const k of keysFor(incoming.phone)) {
  if (staticData.leads[k]) { stored = staticData.leads[k]; break; }
}
return [{ json: { ...(stored || {}), ...incoming, lead_found: Boolean(stored), flow_type: 'CONTINUE_CHAT' } }];
"""

PREPARE_REPLY_JS = r"""
const j = $input.first().json || {};
const p = String(j.phone || '').trim();
const d = p.replace(/\D/g, '');
let e164 = '';
if (p.startsWith('+')) e164 = '+' + d;
else if (d.length === 10) e164 = '+91' + d;
else if (d.length === 12 && d.startsWith('91')) e164 = '+' + d;
else if (d) e164 = '+' + d;
const name = j.name || 'there';
const client = j.client_name || 'our team';
const message = String(j.fallback_inbound_whatsapp || '').trim()
  || ('Hi ' + name + ', thanks for your message. ' + client + ' will continue here on WhatsApp.');
return [{ json: {
  ...j,
  phone_e164: e164,
  message,
  use_template: false,
  use_text: Boolean(e164 && message),
} }];
"""


def if_bool(node_id, name, left, op, notes, pos):
    return {
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
                        "id": node_id + "-c1",
                        "leftValue": left,
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": op},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos,
        "id": node_id,
        "name": name,
        "notes": notes,
    }


def if_or_interested():
    return {
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
                        "id": "int-hot-eq",
                        "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                        "rightValue": "hot",
                        "operator": {"type": "string", "operation": "equals"},
                    },
                    {
                        "id": "int-warm-eq",
                        "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                        "rightValue": "warm",
                        "operator": {"type": "string", "operation": "equals"},
                    },
                    {
                        "id": "int-interested-eq",
                        "leftValue": "={{ ($json.intent_status || '').toLowerCase().trim() }}",
                        "rightValue": "interested",
                        "operator": {"type": "string", "operation": "equals"},
                    },
                ],
                "combinator": "or",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [-80, 220],
        "id": "b89154bb-57f1-409a-8fc5-35ce2ca42177",
        "name": "If Interested",
        "notes": "Exact interested/hot/warm only. \"not interested\" does not match.",
    }


def code(node_id, name, js, pos, notes=""):
    return {
        "parameters": {"jsCode": js, "mode": "runOnceForAllItems"},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "id": node_id,
        "name": name,
        "notes": notes,
    }


def conn(*names):
    return {"main": [[{"node": n, "type": "main", "index": 0} for n in names]]}


def if_conn(true_node, false_node=None):
    true_branch = [{"node": true_node, "type": "main", "index": 0}] if true_node else []
    false_branch = [{"node": false_node, "type": "main", "index": 0}] if false_node else []
    return {"main": [true_branch, false_branch]}


def main() -> None:
    nodes = [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": WEBHOOK_ID,
                "options": {},
                "responseMode": "onReceived",
            },
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [-980, 220],
            "id": "e53146de-80f1-48fe-84b2-91d89872ec20",
            "name": "Webhook",
            "webhookId": WEBHOOK_ID,
            "notes": "Aakashvani lead_qualified. Respond immediately. First contact uses a WhatsApp template.",
        },
        code(
            "301abc52-a75a-4d9c-8415-50d63813461e",
            "Lead Context",
            LEAD_CONTEXT_JS,
            [-700, 220],
            "Unwrap payload and first_contact template fields.",
        ),
        code(
            "11f5db37-f136-4e0a-af6c-1199247e2267",
            "Store Lead",
            STORE_LEAD_JS,
            [-400, 220],
            "Remember lead by phone so WhatsApp replies can find it.",
        ),
        if_or_interested(),
        code(
            "prep-outbound-0001-0002-0003-0004",
            "Prepare Outbound",
            PREPARE_OUTBOUND_JS,
            [180, 220],
            "Template for first contact; text only if no template is configured.",
        ),
        if_bool(
            "if-send-template-0001-0002-0003",
            "If Send Template",
            "={{ $json.use_template }}",
            "true",
            "First conversation: Meta template.",
            [460, 220],
        ),
        {
            "parameters": {
                "operation": "sendTemplate",
                "phoneNumberId": "={{ $json.phone_number_id }}",
                "recipientPhoneNumber": "={{ $json.phone_e164 }}",
                "template": "={{ $json.template }}",
                "components": "={{ $json.n8n_template_components }}",
            },
            "type": "n8n-nodes-base.whatsApp",
            "typeVersion": 1.1,
            "position": [760, 120],
            "id": "send-template-0001-0002-0003-0004",
            "name": "Send Template",
            "credentials": WA_CRED,
            "notes": "Initial WhatsApp template. Recipient and template name come from the lead payload.",
        },
        if_bool(
            "c8043b41-db49-4094-b3e9-500d00da3063",
            "If Has WhatsApp Text",
            "={{ $json.use_text }}",
            "true",
            "Session text after a customer reply, or text fallback if no template.",
            [760, 360],
        ),
        {
            "parameters": {
                "operation": "send",
                "phoneNumberId": PHONE_NUMBER_ID,
                "recipientPhoneNumber": "={{ $json.phone_e164 }}",
                "textBody": "={{ $json.message }}",
                "additionalFields": {},
            },
            "type": "n8n-nodes-base.whatsApp",
            "typeVersion": 1.1,
            "position": [1040, 360],
            "id": "96837a25-2da6-41fb-9bb0-b7286b8588f4",
            "name": "Send WhatsApp",
            "webhookId": "adcbaf72-48ab-433e-8fb7-95cc9e1c5343",
            "credentials": WA_CRED,
            "notes": "Session message after the customer replies.",
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $('Prepare Outbound').first().json.record_url }}",
                "sendHeaders": True,
                "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ client_id: $('Prepare Outbound').first().json.client_id, to_phone: $('Prepare Outbound').first().json.phone_e164, text: $('Prepare Outbound').first().json.template_name || $('Prepare Outbound').first().json.message, lead_id: $('Prepare Outbound').first().json.lead_id || null, campaign_id: $('Prepare Outbound').first().json.campaign_id, customer_name: $('Prepare Outbound').first().json.name, idempotency_key: $('Prepare Outbound').first().json.idempotency_key, direction: 'outgoing', status: 'sent' }) }}",
                "options": {"timeout": 5000},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [1040, 120],
            "id": "record-template-0001-0002-0003-0004",
            "name": "Record Template",
            "notes": "Best-effort write of the template send.",
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.record_url : $('Prepare Outbound').first().json.record_url }}",
                "sendHeaders": True,
                "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ client_id: $json.client_id || ($('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.client_id : $('Prepare Outbound').first().json.client_id), to_phone: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.phone_e164 : $('Prepare Outbound').first().json.phone_e164, text: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.message : $('Prepare Outbound').first().json.message, lead_id: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.lead_id : $('Prepare Outbound').first().json.lead_id, campaign_id: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.campaign_id : $('Prepare Outbound').first().json.campaign_id, customer_name: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.name : $('Prepare Outbound').first().json.name, idempotency_key: $('Prepare Reply').isExecuted ? $('Prepare Reply').first().json.idempotency_key : $('Prepare Outbound').first().json.idempotency_key, direction: 'outgoing', status: 'sent' }) }}",
                "options": {"timeout": 5000},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [1320, 360],
            "id": "9d78116c-69c6-4cbe-bebf-9f40b0fdea3b",
            "name": "Record Message",
            "notes": "Best-effort write of the session WhatsApp text.",
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {"updates": ["messages"], "options": {}},
            "type": "n8n-nodes-base.whatsAppTrigger",
            "typeVersion": 1,
            "position": [-980, 560],
            "id": "2be149ff-0d20-4570-87e1-e0cf463cacb6",
            "name": "WhatsApp Trigger",
            "webhookId": "34664d3e-4506-4e47-9aca-17653d2ec0a6",
            "credentials": WA_TRIGGER_CRED,
            "notes": "Fires when a customer replies on WhatsApp.",
        },
        code(
            "44643a47-a0f3-4449-b2c2-39ba92b15ec5",
            "Normalize Inbound",
            NORMALIZE_JS,
            [-700, 560],
            "Keep customer text; drop receipts and self echoes.",
        ),
        if_bool(
            "ef010640-6335-4b0f-b3cd-bb7d62c12d40",
            "If Customer Message",
            "={{ $json.skip }}",
            "false",
            "Drop delivery receipts, empty messages, and our own echoes.",
            [-400, 560],
        ),
        code(
            "lookup-stored-0001-0002-0003-0004",
            "Lookup Stored Lead",
            LOOKUP_STORED_JS,
            [-80, 560],
            "Match the inbound phone to the lead stored from the webhook.",
        ),
        code(
            "prep-reply-0001-0002-0003-0004",
            "Prepare Reply",
            PREPARE_REPLY_JS,
            [180, 560],
            "Session reply text. No Gemini.",
        ),
    ]

    connections = {
        "Webhook": conn("Lead Context"),
        "Lead Context": conn("Store Lead"),
        "Store Lead": conn("If Interested"),
        "If Interested": if_conn("Prepare Outbound"),
        "Prepare Outbound": conn("If Send Template"),
        "If Send Template": if_conn("Send Template", "If Has WhatsApp Text"),
        "Send Template": conn("Record Template"),
        "If Has WhatsApp Text": if_conn("Send WhatsApp"),
        "Send WhatsApp": conn("Record Message"),
        "WhatsApp Trigger": conn("Normalize Inbound"),
        "Normalize Inbound": conn("If Customer Message"),
        "If Customer Message": if_conn("Lookup Stored Lead"),
        "Lookup Stored Lead": conn("Prepare Reply"),
        "Prepare Reply": conn("If Has WhatsApp Text"),
    }

    workflow = {
        "name": "Mega_Workflow",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "binaryMode": "separate"},
    }
    OUT.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} nodes={len(nodes)}")


if __name__ == "__main__":
    main()

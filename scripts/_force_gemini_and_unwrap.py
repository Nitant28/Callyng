"""Force Gemini 2.5-flash via resource locator + robust webhook unwrap."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

GEMINI = {
    "__rl": True,
    "mode": "id",
    "value": "models/gemini-2.5-flash",
}

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
  if (typeof j.body === 'string') {
    try { return unwrap(JSON.parse(j.body)); } catch (e) {}
  }
  if (j.body && typeof j.body === 'object') return unwrap(j.body);
  if (j.json && typeof j.json === 'object') return unwrap(j.json);
  return j;
}
const payload = unwrap($input.first().json || {});
const lead = leadOr(payload);
function leadOr(p) { return p.lead || {}; }
const extraction = payload.extraction || {};
const campaign = payload.campaign || {};
const client = payload.client || {};
const call = payload.call || {};
const meta = lead.metadata || {};
const aak = payload.aakashvani || {};
const follow = payload.follow_up || {};
const qualification = payload.qualification || {};
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
    idempotency_key: pick(follow.idempotency_key),
    interested: payload.interested === true || String(payload.interested) === 'true',
    debug_keys: Object.keys(payload),
  }
}];
"""


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in wf["nodes"]}
    lc = by["Lead Context"]
    lc["type"] = "n8n-nodes-base.code"
    lc["typeVersion"] = 2
    lc["parameters"] = {"jsCode": LEAD_JS, "mode": "runOnceForAllItems"}

    for name in ("Google Gemini Chat Model", "Google Gemini Chat Model1"):
        node = by[name]
        params = node.setdefault("parameters", {})
        params["modelName"] = GEMINI
        params["options"] = params.get("options") or {}
        node["onError"] = "continueRegularOutput"

    by["Generate Follow-up Email"]["onError"] = "continueRegularOutput"
    by["Generate WhatsApp Message"]["onError"] = "continueRegularOutput"

    interested = by["If Interested"]
    interested["parameters"]["conditions"]["conditions"] = [
        {
            "id": "int-hot",
            "leftValue": "={{ ($json.intent_status || '').toLowerCase() }}",
            "rightValue": "hot",
            "operator": {"type": "string", "operation": "contains"},
        },
        {
            "id": "int-interested-status",
            "leftValue": "={{ ($json.intent_status || '').toLowerCase() }}",
            "rightValue": "interested",
            "operator": {"type": "string", "operation": "contains"},
        },
        {
            "id": "int-lead-type",
            "leftValue": "={{ ($json.lead_type || '').toLowerCase() }}",
            "rightValue": "interested",
            "operator": {"type": "string", "operation": "contains"},
        },
        {
            "id": "int-event",
            "leftValue": "={{ ($json.event || '').toLowerCase() }}",
            "rightValue": "lead_qualified",
            "operator": {"type": "string", "operation": "equals"},
        },
        {
            "id": "int-flag",
            "leftValue": "={{ $json.interested }}",
            "rightValue": True,
            "operator": {"type": "boolean", "operation": "true"},
        },
    ]
    interested["parameters"]["conditions"]["combinator"] = "or"

    SRC.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("forced gemini-2.5-flash + unwrap")


if __name__ == "__main__":
    main()

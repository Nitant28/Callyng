"""Fix empty Lead Context mapping and dead Gemini model."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

LEAD_JS = r"""
function pick() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v !== undefined && v !== null && String(v).trim() !== '') return v;
  }
  return '';
}
const raw = $input.first().json || {};
const body = (raw.body && typeof raw.body === 'object') ? raw.body : raw;
const lead = body.lead || {};
const extraction = body.extraction || {};
const campaign = body.campaign || {};
const client = body.client || {};
const call = body.call || {};
const meta = lead.metadata || {};
const aak = body.aakashvani || {};
const follow = body.follow_up || {};
const qualification = body.qualification || {};
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
    campaign_id: pick(campaign.id, body.campaign_id),
    campaign_name: pick(campaign.name),
    client_id: pick(client.id, body.client_id),
    client_name: pick(client.name),
    client_industry: pick(client.industry),
    recording_url: pick(call.recording_url),
    session_call_id: pick(call.session_call_id),
    lead_city: pick(meta.lead_city, lead.lead_city),
    lead_id: pick(lead.id),
    event: pick(body.event),
    record_url: pick(aak.record_url),
    idempotency_key: pick(follow.idempotency_key),
    interested: body.interested === true || body.interested === 'true',
  }
}];
"""


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in wf["nodes"]}

    lc = by["Lead Context"]
    lc["type"] = "n8n-nodes-base.code"
    lc["typeVersion"] = 2
    lc["parameters"] = {"jsCode": LEAD_JS}
    lc["notes"] = "Unwrap webhook body in code so lead/phone/email always populate."

    for name in ("Google Gemini Chat Model", "Google Gemini Chat Model1"):
        if name in by:
            by[name]["parameters"]["modelName"] = "models/gemini-2.5-flash"

    if "Generate Follow-up Email" in by:
        by["Generate Follow-up Email"]["onError"] = "continueRegularOutput"
    if "Generate WhatsApp Message" in by:
        by["Generate WhatsApp Message"]["onError"] = "continueRegularOutput"

    # Email only if address actually contains @
    email_if = by["If Has Email"]
    email_if["parameters"]["conditions"]["options"]["typeValidation"] = "loose"
    email_if["parameters"]["conditions"]["conditions"] = [
        {
            "id": "email-not-empty-001",
            "leftValue": "={{ $json.email }}",
            "rightValue": "",
            "operator": {"type": "string", "operation": "notEmpty"},
        },
        {
            "id": "email-has-at-002",
            "leftValue": "={{ $json.email }}",
            "rightValue": "@",
            "operator": {"type": "string", "operation": "contains"},
        },
    ]
    email_if["parameters"]["conditions"]["combinator"] = "and"

    SRC.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("lead-context code + gemini-2.5-flash")


if __name__ == "__main__":
    main()

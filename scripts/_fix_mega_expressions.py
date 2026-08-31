"""Fix Mega_Workflow expressions and re-enable Aakashvani persist HTTP node."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")
OUT = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

LC_MAP = {
    "name": "={{ $json.body.lead.name || $json.lead.name }}",
    "phone": "={{ $json.body.lead.phone || $json.lead.phone }}",
    "lead_type": "={{ $json.body.lead.lead_type || $json.lead.lead_type }}",
    "intent_status": "={{ $json.body.extraction.intent_status || $json.extraction.intent_status || $json.body.qualification.status }}",
    "bhk_preference": "={{ $json.body.extraction.bhk_preference || $json.extraction.bhk_preference }}",
    "location_preference": "={{ $json.body.extraction.location_preference || $json.extraction.location_preference }}",
    "budget": "={{ $json.body.extraction.budget || $json.extraction.budget }}",
    "callback_time": "={{ $json.body.extraction.callback_time || $json.extraction.callback_time }}",
    "summary": "={{ $json.body.extraction.summary || $json.extraction.summary }}",
    "campaign_id": "={{ $json.body.campaign.id || $json.campaign.id }}",
    "campaign_name": "={{ $json.body.campaign.name || $json.campaign.name }}",
    "client_id": "={{ $json.body.client.id || $json.client.id || $json.body.client_id || $json.client_id }}",
    "client_name": "={{ $json.body.client.name || $json.client.name }}",
    "client_industry": "={{ $json.body.client.industry || $json.client.industry }}",
    "recording_url": "={{ $json.body.call.recording_url || $json.call.recording_url }}",
    "session_call_id": "={{ $json.body.call.session_call_id || $json.call.session_call_id }}",
    "lead_city": "={{ $json.body.lead.metadata.lead_city || $json.lead.metadata.lead_city }}",
    "email": "={{ $json.body.lead.email || $json.lead.email }}",
    "lead_id": "={{ $json.body.lead.id || $json.lead.id }}",
    "event": "={{ $json.body.event || $json.event }}",
    "record_url": "={{ $json.body.aakashvani.record_url || $json.aakashvani.record_url }}",
    "idempotency_key": "={{ $json.body.follow_up.idempotency_key || $json.follow_up.idempotency_key }}",
}


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    seen = set()
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
    have = {a["name"] for a in assigns}
    for a in assigns:
        if a.get("name") in LC_MAP:
            a["value"] = LC_MAP[a["name"]]
    if "record_url" not in have:
        assigns.append(
            {
                "id": "b7c1e0d2-4a11-4c8f-9e2a-recordurl0001",
                "name": "record_url",
                "value": LC_MAP["record_url"],
                "type": "string",
            }
        )

    lp = by_name["Lead Payload"]
    for a in lp["parameters"]["assignments"]["assignments"]:
        val = a.get("value") or ""
        if val.startswith("={ ") and not val.startswith("={{ "):
            a["value"] = "={{" + val[2:]
        if a.get("name") == "flow_type":
            a["value"] = "={{ $json.flow_type }}"
    lp_names = {a["name"] for a in lp["parameters"]["assignments"]["assignments"]}
    extra = [
        ("record_url", "={{ $json.record_url }}"),
        ("lead_id", "={{ $json.lead_id }}"),
        ("campaign_id", "={{ $json.campaign_id }}"),
        ("idempotency_key", "={{ $json.idempotency_key }}"),
    ]
    for name, value in extra:
        if name not in lp_names:
            lp["parameters"]["assignments"]["assignments"].append(
                {"id": f"lp-{name}", "name": name, "value": value, "type": "string"}
            )

    ps = by_name["Prepare Send"]
    for a in ps["parameters"]["assignments"]["assignments"]:
        if a.get("name") == "message":
            a["value"] = "={{ ($json.output && $json.output.message) ? $json.output.message : $json.message }}"
        if a.get("name") == "phone_e164":
            a["value"] = (
                "={{ (()=>{ const p=String($('Lead Payload').item.json.phone||'').trim(); "
                "if(!p) return ''; const d=p.replace(/\\D/g,''); "
                "if(p.startsWith('+')) return '+'+d; "
                "if(d.length===10) return '+91'+d; "
                "if(d.length===12 && d.startsWith('91')) return '+'+d; "
                "return d? '+'+d : ''; })() }}"
            )
    ps_names = {a["name"] for a in ps["parameters"]["assignments"]["assignments"]}
    for name, value in (
        ("client_id", "={{ $('Lead Payload').item.json.client_id }}"),
        ("lead_id", "={{ $('Lead Payload').item.json.lead_id }}"),
        ("campaign_id", "={{ $('Lead Payload').item.json.campaign_id }}"),
        ("record_url", "={{ $('Lead Payload').item.json.record_url }}"),
        ("idempotency_key", "={{ $('Lead Payload').item.json.idempotency_key }}"),
        ("customer_name", "={{ $('Lead Payload').item.json.name }}"),
    ):
        if name not in ps_names:
            ps["parameters"]["assignments"]["assignments"].append(
                {"id": f"ps-{name}", "name": name, "value": value, "type": "string"}
            )

    http = by_name["HTTP Request"]
    http["disabled"] = False
    http["parameters"]["url"] = "={{ $('Prepare Send').first().json.record_url }}"
    http["parameters"]["jsonBody"] = (
        "={{ JSON.stringify({ "
        "client_id: $('Prepare Send').first().json.client_id, "
        "to_phone: $('Prepare Send').first().json.phone_e164, "
        "text: $('Prepare Send').first().json.message, "
        "lead_id: $('Prepare Send').first().json.lead_id || null, "
        "campaign_id: $('Prepare Send').first().json.campaign_id, "
        "customer_name: $('Prepare Send').first().json.customer_name, "
        "idempotency_key: $('Prepare Send').first().json.idempotency_key, "
        "direction: 'outgoing', "
        "status: 'sent' "
        "}) }}"
    )
    # Keep existing X-Admin-Key header; n8n env can override later.

    wf["connections"]["Send message"] = {
        "main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]
    }

    OUT.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("patched expressions + HTTP persist", OUT)


if __name__ == "__main__":
    main()

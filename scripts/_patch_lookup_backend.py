"""Patch Mega_Workflow Lookup Lead to fetch context from AakashVani backend."""

from __future__ import annotations

import json
from pathlib import Path

PATCH = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

LOOKUP_JS = r"""
const incoming = $input.first().json;
const base = ($env.AAKASHVANI_PUBLIC_URL || $env.NGROK_URL || '').replace(/\/$/, '');
const adminKey = $env.AAKASHVANI_ADMIN_KEY || $env.ADMIN_API_KEY || '';

function fallback(reason) {
  return [{
    json: {
      ...incoming,
      flow_type: 'CONTINUE_CHAT',
      lead_found: false,
      lookup_error: reason,
      message: incoming.message,
      phone: incoming.phone,
      name: incoming.name || '',
    },
  }];
}

if (!base || !adminKey) {
  return fallback('backend_env_missing');
}

const phone = encodeURIComponent(String(incoming.phone || ''));
const msg = encodeURIComponent(String(incoming.message || ''));
const url = `${base}/internal/leads/context?phone=${phone}&flow_type=CONTINUE_CHAT&inbound_message=${msg}`;

let resp;
try {
  resp = await this.helpers.httpRequest({
    method: 'GET',
    url,
    headers: { 'X-Admin-Key': adminKey, 'Accept': 'application/json' },
    json: true,
    timeout: 15000,
  });
} catch (e) {
  return fallback(String(e.message || e));
}

if (!resp || !resp.ok || !resp.payload) {
  return fallback(resp?.error || 'lead_not_found');
}

const p = resp.payload;
const lead = p.lead || {};
const ext = p.extraction || {};
const meta = lead.metadata || {};

return [{
  json: {
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
    campaign_id: (p.campaign && p.campaign.id) || p.metadata?.campaign_id,
    campaign_name: (p.campaign && p.campaign.name) || '',
    lead_id: lead.id,
    flow_type: 'CONTINUE_CHAT',
    lead_found: true,
    message: incoming.message,
    inbound_name: incoming.name || '',
    message_id: incoming.message_id || '',
  },
}];
"""


def main() -> None:
    wf = json.loads(PATCH.read_text(encoding="utf-8"))
    updated = False
    for node in wf.get("nodes", []):
        if node.get("name") == "Lookup Lead":
            node["parameters"]["jsCode"] = LOOKUP_JS.strip()
            node["notes"] = (
                "Fetch full lead context from AakashVani GET /internal/leads/context "
                "(requires AAKASHVANI_PUBLIC_URL + AAKASHVANI_ADMIN_KEY in n8n env)."
            )
            updated = True
            break
    if not updated:
        raise SystemExit("Lookup Lead node not found in patched workflow")
    PATCH.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("Patched Lookup Lead -> backend /internal/leads/context in", PATCH)


if __name__ == "__main__":
    main()

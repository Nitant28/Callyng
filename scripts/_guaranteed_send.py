"""Bypass Gemini on the send path so WhatsApp and email always go out."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

WA_JS = r"""
const j = $input.first().json || {};
let raw = '';
const mode = String(j.flow_type || '').trim().toUpperCase();
const isContinue = mode === 'CONTINUE_CHAT' || mode === 'INBOUND_REPLY';
if (j.output && typeof j.output === 'object' && j.output.message) raw = j.output.message;
else if (typeof j.output === 'string') raw = j.output;
else if (j.message && isContinue) raw = '';
raw = String(raw || '').trim();
const name = j.name || 'there';
const bhk = j.bhk_preference || '';
const loc = j.location_preference || j.lead_city || '';
const about = [bhk, loc].filter(Boolean).join(' in ');
const client = j.client_name || 'our team';
let message = raw;
if (!message && isContinue) {
  message = 'Hi ' + name + ', thanks for your message. A specialist from ' + client + ' will continue this conversation here shortly.';
}
if (!message) {
  message = 'Hi ' + name + '! Thanks for speaking with ' + client + (about ? ' about ' + about : '') + '. Reply on this WhatsApp chat and we will help with the next steps.';
}
return [{ json: { ...j, output: { message }, message } }];
"""

EMAIL_JS = r"""
const ai = $input.first().json || {};
const src = $('If Has Email').first().json || $('Lead Payload').first().json || {};
const j = { ...src, ...ai };
const name = j.name || 'there';
const client = j.client_name || 'our team';
const summary = j.summary || '';
const bhk = j.bhk_preference || '';
const loc = j.location_preference || j.lead_city || '';
const budget = j.budget || '';
const about = [bhk, loc, budget ? ('budget ' + budget) : ''].filter(Boolean).join(', ');
const aiOut = (ai.output && typeof ai.output === 'object') ? ai.output : {};
const subject = String(aiOut.subject || ('Follow-up from ' + client)).trim();
const body = String(aiOut.body || [
  'Hi ' + name + ',',
  '',
  'Thank you for speaking with us' + (about ? ' about ' + about : '') + '.',
  summary ? ('Call summary: ' + summary) : '',
  'A representative will contact you shortly. You can also reply to our WhatsApp message.',
  '',
  'Regards,',
  client,
].filter((line, i, arr) => line !== '' || (arr[i-1] !== '')).join('\n')).trim();
return [{ json: { ...j, output: { subject, body }, email: j.email } }];
"""


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in wf["nodes"]}

    # Always-on WhatsApp copy (reuse Ensure node)
    by["Ensure WhatsApp Text"]["parameters"]["jsCode"] = WA_JS
    by["Ensure WhatsApp Text"]["notes"] = "Always produces WhatsApp text. Does not depend on Gemini."

    if "Build Email" not in by:
        wf["nodes"].append(
            {
                "parameters": {"jsCode": EMAIL_JS, "mode": "runOnceForAllItems"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [520, 40],
                "id": "build-email-0001-0002-0003-0004",
                "name": "Build Email",
                "notes": "Always builds subject/body from lead fields. No Gemini.",
            }
        )

    # Outbound WhatsApp: skip Gemini entirely
    wf["connections"]["Lead Payload"] = {
        "main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]
    }
    wf["connections"]["Ensure WhatsApp Text"] = {
        "main": [[{"node": "Prepare Send", "type": "main", "index": 0}]]
    }
    # Keep Gemini connected as unused optional? Disconnect so it cannot fail the run.
    # Generate WhatsApp Message remains on canvas for later, but not in path.

    wf["connections"]["If Has Email"] = {
        "main": [[{"node": "Build Email", "type": "main", "index": 0}], []]
    }
    wf["connections"]["Generate Follow-up Email"] = {"main": [[]]}
    wf["connections"]["Build Email"] = {
        "main": [[{"node": "Send Email", "type": "main", "index": 0}]]
    }

    send_email = by["Send Email"]
    send_email["parameters"]["sendTo"] = "={{ $json.email }}"
    send_email["parameters"]["subject"] = "={{ $json.output.subject }}"
    send_email["parameters"]["message"] = "={{ $json.output.body }}"

    SRC.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("guaranteed send path: code WhatsApp + email, Gemini off the critical path")


if __name__ == "__main__":
    main()

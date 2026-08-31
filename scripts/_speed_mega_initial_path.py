"""Speed up Mega_Workflow initial WhatsApp+email path.

Root cause of 2–4 min: LangChain Gemini agent on the FIRST send, plus webhook
waiting for the full graph. Initial follow-up already has backend-generated
copy in fallback_whatsapp / fallback email. Skip Gemini for INITIAL_FOLLOWUP.
Keep Gemini only for inbound CONTINUE_CHAT.
"""
from __future__ import annotations

import json
from pathlib import Path

PATCH = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

ENSURE_JS = r"""
const j = $input.first().json || {};
const mode = String(j.flow_type || '').trim().toUpperCase();
const isContinue = mode === 'CONTINUE_CHAT' || mode === 'INBOUND_REPLY';
let raw = '';
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
  message = j.fallback_inbound_whatsapp || ('Hi ' + name + ', thanks for your message. How can I help you further?');
}
if (!message) {
  message = j.fallback_whatsapp || ('Hi ' + name + '! Thanks for speaking with ' + client + (about ? ' about ' + about : '') + '. Reply on this WhatsApp chat and we will help with the next steps.');
}
return [{ json: { ...j, output: { message }, message } }];
"""


def main() -> None:
    data = json.loads(PATCH.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in data["nodes"]}

    webhook = by["Webhook"]
    webhook["parameters"]["responseMode"] = "onReceived"
    webhook["parameters"].setdefault("options", {})
    webhook["notes"] = "Respond immediately so Aakashvani is not blocked. WhatsApp/email send in the background."

    by["Ensure WhatsApp Text"]["parameters"]["jsCode"] = ENSURE_JS
    by["Ensure WhatsApp Text"]["notes"] = "Instant first message from backend fallback. No Gemini wait."

    gen = by["Generate WhatsApp Message"]
    gen["parameters"].setdefault("options", {})
    gen["parameters"]["options"]["maxIterations"] = 1
    gen["onError"] = "continueRegularOutput"

    rec = by["Record in Aakashvani"]
    rec["parameters"].setdefault("options", {})
    rec["parameters"]["options"]["timeout"] = 5000
    rec["onError"] = "continueRegularOutput"

    conn = data["connections"]
    conn["Lead Payload"] = {
        "main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]
    }
    conn["Lookup Lead"] = {
        "main": [[{"node": "Generate WhatsApp Message", "type": "main", "index": 0}]]
    }
    conn["Generate WhatsApp Message"] = {
        "main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]
    }

    PATCH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("patched", PATCH)
    print("initial path: Lead Payload -> Ensure WhatsApp Text (no Gemini)")
    print("inbound path: Lookup Lead -> Generate WhatsApp Message -> Ensure WhatsApp Text")
    print("webhook responseMode=onReceived")


if __name__ == "__main__":
    main()

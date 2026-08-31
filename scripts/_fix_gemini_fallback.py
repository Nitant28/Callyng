"""Use a working Gemini model and always emit WhatsApp text."""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")

ENSURE_JS = """
const lead = $('Lead Payload').first().json;
const ai = $input.first().json || {};
let raw = '';
if (ai.output && typeof ai.output === 'object' && ai.output.message) {
  raw = ai.output.message;
} else if (typeof ai.output === 'string') {
  raw = ai.output;
} else if (ai.message) {
  raw = ai.message;
}
raw = String(raw || '').trim();
if (raw.startsWith('{')) {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && parsed.message) raw = String(parsed.message).trim();
  } catch (e) {}
}
const name = lead.name || 'there';
const bhk = lead.bhk_preference || '';
const loc = lead.location_preference || lead.lead_city || '';
const about = [bhk, loc].filter(Boolean).join(' in ');
const fallback = 'Hi ' + name + '! Thanks for speaking with our assistant' + (about ? ' about ' + about : '') + '. Reply on WhatsApp and we will help with the next steps.';
const message = raw || fallback;
return [{ json: { ...lead, output: { message }, message } }];
"""


def main() -> None:
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    by = {n["name"]: n for n in wf["nodes"]}

    for name in ("Google Gemini Chat Model", "Google Gemini Chat Model1"):
        if name in by:
            by[name]["parameters"]["modelName"] = "models/gemini-2.5-flash"

    wa = by["Generate WhatsApp Message"]
    wa["onError"] = "continueRegularOutput"
    wa["parameters"]["hasOutputParser"] = False

    ensure = {
        "parameters": {"jsCode": ENSURE_JS},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [720, 420],
        "id": "ensure-wa-text-0001-0002-0003-0004",
        "name": "Ensure WhatsApp Text",
        "notes": "If Gemini fails or returns empty, still send a safe follow-up.",
    }
    if "Ensure WhatsApp Text" not in by:
        wf["nodes"].append(ensure)

    wf["connections"]["Generate WhatsApp Message"] = {
        "main": [[{"node": "Ensure WhatsApp Text", "type": "main", "index": 0}]]
    }
    wf["connections"]["Ensure WhatsApp Text"] = {
        "main": [[{"node": "Prepare Send", "type": "main", "index": 0}]]
    }

    SRC.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print("gemini+fallback written")


if __name__ == "__main__":
    main()

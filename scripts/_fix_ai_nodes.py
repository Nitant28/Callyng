"""Fix the Mega_Workflow AI nodes on the live n8n instance.

What it repairs:
  1. Both Gemini chat models: `modelName` must be a plain string. A previous patch
     wrote a resource-locator object (`{__rl: true, ...}`), which makes the node
     throw `fields.model.replace is not a function` on every run.
  2. `Generate Follow-up Email` is wired back into the email path
     (If Has Email -> agent -> Build Email -> Send Email).
  3. Code nodes downstream of the agents parse the AI output defensively and always
     recover lead context from a guaranteed upstream node.
  4. Memory session key is scoped per client + phone.

Run with no args for a dry run, `--apply` to publish.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

BASE = os.environ.get("N8N_BASE", "https://n8n.bhuvisx.com")
WF = os.environ.get("N8N_WF_ID", "4xarbWK3DXLbENzC")
BACKUP_DIR = Path("fixtures/n8n_exports_local")

# Pro models return HTTP 429 (free-tier quota 0) on this API key; flash models work.
# 3.7-flash is the newest that the key can actually call - see scripts/_probe_gemini_models.py.
MODEL = os.environ.get("N8N_GEMINI_MODEL", "models/gemini-3.7-flash")
# Gemini 3.x flash spends output tokens on reasoning, so a small cap yields empty text.
MAX_OUTPUT_TOKENS = int(os.environ.get("N8N_GEMINI_MAX_TOKENS", "8192"))

BUILD_EMAIL_JS = r"""
function parseOut(v) {
  if (v === undefined || v === null) return {};
  if (typeof v === 'object') return v;
  if (typeof v === 'string') {
    const s = v.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
    try { return JSON.parse(s); } catch (e) { return { body: v }; }
  }
  return {};
}
const ai = $input.first().json || {};
const src = $('If Has Email').first().json || {};
const base = { ...src, ...ai };
const aiOut = parseOut(ai.output !== undefined ? ai.output : (ai.text !== undefined ? ai.text : ai.response));
const name = base.name || 'there';
const client = base.client_name || 'our team';
const summary = base.summary || '';
const bhk = base.bhk_preference || '';
const loc = base.location_preference || base.lead_city || '';
const budget = base.budget || '';
const about = [bhk, loc, budget ? ('budget ' + budget) : ''].filter(Boolean).join(', ');
const aiSubject = String((aiOut && aiOut.subject) || '').trim();
const aiBody = String((aiOut && aiOut.body) || '').trim();
const subject = aiSubject || ('Follow-up from ' + client);
const body = aiBody || [
  'Hi ' + name + ',',
  '',
  'Thank you for speaking with us' + (about ? ' about ' + about : '') + '.',
  summary ? ('Call summary: ' + summary) : '',
  'A representative will contact you shortly. You can also reply to our WhatsApp message.',
  '',
  'Regards,',
  client,
].filter(Boolean).join('\n');
return [{ json: {
  ...base,
  output: { subject, body },
  email: base.email,
  ai_generated: Boolean(aiSubject && aiBody),
} }];
"""

ENSURE_WA_JS = r"""
function parseOut(v) {
  if (v === undefined || v === null) return {};
  if (typeof v === 'object') return v;
  if (typeof v === 'string') {
    const s = v.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
    try { return JSON.parse(s); } catch (e) { return { message: v }; }
  }
  return {};
}
const ai = $input.first().json || {};
const src = $('Lead Payload').first().json || {};
const base = { ...src, ...ai };
const mode = String(base.flow_type || '').trim().toUpperCase();
const isContinue = mode === 'CONTINUE_CHAT' || mode === 'INBOUND_REPLY';
const parsed = parseOut(ai.output !== undefined ? ai.output : (ai.text !== undefined ? ai.text : ai.response));
let raw = String((parsed && parsed.message) || '').trim();
const inbound = String(src.message || '').trim();
if (raw && inbound && raw === inbound) raw = '';
const name = src.name || 'there';
const bhk = src.bhk_preference || '';
const loc = src.location_preference || src.lead_city || '';
const about = [bhk, loc].filter(Boolean).join(' in ');
const client = src.client_name || 'our team';
let message = raw;
if (!message && isContinue) {
  message = 'Hi ' + name + ', thanks for your message. A specialist from ' + client + ' will continue this conversation here shortly.';
}
if (!message) {
  message = 'Hi ' + name + '! Thanks for speaking with ' + client + (about ? ' about ' + about : '') + '. Reply on this WhatsApp chat and we will help with the next steps.';
}
return [{ json: { ...base, output: { message }, message, ai_generated: Boolean(raw) } }];
"""

PREPARE_SEND_JS = r"""
const src = $('Lead Payload').first().json || {};
const upstream = $input.first().json || {};
const p = String(src.phone || upstream.phone || '').trim();
const d = p.replace(/\D/g, '');
let e164 = '';
if (p.startsWith('+')) e164 = '+' + d;
else if (d.length === 10) e164 = '+91' + d;
else if (d.length === 12 && d.startsWith('91')) e164 = '+' + d;
else if (d) e164 = '+' + d;
const message = String(
  (upstream.output && upstream.output.message) || upstream.message || ''
).trim();
return [{ json: {
  ...src,
  phone_e164: e164,
  message,
  customer_name: src.name || '',
  ai_generated: Boolean(upstream.ai_generated),
} }];
"""

EMAIL_SYSTEM = (
    "You write short, warm, factual follow-up emails for a real-estate sales team. "
    "Use only the facts given to you. Never invent prices, availability, or promises. "
    "Respond with JSON only, matching the requested schema."
)

WA_SYSTEM = (
    "You write concise WhatsApp messages for a real-estate sales team. "
    "Use only the facts given to you. Never invent prices, inventory, or promises. "
    "Respond with JSON only, matching the requested schema."
)


def login():
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps(
        {"emailOrLdapLoginId": os.environ["N8N_EMAIL"], "password": os.environ["N8N_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def get_workflow(op):
    req = urllib.request.Request(BASE + f"/rest/workflows/{WF}", headers={"Accept": "application/json"})
    with op.open(req, timeout=60) as r:
        wf = json.loads(r.read())
    return wf.get("data", wf)


def patch_workflow(op, wf, nodes, connections):
    payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings") or {},
        "staticData": wf.get("staticData"),
        "versionId": wf.get("versionId"),
    }
    req = urllib.request.Request(
        BASE + f"/rest/workflows/{WF}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "n8n-version-id": str(wf.get("versionId") or ""),
        },
    )
    try:
        with op.open(req, timeout=60) as r:
            saved = json.loads(r.read())
            return saved.get("data", saved)
    except urllib.error.HTTPError as e:
        print("PATCH failed:", e.code, e.read()[:1000].decode("utf-8", "replace"))
        raise


def main() -> None:
    apply = "--apply" in sys.argv
    op = login()
    wf = get_workflow(op)
    nodes = wf["nodes"]
    conns = wf["connections"]
    by = {n["name"]: n for n in nodes}

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"Mega_Workflow__backup_{stamp}.json"
    backup.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print(f"backup -> {backup}")

    print("\n== current send/record node params ==")
    for name in ("Send Email", "Send WhatsApp", "Record in Aakashvani", "If Has WhatsApp Text"):
        node = by.get(name)
        if node:
            print(f"\n--- {name} ({node.get('type')} v{node.get('typeVersion')}) ---")
            print(json.dumps(node.get("parameters") or {}, indent=2)[:2000])

    changes: list[str] = []

    for name in ("Google Gemini Chat Model", "Google Gemini Chat Model1"):
        node = by[name]
        params = node.setdefault("parameters", {})
        before = params.get("modelName")
        params["modelName"] = MODEL
        params["options"] = {"temperature": 0.4, "maxOutputTokens": MAX_OUTPUT_TOKENS}
        node["retryOnFail"] = True
        node["maxTries"] = 3
        node["waitBetweenTries"] = 2000
        node.pop("onError", None)
        changes.append(f"{name}: modelName {json.dumps(before)} -> {MODEL!r}, +retry(3)")

    for name, system in (
        ("Generate Follow-up Email", EMAIL_SYSTEM),
        ("Generate WhatsApp Message", WA_SYSTEM),
    ):
        node = by[name]
        params = node.setdefault("parameters", {})
        params["hasOutputParser"] = True
        opts = params.setdefault("options", {})
        opts["systemMessage"] = system
        node["onError"] = "continueRegularOutput"
        node["retryOnFail"] = True
        node["maxTries"] = 2
        node["waitBetweenTries"] = 2000
        node["alwaysOutputData"] = True
        changes.append(f"{name}: +systemMessage, onError=continueRegularOutput, retry(2)")

    mem = by["Simple Memory"]
    mem["parameters"]["sessionKey"] = (
        "={{ ($json.client_id || 'global') + ':' + ($json.phone || $json.lead_id || 'unknown') }}"
    )
    changes.append("Simple Memory: sessionKey scoped to client_id + phone")

    by["Build Email"]["parameters"] = {"jsCode": BUILD_EMAIL_JS, "mode": "runOnceForAllItems"}
    by["Ensure WhatsApp Text"]["parameters"] = {"jsCode": ENSURE_WA_JS, "mode": "runOnceForAllItems"}
    by["Prepare Send"]["parameters"] = {"jsCode": PREPARE_SEND_JS, "mode": "runOnceForAllItems"}
    changes.append("Build Email / Ensure WhatsApp Text / Prepare Send: defensive AI-output parsing")

    conns["If Has Email"]["main"][0] = [
        {"node": "Generate Follow-up Email", "type": "main", "index": 0}
    ]
    conns.setdefault("Generate Follow-up Email", {})["main"] = [
        [{"node": "Build Email", "type": "main", "index": 0}]
    ]
    changes.append("connections: If Has Email -> Generate Follow-up Email -> Build Email")

    print("\n== planned changes ==")
    for c in changes:
        print("  -", c)

    if not apply:
        print("\nDRY RUN. Re-run with --apply to publish.")
        return

    saved = patch_workflow(op, wf, nodes, conns)
    print("\npublished. new versionId:", saved.get("versionId"), "active:", saved.get("active"))


if __name__ == "__main__":
    main()

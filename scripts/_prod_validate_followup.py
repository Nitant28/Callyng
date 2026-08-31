"""Controlled production validation of Mega_Workflow + Aakashvani follow-up.

Does not modify n8n unless --fix-workflow is passed (not used here).
Prints evidence for webhook, payload, timings, and record-back.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

N8N_BASE = (os.getenv("N8N_BASE_URL") or os.getenv("N8N_BASE") or "https://n8n.bhuvisx.com").rstrip("/")
PROD_WEBHOOK = (
    os.getenv("N8N_LEAD_WEBHOOK_URL")
    or os.getenv("N8N_FOLLOWUP_WEBHOOK_URL")
    or "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
)
USER_WEBHOOK = "https://n8n.bhuvisx.com/webhook/5879f520-d9b9-4dc9-ba95-3392c2f30792"
WF = os.getenv("N8N_WF_ID", "4xarbWK3DXLbENzC")


def login():
    email = os.environ.get("N8N_EMAIL")
    password = os.environ.get("N8N_PASSWORD")
    if not email or not password:
        raise SystemExit("N8N_EMAIL / N8N_PASSWORD required")
    cj = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps({"emailOrLdapLoginId": email, "password": password}).encode()
    req = urllib.request.Request(
        N8N_BASE + "/rest/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with op.open(req, timeout=30):
        pass
    return op


def get(op, path):
    req = urllib.request.Request(N8N_BASE + path, headers={"Accept": "application/json"})
    with op.open(req, timeout=60) as r:
        return json.loads(r.read())


def unwrap_wf(payload):
    if isinstance(payload, dict) and "nodes" not in payload and "data" in payload:
        return payload["data"]
    return payload


def post_webhook(url: str, payload: dict, timeout: int = 20) -> tuple[int, str, float]:
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "aakashvani-prod-validate/1.0",
    }
    secret = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip()
    if secret:
        headers["X-Aakashvani-Webhook-Secret"] = secret
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.perf_counter() - t0
            return int(resp.status), resp.read().decode("utf-8", "replace")[:800], elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        return int(e.code), e.read().decode("utf-8", "replace")[:800], elapsed
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return 0, str(e), elapsed


def sample_payload(*, interested: bool, event_id: str, email: str | None = "singhnitant28@gmail.com") -> dict:
    return {
        "event": "lead_qualified",
        "event_type": "INTERESTED_LEAD" if interested else "LEAD_QUALIFIED",
        "flow_type": "INITIAL_FOLLOWUP",
        "interested": interested,
        "event_id": event_id,
        "client_id": "00000000-0000-4000-8000-000000000001",
        "lead": {
            "id": "00000000-0000-4000-8000-000000000011",
            "name": "Nitant",
            "phone": "+917397867643",
            "email": email,
            "lead_type": "interested" if interested else "cold",
            "metadata": {"lead_city": "Pune", "email": email},
        },
        "extraction": {
            "intent_status": "Interested" if interested else "Not Interested",
            "intent_status": "hot" if interested else "not_interested",
            "bhk_preference": "2 BHK",
            "bhk_preference": "2 BHK",
            "location_preference": "Pune",
            "location_preference": "Pune",
            "budget": "8000000",
            "summary": "Customer is interested in a 2 BHK property in Pune." if interested else "Not interested.",
        },
        "campaign": {"id": "00000000-0000-4000-8000-000000000003", "name": "Aakashvani Test"},
        "client": {"id": "00000000-0000-4000-8000-000000000001", "name": "Dev Client", "industry": "real_estate"},
        "call": {"recording_url": "", "session_call_id": event_id.split(":")[0], "id": event_id.split(":")[0]},
        "qualification": {"status": "interested" if interested else "not interested", "score": 80 if interested else 10},
        "agent": {"id": None},
        "follow_up": {"channel": "whatsapp", "action": "send", "stage": 1, "idempotency_key": f"n8n_{event_id}_wa_1"},
        "fallback": {
            "generated_by": "aakashvani-backend",
            "whatsapp": {"message": "Hi Nitant, thanks for speaking with Dev Client about a 2 BHK in Pune. Reply here and we will help with next steps."},
            "email": {"subject": "Follow-up from Dev Client", "body": "Hi Nitant,\n\nThank you for speaking with Dev Client about a 2 BHK in Pune.\n\nRegards,\nDev Client"},
            "reply": {"message": "Hi Nitant, this is Dev Client. How can we help with your 2 BHK search in Pune?"},
        },
        "metadata": {"test": True, "validation_run": True},
    }


def inspect_workflow(wf: dict) -> None:
    nodes = wf.get("nodes") or []
    conns = wf.get("connections") or {}
    print("\n== WORKFLOW ==")
    print("name", wf.get("name"), "active", wf.get("active"), "id", wf.get("id"), "version", wf.get("versionId"))
    print("nodes", len(nodes))
    stale = []
    for n in nodes:
        blob = json.dumps(n.get("parameters") or {})
        if "ngrok" in blob.lower() or "localhost" in blob.lower():
            stale.append(n.get("name"))
        if n.get("name") == "Webhook":
            print("Webhook path", (n.get("parameters") or {}).get("path"))
            print("Webhook options", (n.get("parameters") or {}).get("options"))
            print("disabled", n.get("disabled"))
        if n.get("disabled"):
            print("DISABLED", n.get("name"))
    print("stale ngrok/localhost nodes:", stale or "none")
    for src in ("Lead Payload", "If Continue Chat", "If Has Email", "If Interested"):
        if src in conns:
            print("conn", src, "->", json.dumps(conns[src])[:400])
    lc = next((n for n in nodes if n.get("name") in ("Lead Context", "Lead Context")), None)
    if lc:
        js = (lc.get("parameters") or {}).get("jsCode") or (lc.get("parameters") or {}).get("jsCode") or ""
        print("Lead Context reads intent_status", "intent_status" in js, "intent_status", "intent_status" in js)
        print("Lead Context reads bhk_preference", "bhk_preference" in js, "bhk_preference", "bhk_preference" in js)


def latest_execs(op, limit=5):
    q = urllib.parse.quote(json.dumps({"workflowId": WF}))
    listing = get(op, f"/rest/executions?filter={q}&limit={limit}")
    items = listing.get("data", {}).get("results") if isinstance(listing.get("data"), dict) else listing.get("data")
    return items or []


def main() -> None:
    print("N8N_BASE", N8N_BASE)
    print("PROD_WEBHOOK", PROD_WEBHOOK)
    print("USER_WEBHOOK", USER_WEBHOOK)
    print("same_url", PROD_WEBHOOK.rstrip("/") == USER_WEBHOOK.rstrip("/"))

    op = login()
    wf = unwrap_wf(get(op, f"/rest/workflows/{WF}"))
    inspect_workflow(wf)

    print("\n== WEBHOOK HTTP ==")
    # Invalid URL
    st, body, elapsed = post_webhook("https://n8n.bhuvisx.com/webhook/does-not-exist-aaaa", {"ping": True}, timeout=10)
    print(f"invalid webhook HTTP {st} in {elapsed:.3f}s body={body[:120]!r}")

    results = []
    for i in range(3):
        eid = f"validate-{datetime.now(timezone.utc).strftime('%H%M%S')}-{i}:{uuid4()}"
        payload = sample_payload(interested=True, event_id=eid)
        st, body, elapsed = post_webhook(PROD_WEBHOOK, payload, timeout=20)
        print(f"interested[{i}] HTTP {st} in {elapsed:.3f}s event_id={eid} body={body[:160]!r}")
        results.append((eid, st, elapsed, body))
        time.sleep(1.5)

    # duplicate
    dup_id = results[0][0]
    st, body, elapsed = post_webhook(PROD_WEBHOOK, sample_payload(interested=True, event_id=dup_id), timeout=20)
    print(f"duplicate HTTP {st} in {elapsed:.3f}s event_id={dup_id} body={body[:160]!r}")

    # not interested
    nid = f"validate-ni-{uuid4()}"
    st, body, elapsed = post_webhook(PROD_WEBHOOK, sample_payload(interested=False, event_id=nid), timeout=20)
    print(f"not_interested HTTP {st} in {elapsed:.3f}s body={body[:160]!r}")

    # no email
    eid = f"validate-noemail-{uuid4()}"
    p = sample_payload(interested=True, event_id=eid, email=None)
    p["lead"]["email"] = None
    st, body, elapsed = post_webhook(PROD_WEBHOOK, p, timeout=20)
    print(f"no_email HTTP {st} in {elapsed:.3f}s body={body[:160]!r}")

    print("\n== RECENT EXECUTIONS ==")
    time.sleep(3)
    for it in latest_execs(op, 8):
        print(f"  #{it.get('id')} status={it.get('status')} started={it.get('startedAt')} stopped={it.get('stoppedAt')} mode={it.get('mode')}")

    print("\n== PAYLOAD KEY CHECK ==")
    from integrations.n8n.payload import build_lead_qualified_payload
    from uuid import UUID as _UUID

    built = build_lead_qualified_payload(
        client_id=_UUID("00000000-0000-4000-8000-000000000001"),
        lead={"id": uuid4(), "name": "Nitant", "phone": "7397867643", "lead_type": "interested", "metadata": {"email": "a@b.co", "lead_city": "Pune"}},
        session_call_id="sess1",
        duration_seconds=10,
        extraction={"intent_status": "Interested", "summary": "2 BHK Pune", "bhk_preference": "2 BHK", "location_preference": "Pune", "budget": "80L"},
        campaign={"id": uuid4(), "name": "Camp"},
        outcome="Interested",
        client={"name": "Dev Client", "industry": "real_estate"},
    )
    required = ["event", "event_id", "client_id", "client", "lead", "call", "extraction", "qualification", "campaign", "agent", "follow_up", "metadata"]
    print("missing top-level", [k for k in required if k not in built])
    print("lead.name", built["lead"].get("name"), "phone", built["lead"].get("phone"), "email", built["lead"].get("email"))
    print("extraction keys", sorted(built["extraction"].keys()))
    print("fallback whatsapp", (built.get("fallback") or {}).get("whatsapp", {}).get("message", "")[:80])
    print("aakashvani", built.get("aakashvani"))


if __name__ == "__main__":
    from uuid import UUID as _UUID  # noqa: F401 — used in payload check

    main()

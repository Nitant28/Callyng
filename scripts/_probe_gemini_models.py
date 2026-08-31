"""List Gemini models the project API key can see and probe which ones have quota.

Read-only discovery plus a 1-token generation probe per candidate, so we pick a model
that actually works on this key's tier instead of guessing. Never prints the key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"


def load_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        return key
    env = Path(".env")
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("GOOGLE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GOOGLE_API_KEY not found")


def req(url: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:400]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def main() -> None:
    key = load_key()
    status, body = req(f"{API}/models?key={key}&pageSize=200")
    if status != 200:
        print("list models failed:", status, json.dumps(body)[:500])
        return
    models = [
        m
        for m in body.get("models") or []
        if "generateContent" in (m.get("supportedGenerationMethods") or [])
        and "embedding" not in m.get("name", "")
        and "imagen" not in m.get("name", "")
    ]
    names = sorted(m["name"] for m in models)
    print(f"== {len(names)} chat-capable models visible to this key ==")
    for n in names:
        print("  ", n)

    preferred = [
        "models/gemini-3.7-flash",
        "models/gemini-3.6-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.5-flash-lite",
        "models/gemini-flash-latest",
        "models/gemini-pro-latest",
        "models/gemini-3.1-flash-lite",
        "models/gemini-3-flash-preview",
    ]
    candidates = [p for p in preferred if p in names]
    extra = [n for n in names if n not in candidates]
    if "--all" in sys.argv:
        candidates += extra

    print("\n== quota probe (tiny request each) ==")
    for name in candidates:
        st, resp = req(
            f"{API}/{name.split('models/')[-1] and name}:generateContent?key={key}",
            {
                "contents": [{"role": "user", "parts": [{"text": "Reply with the single word OK."}]}],
                "generationConfig": {"maxOutputTokens": 16, "temperature": 0},
            },
        )
        if st == 200:
            text = ""
            for cand in resp.get("candidates") or []:
                for part in ((cand.get("content") or {}).get("parts") or []):
                    text += part.get("text") or ""
            print(f"  OK   {name}  -> {text.strip()[:60]!r}")
        else:
            msg = ((resp.get("error") or {}).get("message") or json.dumps(resp))[:130]
            print(f"  FAIL {name}  -> HTTP {st}: {msg}")


if __name__ == "__main__":
    main()

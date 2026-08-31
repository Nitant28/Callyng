"""Check which N8N_* env keys are set without printing values."""
from pathlib import Path

KEYS = [
    "N8N_BASE_URL",
    "N8N_LEAD_WEBHOOK_URL",
    "N8N_FOLLOWUP_WEBHOOK_URL",
    "N8N_WEBHOOK_SECRET",
    "N8N_TIMEOUT_SECONDS",
    "N8N_WEBHOOK_URL",
]

p = Path(".env")
if not p.exists():
    print("ENV_FILE: missing")
else:
    print("ENV_FILE: present")
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for key in KEYS:
        present = False
        nonempty = False
        localhost = False
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            name, val = s.split("=", 1)
            if name.strip() != key:
                continue
            present = True
            v = val.strip().strip('"').strip("'")
            nonempty = bool(v)
            localhost = ("localhost" in v.lower()) or ("127.0.0.1" in v)
        print(f"{key}: present={present} set={nonempty} contains_localhost={localhost}")

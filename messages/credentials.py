"""Server-side credential helpers — never expose plaintext to React."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any


def _key_bytes() -> bytes:
    raw = (os.getenv("WHATSAPP_CREDENTIALS_KEY") or os.getenv("ADMIN_API_KEY") or "dev-only-not-for-prod").encode()
    return hashlib.sha256(raw).digest()


def encrypt_credentials(plaintext: str) -> str:
    """Obfuscate credentials at rest (HMAC-masked XOR). Replace with KMS/Fernet in prod ops."""
    if not plaintext:
        return ""
    key = _key_bytes()
    data = plaintext.encode("utf-8")
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    mac = hmac.new(key, out, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac + out).decode("ascii")


def decrypt_credentials(blob: str | None) -> str:
    if not blob:
        return ""
    key = _key_bytes()
    raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    mac, out = raw[:32], raw[32:]
    if not hmac.compare_digest(mac, hmac.new(key, out, hashlib.sha256).digest()):
        raise ValueError("credentials integrity check failed")
    data = bytes(b ^ key[i % len(key)] for i, b in enumerate(out))
    return data.decode("utf-8")


def decrypt_secret_map(blob: str | None) -> dict[str, str]:
    """Credentials may be a raw token (legacy) or a JSON object of secrets."""
    import json

    raw = decrypt_credentials(blob)
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items() if v is not None and str(v) != ""}
        except json.JSONDecodeError:
            pass
    return {"access_token": raw}


def encrypt_secret_map(secrets: dict[str, str]) -> str:
    import json

    cleaned = {k: v for k, v in secrets.items() if v}
    if not cleaned:
        return ""
    return encrypt_credentials(json.dumps(cleaned, separators=(",", ":")))


def public_integration_view(row: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets before any API response."""
    cfg = row.get("configuration") or {}
    if isinstance(cfg, str):
        import json
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    public_cfg = {
        k: v
        for k, v in (cfg.items() if isinstance(cfg, dict) else [])
        if k not in ("access_token", "api_key", "app_secret", "webhook_verify_token")
    }
    return {
        "id": str(row["id"]),
        "client_id": str(row["client_id"]),
        "provider": row.get("provider"),
        "display_name": row.get("display_name"),
        "phone_number_id": row.get("phone_number_id"),
        "business_account_id": row.get("business_account_id"),
        "status": row.get("status"),
        "enabled": bool(row.get("enabled")),
        "connection_status": row.get("connection_status") or "untested",
        "last_tested_at": row.get("last_tested_at"),
        "configuration": public_cfg,
        "last_error": row.get("last_error"),
        "credentials_configured": bool(row.get("credentials_encrypted")),
        "webhook_verify_token_configured": bool(row.get("webhook_verify_token")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }

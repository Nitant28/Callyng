"""Validate n8n webhook URLs — HTTPS only, block obvious SSRF targets."""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse


def validate_n8n_webhook_url(url: str) -> tuple[bool, str | None]:
    """Return (ok, error_message)."""
    raw = (url or "").strip()
    if not raw:
        return False, "URL is required"
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme != "https":
        return False, "Webhook URL must use HTTPS"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL must include a hostname"

    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host in blocked_hosts or host.endswith(".local"):
        return False, "Local/private hosts are not allowed"

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, "Private/reserved IP addresses are not allowed"
    except ValueError:
        pass

    allowed_suffixes = (
        ".bhuvisx.com",
        ".n8n.cloud",
        ".n8n.io",
    )
    base = (os.getenv("N8N_BASE_URL") or "").strip().rstrip("/")
    allowed_hosts: set[str] = set()
    if base:
        base_host = (urlparse(base).hostname or "").lower()
        if base_host:
            allowed_hosts.add(base_host)

    if host in allowed_hosts or any(host.endswith(s) for s in allowed_suffixes):
        return True, None

    # Allow any public HTTPS host when explicitly enabled (default: permissive for ops).
    permissive = (os.getenv("N8N_ALLOW_ANY_HTTPS_HOST") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if permissive:
        return True, None

    return False, "Webhook host is not in the allowed list; set N8N_ALLOW_ANY_HTTPS_HOST=1 or use N8N_BASE_URL host"

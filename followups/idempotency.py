"""HTTP failure classification for n8n / provider retries."""

from __future__ import annotations


def classify_http_failure(status: int | None, error: str | None = None) -> tuple[str, bool]:
    """Return (category, retryable)."""
    code = int(status or 0)
    err = str(error or "").casefold()
    if code in (408, 425, 429) or code >= 500:
        return ("transient_http", True)
    if code in (401, 403):
        return ("auth_failed", False)
    if code == 404:
        return ("not_found", False)
    if code == 400:
        permanent_markers = (
            "template",
            "parameter",
            "opt",
            "phone",
            "invalid",
            "not approved",
            "does not exist",
        )
        if any(m in err for m in permanent_markers):
            return ("provider_rejected", False)
        return ("bad_request", False)
    if "timeout" in err or "temporarily" in err:
        return ("transient_network", True)
    return ("unknown", False)


def inbound_message_key(*, client_id, provider_message_id: str | None) -> str | None:
    pmid = str(provider_message_id or "").strip()
    if not pmid:
        return None
    return f"inbound:{client_id}:{pmid}"

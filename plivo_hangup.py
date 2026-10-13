"""Compatibility wrapper pointing to telnyx_hangup.py."""

from telnyx_hangup import (
    _is_intentional_api_hangup,
    _parse_telnyx_payload as _parse_plivo_payload,
    handle_plivo_hangup,
    handle_telnyx_webhook,
)

__all__ = [
    "_is_intentional_api_hangup",
    "_parse_plivo_payload",
    "handle_plivo_hangup",
    "handle_telnyx_webhook",
]

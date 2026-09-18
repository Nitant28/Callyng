"""Unit tests for MetaCloudProvider.verify_webhook (subscribe + POST HMAC)."""

from __future__ import annotations

import hashlib
import hmac

from messages.providers.meta import MetaCloudProvider


def _sig(app_secret: str, raw_body: bytes) -> str:
    digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_meta_signature_accepted():
    provider = MetaCloudProvider()
    secret = "test_app_secret"
    body = b'{"object":"whatsapp_business_account"}'
    ok = provider.verify_webhook(
        {"app_secret": secret, "webhook_verify_token": "verify-me"},
        headers={"x-hub-signature-256": _sig(secret, body)},
        raw_body=body,
        query={},
    )
    assert ok is True


def test_invalid_signature_rejected():
    provider = MetaCloudProvider()
    body = b'{"object":"whatsapp_business_account"}'
    ok = provider.verify_webhook(
        {"app_secret": "test_app_secret"},
        headers={"x-hub-signature-256": "sha256=deadbeef"},
        raw_body=body,
        query={},
    )
    assert ok is False


def test_missing_signature_rejected():
    provider = MetaCloudProvider()
    body = b'{"object":"whatsapp_business_account"}'
    ok = provider.verify_webhook(
        {"app_secret": "test_app_secret"},
        headers={},
        raw_body=body,
        query={},
    )
    assert ok is False


def test_missing_app_secret_rejected():
    provider = MetaCloudProvider()
    body = b'{"object":"whatsapp_business_account"}'
    ok = provider.verify_webhook(
        {"app_secret": "", "webhook_verify_token": "verify-me"},
        headers={"x-hub-signature-256": _sig("anything", body)},
        raw_body=body,
        query={},
    )
    assert ok is False


def test_valid_subscription_verification_token_accepted():
    provider = MetaCloudProvider()
    ok = provider.verify_webhook(
        {"webhook_verify_token": "verify-me", "app_secret": "unused"},
        headers={},
        raw_body=b"",
        query={"hub.mode": "subscribe", "hub.verify_token": "verify-me"},
    )
    assert ok is True


def test_invalid_subscription_verification_token_rejected():
    provider = MetaCloudProvider()
    ok = provider.verify_webhook(
        {"webhook_verify_token": "verify-me"},
        headers={},
        raw_body=b"",
        query={"hub.mode": "subscribe", "hub.verify_token": "wrong-token"},
    )
    assert ok is False

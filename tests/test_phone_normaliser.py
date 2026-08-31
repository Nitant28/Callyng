"""Shared E.164 / last-10 phone contract for lead lookup."""

from lead_upload.normaliser import last10_digits, normalise_phone


def test_indian_phone_variants_share_e164_and_last10():
    variants = [
        "7397867643",
        "+917397867643",
        "917397867643",
        "+91 7397867643",
        "91-7397867643",
    ]
    e164s = {normalise_phone(v) for v in variants}
    last10s = {last10_digits(v) for v in variants}
    assert e164s == {"+917397867643"}
    assert last10s == {"7397867643"}


def test_last10_rejects_empty():
    assert last10_digits("") is None
    assert last10_digits("   ") is None

from integrations.n8n.fallbacks import fallback_inbound_whatsapp, fallback_initial_email, fallback_initial_whatsapp


def test_initial_whatsapp_uses_name_and_context():
    text = fallback_initial_whatsapp(
        name="Nitantt Sharma",
        client_name="BhuvisX",
        extraction={"bhk_preference": "2 BHK", "location_preference": "Bangalore"},
        metadata={},
    )
    assert "Nitantt" in text
    assert "BhuvisX" in text
    assert "2 BHK" in text
    assert "AI" not in text
    assert "fail" not in text.lower()


def test_initial_email_has_subject_and_body():
    subject, body = fallback_initial_email(
        name="Rahul",
        client_name="Acme",
        extraction={"summary": "Wants a site visit"},
        metadata={},
    )
    assert "Acme" in subject
    assert "Rahul" in body
    assert "fail" not in body.lower()


def test_inbound_who_is_this_is_conversational():
    text = fallback_inbound_whatsapp(
        name="Nitantt",
        client_name="BhuvisX",
        inbound_text="hi who is this",
        extraction={"location_preference": "Bangalore"},
        metadata={},
    )
    assert "who is this" not in text.lower() or "BhuvisX" in text
    assert "BhuvisX" in text
    assert "Nitantt" in text

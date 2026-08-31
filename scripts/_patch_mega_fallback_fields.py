from pathlib import Path

p = Path("fixtures/n8n_exports_local/Mega_Workflow__patched.json")
t = p.read_text(encoding="utf-8")
t = t.replace(
    "fallback_whatsapp: pick(payload.fallback && payload.fallback.whatsapp),",
    "fallback_whatsapp: pick(payload.fallback && payload.fallback.whatsapp && payload.fallback.whatsapp.message, payload.fallback && payload.fallback.whatsapp),",
)
t = t.replace(
    "fallback_email_subject: pick(payload.fallback && payload.fallback.email_subject),",
    "fallback_email_subject: pick(payload.fallback && payload.fallback.email && payload.fallback.email.subject, payload.fallback && payload.fallback.email_subject),",
)
t = t.replace(
    "fallback_email_body: pick(payload.fallback && payload.fallback.email_body),",
    "fallback_email_body: pick(payload.fallback && payload.fallback.email && payload.fallback.email.body, payload.fallback && payload.fallback.email_body),",
)
t = t.replace(
    "fallback_inbound_whatsapp: pick(payload.fallback && payload.fallback.inbound_whatsapp),",
    "fallback_inbound_whatsapp: pick(payload.fallback && payload.fallback.reply && payload.fallback.reply.message, payload.fallback && payload.fallback.inbound_whatsapp),",
)
p.write_text(t, encoding="utf-8")
print("ok")

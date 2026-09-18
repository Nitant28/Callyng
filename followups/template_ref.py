"""Canonical WhatsApp template name + language handling.

Never pass a combined value such as ``hello_world=en_US`` or ``name|lang``
as the Meta template *name*. Providers may need a UI ``name|lang`` string;
that concatenation happens only via :func:`format_n8n_template_field`.
"""

from __future__ import annotations

import re
from typing import Any

_LANG_RE = re.compile(r"^[A-Za-z]{2}(_[A-Za-z]{2})?$")
_NAME_RE = re.compile(r"^[a-z0-9_]+$")


class TemplateRefError(ValueError):
    """Invalid template name or language code."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        super().__init__(detail or code)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def parse_combined_template_ref(raw: str) -> tuple[str | None, str | None]:
    text = _clean(raw)
    if not text:
        return None, None
    pipe = text.count("|")
    eq = text.count("=")
    if pipe == 0 and eq == 0:
        return text, None
    if pipe >= 1 and eq >= 1:
        raise TemplateRefError("invalid_template_name", "combined template has mixed separators")
    if pipe > 1 or eq > 1:
        raise TemplateRefError("invalid_template_name", "combined template has multiple separators")
    sep = "|" if pipe == 1 else "="
    left, right = text.split(sep, 1)
    name, lang = left.strip(), right.strip()
    if not name or not lang:
        raise TemplateRefError("invalid_template_name", "combined template missing name or language")
    return name, lang


def normalize_language_code(language: Any, *, default: str = "en_US") -> str:
    lang = _clean(language) or default
    if lang == "en":
        lang = "en_US"
    if not _LANG_RE.match(lang):
        raise TemplateRefError("invalid_language_code", f"unsupported language code: {lang}")
    return lang


def normalize_template_name(name: Any) -> str:
    raw = _clean(name)
    if not raw:
        raise TemplateRefError("invalid_template_name", "template name required")
    if "|" in raw or "=" in raw:
        peeled, _lang = parse_combined_template_ref(raw)
        raw = peeled or ""
    raw = raw.strip().casefold()
    if not raw or not _NAME_RE.match(raw):
        raise TemplateRefError("invalid_template_name", f"unsupported template name: {raw}")
    return raw


def normalize_template_ref(
    template_name: Any,
    language_code: Any = None,
    *,
    default_language: str = "en_US",
) -> dict[str, str]:
    raw_name = _clean(template_name)
    raw_lang = _clean(language_code)
    if raw_name and ("|" in raw_name or "=" in raw_name):
        peeled_name, peeled_lang = parse_combined_template_ref(raw_name)
        name = normalize_template_name(peeled_name)
        lang = normalize_language_code(raw_lang or peeled_lang, default=default_language)
        return {"template_name": name, "language_code": lang}
    name = normalize_template_name(raw_name)
    lang = normalize_language_code(raw_lang, default=default_language)
    return {"template_name": name, "language_code": lang}


def format_n8n_template_field(template_name: str, language_code: str) -> str:
    """n8n WhatsApp node UI often expects ``name|language`` in one field."""
    ref = normalize_template_ref(template_name, language_code)
    return f"{ref['template_name']}|{ref['language_code']}"


def meta_template_payload(
    *,
    to_phone: str,
    template_name: str,
    language_code: str,
    components: list | dict | None = None,
) -> dict[str, Any]:
    """Canonical Meta Cloud template body (no credentials)."""
    ref = normalize_template_ref(template_name, language_code)
    template: dict[str, Any] = {
        "name": ref["template_name"],
        "language": {"code": ref["language_code"]},
    }
    if components:
        template["components"] = components if isinstance(components, list) else [components]
    return {
        "messaging_product": "whatsapp",
        "to": str(to_phone or "").lstrip("+"),
        "type": "template",
        "template": template,
    }

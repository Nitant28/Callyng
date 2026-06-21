"""Shared post-call EXTRACTION_SCHEMA for Pyramid Parkland Nxt bots (Marathi / Hindi)."""

from __future__ import annotations

PYRAMID_EXTRACTION_RULES = """Consistency (critical):
- If the caller agreed to a site visit, said yes to visiting / a weekend slot / "चालेल" / "haan chalel" / "haan chalega" for the visit, or confirmed a visit time, site_visit_agreed should be true and intent_status must reflect engagement — use Interested, or Callback_Requested if the main outcome was a scheduled callback with a concrete time. Do NOT leave intent_status as Unknown when a site visit was clearly agreed.
- If assistant only asked whether the caller had *more questions* / *anything specific to ask* / *काही specific विचारायचं आहे* / *और कुछ पूछना है* / similar, and the caller replied with a short negative like "nahi nahi" / "नाही नाही" meaning "nothing else to ask", that is NOT property refusal — not Not_Interested unless they also clearly refuse the project/home.
- STT conflict: user role text may mishear Hindi/Marathi on phone lines (e.g. "2-3 location" transcribed as unrelated words like selling a TV). When the assistant closing turn confirms BHK and locations (e.g. "बानेर, कोंढवा और कात्रज में 3 BHK की आवश्यकता नोट कर ली है"), extract bhk_preference and location_preference from the assistant and set intent_status to Interested — NOT Wrong_Requirement based only on the garbled user phrase.

Transcript is JSON: array of {role, content, ...}. Infer only what the conversation supports."""

PYRAMID_EXTRACTION_SCHEMA: dict = {
    "mode": "both",
    "summary_prompt": (
        "Summarise this call in 2-3 sentences. Focus on the lead's "
        "interest level, any budget or property preference mentioned, "
        "and whether a site visit was agreed."
    ),
    "fields": [
        {
            "key": "intent_status",
            "type": "enum",
            "values": [
                "Interested",
                "Not_Interested",
                "Busy",
                "Callback_Requested",
                "Wrong_Requirement",
                "Unknown",
            ],
            "required": True,
            "description": (
                "Interested: engaged — site visit agreed/leaning, wants details on 2 BHK. "
                "Callback_Requested: concrete callback time/date given. "
                "Busy: wants to end / call later with NO specific time. "
                "Not_Interested: explicit refusal of home/project — not a logistical 'no'. "
                "Wrong_Requirement: plot/shop/office/rent/commercial/wrong BHK. "
                "Unknown: ambiguous or dropped call."
            ),
        },
        {
            "key": "bhk_preference",
            "type": "string",
            "required": False,
            "description": "e.g. 2BHK, 3BHK, or the literal NULL if not stated.",
        },
        {
            "key": "location_preference",
            "type": "string",
            "required": False,
            "description": "Area/city mentioned, or the literal NULL.",
        },
        {
            "key": "site_visit_agreed",
            "type": "boolean",
            "required": False,
            "description": "true only if caller clearly agreed to a site visit.",
        },
        {
            "key": "callback_time",
            "type": "string",
            "required": False,
            "description": "Specific time/date if given, else the literal NULL.",
        },
        {
            "key": "language_used",
            "type": "enum",
            "values": ["Marathi", "Hindi", "English", "Mixed"],
            "required": False,
            "description": "Primary language of the conversation.",
        },
        {
            "key": "caller_notes",
            "type": "string",
            "required": False,
            "description": "Other useful facts, or the literal NULL.",
        },
    ],
    "extraction_rules": PYRAMID_EXTRACTION_RULES,
}

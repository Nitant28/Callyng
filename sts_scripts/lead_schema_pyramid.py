"""Shared LEAD_SCHEMA for Pyramid / Prowave CSV uploads."""

PYRAMID_LEAD_SCHEMA: dict = {
    "fields": [
        {
            "key": "city",
            "type": "string",
            "required": False,
            "csv_column": "City",
        },
        {
            "key": "budget",
            "type": "string",
            "required": False,
            "csv_column": "Budget",
        },
        {
            "key": "lead_type",
            "type": "string",
            "required": False,
            "csv_column": "lead_type",
        },
    ]
}

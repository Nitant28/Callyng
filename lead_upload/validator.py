"""Validate uploaded lead DataFrames against script LEAD_SCHEMA."""

from __future__ import annotations

import pandas as pd


def _normalize_col(name: str) -> str:
    return (name or "").strip().lower()


def extract_lead_fields(lead_schema: dict) -> list[dict]:
    if not lead_schema:
        return []
    if "fields" in lead_schema and isinstance(lead_schema["fields"], list):
        return lead_schema["fields"]
    out = []
    for k, v in lead_schema.items():
        if isinstance(v, dict):
            f = dict(v)
            f["key"] = k
            out.append(f)
    return out


def _field_header_candidates(field: dict) -> list[str]:
    """Possible Excel header names for a schema field."""
    candidates = []
    for k in ("csv_column", "label", "key", "name"):
        v = field.get(k)
        if v and str(v).strip():
            candidates.append(str(v).strip())
    # de-dupe case-insensitively
    seen = set()
    out = []
    for c in candidates:
        n = _normalize_col(c)
        if n not in seen:
            seen.add(n)
            out.append(c)
    return out


def _column_present(col_map: dict, field: dict) -> bool:
    for cand in _field_header_candidates(field):
        if _normalize_col(cand) in col_map:
            return True
    return False


def field_display_header(field: dict) -> str:
    """Preferred Excel column header for a schema field."""
    for k in ("csv_column", "label", "key", "name"):
        v = field.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return "field"


def validate_dataframe(df: pd.DataFrame, lead_schema: dict) -> list[str]:
    errors: list[str] = []
    if df is None or df.empty:
        errors.append("Upload file is empty")
        return errors

    col_map = {_normalize_col(c): c for c in df.columns}

    if "phone" not in col_map:
        errors.append("Missing required column: Phone")
    if "name" not in col_map:
        errors.append("Missing required column: Name")

    fields = extract_lead_fields(lead_schema)
    for field in fields:
        if not field.get("required"):
            continue
        header = field_display_header(field)
        ncol = _normalize_col(header)
        if ncol in ("phone", "name", "lead_phone", "lead_name"):
            continue
        if not _column_present(col_map, field):
            errors.append(f"Missing required column: {header}")

    return errors

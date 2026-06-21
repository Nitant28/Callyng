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


def validate_dataframe(df: pd.DataFrame, lead_schema: dict) -> list[str]:
    errors: list[str] = []
    if df is None or df.empty:
        errors.append("Upload file is empty")
        return errors

    col_map = {_normalize_col(c): c for c in df.columns}

    if "phone" not in col_map:
        errors.append("Missing required column: phone")

    fields = extract_lead_fields(lead_schema)
    for field in fields:
        if not field.get("required"):
            continue
        csv_col = field.get("csv_column") or field.get("key")
        ncol = _normalize_col(csv_col)
        if ncol in ("phone", "name", "lead_phone", "lead_name"):
            continue
        if ncol not in col_map:
            errors.append(f"Missing required column: {csv_col}")

    return errors

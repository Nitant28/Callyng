"""Validate uploaded lead DataFrames against script LEAD_SCHEMA."""

from __future__ import annotations

import pandas as pd


def _normalize_col(name: str) -> str:
    return (name or "").strip().lower()


def validate_dataframe(df: pd.DataFrame, lead_schema: dict) -> list[str]:
    errors: list[str] = []
    if df is None or df.empty:
        errors.append("Upload file is empty")
        return errors

    col_map = {_normalize_col(c): c for c in df.columns}

    if "phone" not in col_map:
        errors.append("Missing required column: phone")

    fields = lead_schema.get("fields") or []
    for field in fields:
        if not field.get("required"):
            continue
        csv_col = field.get("csv_column") or field.get("key")
        if _normalize_col(csv_col) not in col_map:
            errors.append(f"Missing required column: {csv_col}")

    return errors

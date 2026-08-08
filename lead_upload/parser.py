"""Parse CSV and Excel (.xlsx, .xls) uploads into a string-typed DataFrame."""

from __future__ import annotations

from typing import BinaryIO

import pandas as pd


def parse_upload(file: BinaryIO, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(file, dtype=str)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(file, dtype=str, engine="openpyxl")
    raise ValueError("Only CSV and Excel (.xlsx, .csv) files are supported")

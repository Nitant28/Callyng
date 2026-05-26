"""Parse CSV/Excel uploads into a string-typed DataFrame."""

from __future__ import annotations

import io
from typing import BinaryIO

import pandas as pd


def parse_upload(file: BinaryIO, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(file, dtype=str, engine="openpyxl")
    raw = file.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        text = raw
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)

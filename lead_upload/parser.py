"""Parse Excel (.xlsx) uploads into a string-typed DataFrame."""

from __future__ import annotations

from typing import BinaryIO

import pandas as pd


def parse_upload(file: BinaryIO, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if not (name.endswith(".xlsx") or name.endswith(".xls")):
        raise ValueError("Only Excel (.xlsx) files are supported")
    return pd.read_excel(file, dtype=str, engine="openpyxl")

#!/usr/bin/env python3
"""Print Plivo prepaid cash_credits (USD)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env", override=True)


async def main() -> None:
    import aiohttp
    from telephony import fetch_plivo_cash_credits

    async with aiohttp.ClientSession() as session:
        balance = await fetch_plivo_cash_credits(session)
    print(f"Plivo cash_credits (USD): {balance}")


if __name__ == "__main__":
    asyncio.run(main())

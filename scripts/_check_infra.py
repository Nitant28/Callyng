import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

async def main():
    base = (os.getenv("NGROK_URL") or "").strip().rstrip("/")
    print("NGROK_URL:", base or "(empty)")
    if not base:
        return
    url = f"{base}/answer?call_id=health-check"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                body = await r.text()
                print("status:", r.status)
                print("has Stream:", "<Stream" in body)
                print(body[:500])
    except Exception as e:
        print("ERROR:", e)

    from telephony import fetch_plivo_cash_credits
    try:
        async with aiohttp.ClientSession() as s:
            bal = await fetch_plivo_cash_credits(s)
            print("Plivo USD:", bal)
    except Exception as e:
        print("Plivo ERROR:", e)

asyncio.run(main())

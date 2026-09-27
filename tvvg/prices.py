"""
Daily Steam prices, including sales.

Source: https://store.steampowered.com/api/appdetails (public, no key)
Asking for many games in one request only works with filters=price_overview,
which returns the current price, the regular price and the discount %.
Prices are US dollars (cc=us), in cents.
"""

import time
import requests

URL = "https://store.steampowered.com/api/appdetails"
HEADERS = {"User-Agent": "DemystifyPriceBot/0.1 (personal research project)"}
BATCH = 50
SLEEP = 1.6
BACKOFF_ON_429 = 300


def _batch(ids):
    """Return (dict_or_None, rate_limited)."""
    try:
        r = requests.get(URL, params={"appids": ",".join(ids), "cc": "us",
                                      "filters": "price_overview"},
                         headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None, False
    if r.status_code == 429:
        return None, True
    if r.status_code != 200:
        return None, False
    try:
        return r.json() or {}, False
    except ValueError:
        return None, False


def parse(item):
    """Turn one appdetails item into a price record, or None if not for sale."""
    if not item or not item.get("success"):
        return None
    data = item.get("data")
    po = data.get("price_overview") if isinstance(data, dict) else None
    if not po or po.get("currency") != "USD":
        return None  # free, not sold, or no US price
    return {"final": int(po.get("final") or 0),
            "initial": int(po.get("initial") or 0),
            "discount": int(po.get("discount_percent") or 0)}


def fetch_prices(appids, budget_minutes: float) -> dict:
    """Return {appid: {"final", "initial", "discount"}} for games on sale in the US store."""
    deadline = time.monotonic() + budget_minutes * 60
    prices = {}
    batches = [appids[i:i + BATCH] for i in range(0, len(appids), BATCH)]
    print(f"  Prices: {len(appids)} games in {len(batches)} requests, budget {budget_minutes:.0f} min")
    for i, ids in enumerate(batches):
        if time.monotonic() > deadline:
            print(f"  Prices: time budget reached after {i} requests")
            break
        body, limited = _batch(ids)
        if limited:
            print("  Steam rate limit hit, pausing 5 minutes")
            time.sleep(BACKOFF_ON_429)
            body, limited = _batch(ids)
        if body:
            for appid in ids:
                rec = parse(body.get(appid))
                if rec:
                    prices[appid] = rec
        time.sleep(SLEEP)
    print(f"  Prices: got {len(prices)} prices")
    return prices

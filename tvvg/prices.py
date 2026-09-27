"""
Daily Steam prices, including sales.

Source: https://store.steampowered.com/api/appdetails (public, no key)
Prices are US dollars (cc=us), in cents.

Pass 1 (fast): ask for 50 games per request with filters=price_overview.
  If Steam rejects a batch, split it in half and retry, so one bad game
  can't wipe out the prices of the other 49.
Pass 2 (careful): games that came back with no price get a full lookup,
  which tells us whether they are free, sold only as editions/bundles
  (price comes from the cheapest edition), or genuinely not for sale.
  Games already known to be free are skipped.
"""

import time
import requests

URL = "https://store.steampowered.com/api/appdetails"
HEADERS = {"User-Agent": "DemystifyPriceBot/0.1 (personal research project)"}
BATCH = 50
SLEEP = 1.6
BACKOFF_ON_429 = 300


def _get(params):
    """Return (dict_or_None, rate_limited)."""
    try:
        r = requests.get(URL, params=params, headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None, False
    if r.status_code == 429:
        return None, True
    if r.status_code != 200:
        return None, False
    try:
        body = r.json()
    except ValueError:
        return None, False
    return (body if isinstance(body, dict) else None), False


def _from_packages(data):
    """Cheapest paid edition, for games sold only as editions or bundles."""
    best = None
    for group in data.get("package_groups") or []:
        for sub in group.get("subs") or []:
            if sub.get("is_free_license"):
                continue
            final = sub.get("price_in_cents_with_discount")
            if not final or final <= 0:
                continue
            if best is None or final < best["final"]:
                pct = int(sub.get("percent_savings") or 0)
                initial = round(final / (1 - pct / 100)) if 0 < pct < 100 else final
                best = {"final": int(final), "initial": int(initial), "discount": pct}
    return best


def parse(item):
    """Turn one appdetails item into a price record, or None if no price."""
    if not item or not item.get("success"):
        return None
    data = item.get("data")
    if not isinstance(data, dict):
        return None  # batch mode returns [] for games without a price
    po = data.get("price_overview")
    if po and po.get("currency") == "USD" and po.get("final"):
        return {"final": int(po["final"]),
                "initial": int(po.get("initial") or po["final"]),
                "discount": int(po.get("discount_percent") or 0)}
    if data.get("is_free"):
        return None
    return _from_packages(data)


def fetch_prices(appids, budget_minutes: float, cache: dict):
    """
    Return (prices, not_for_sale):
      prices       {appid: {"final", "initial", "discount"}}
      not_for_sale set of appids confirmed to have no price today
    Also records cache[appid]["free"] when a full lookup finds a free game.
    """
    deadline = time.monotonic() + budget_minutes * 60
    prices, not_for_sale, failed = {}, set(), 0

    def wait_if_limited(limited):
        if limited:
            print("  Steam rate limit hit, pausing 5 minutes")
            time.sleep(BACKOFF_ON_429)
        return limited

    # ---- Pass 1: batches, split on failure ---------------------------------
    queue = [appids[i:i + BATCH] for i in range(0, len(appids), BATCH)]
    print(f"  Prices: {len(appids)} games, budget {budget_minutes:.0f} min")
    while queue and time.monotonic() < deadline:
        ids = queue.pop(0)
        body, limited = _get({"appids": ",".join(ids), "cc": "us", "filters": "price_overview"})
        time.sleep(SLEEP)
        if wait_if_limited(limited):
            queue.insert(0, ids)
            continue
        if body is None:
            if len(ids) > 1:
                half = len(ids) // 2
                queue[:0] = [ids[:half], ids[half:]]
            else:
                failed += 1
            continue
        for appid in ids:
            rec = parse(body.get(appid))
            if rec:
                prices[appid] = rec

    # ---- Pass 2: full lookups for games with no price -----------------------
    missing = [a for a in appids if a not in prices
               and not (cache.get(a) or {}).get("free")]
    checked = 0
    for appid in missing:
        if time.monotonic() > deadline:
            break
        body, limited = _get({"appids": appid, "cc": "us", "l": "en"})
        time.sleep(SLEEP)
        if wait_if_limited(limited) or body is None:
            continue
        item = body.get(appid) or {}
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        checked += 1
        if appid in cache and item.get("success"):
            cache[appid]["free"] = bool(data.get("is_free"))
        rec = parse(item)
        if rec:
            prices[appid] = rec
        elif item.get("success") and not data.get("is_free"):
            not_for_sale.add(appid)

    print(f"  Prices: {len(prices)} priced, {len(not_for_sale)} not for sale, "
          f"{checked} full lookups, {failed} games Steam wouldn't answer for, "
          f"{len(missing) - checked} left for tomorrow")
    return prices, not_for_sale

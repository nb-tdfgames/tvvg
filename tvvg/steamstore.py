"""
Steam store lookups: gameplay hours (H), user reviews (Pu, n), critic score (Pc).

Sources (both public, no key needed):
  https://store.steampowered.com/api/appdetails  -> Metacritic score, app type
  https://store.steampowered.com/appreviews/<id> -> review totals + each
                                                    reviewer's hours played

H = median total hours played by up to 100 reviewers of the game
    (Steam's "most helpful" reviews, reviewers with 0 hours ignored).

Steam rate-limits these lookups, so each run spends a fixed time budget
checking games it hasn't checked yet (most-reviewed first) and saves the
results to a cache file. Cached results are refreshed every RECHECK_DAYS.
"""

import json
import statistics
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

DETAILS_URL = "https://store.steampowered.com/api/appdetails"
REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
HEADERS = {"User-Agent": "TVVG-TrueValueBot/0.1 (personal research project)"}
SLEEP_DETAILS = 1.6     # appdetails allows roughly 200 calls per 5 minutes
SLEEP_REVIEWS = 1.0
BACKOFF_ON_429 = 300    # if Steam says "slow down", wait 5 minutes
RECHECK_DAYS = 30
REVIEW_SAMPLE = 100


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")


def _needs_check(entry, now) -> bool:
    if entry is None or "h_sample" not in entry:   # new, or from the old version
        return True
    checked = datetime.fromisoformat(entry["checked"])
    return now - checked > timedelta(days=RECHECK_DAYS)


def _get(url, params):
    """Return (json_or_None, rate_limited)."""
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None, False
    if r.status_code == 429:
        return None, True
    if r.status_code != 200:
        return None, False
    try:
        return r.json(), False
    except ValueError:
        return None, False


def _details(appid):
    body, limited = _get(DETAILS_URL, {"appids": appid, "cc": "us", "l": "en"})
    if body is None:
        return None, limited
    item = body.get(appid) or {}
    data = item.get("data") or {}
    mc = data.get("metacritic") or {}
    return {"ok": bool(item.get("success")), "type": data.get("type"),
            "metacritic": mc.get("score"), "img": data.get("header_image")}, False


def _reviews(appid):
    body, limited = _get(REVIEWS_URL.format(appid=appid), {
        "json": 1, "language": "all", "purchase_type": "all", "filter": "all",
        "num_per_page": REVIEW_SAMPLE, "cursor": "*"})
    if body is None or body.get("success") != 1:
        return None, limited
    qs = body.get("query_summary") or {}
    hours = [rv.get("author", {}).get("playtime_forever", 0) for rv in body.get("reviews", [])]
    hours = [m for m in hours if m and m > 0]
    return {"pos": int(qs.get("total_positive") or 0),
            "neg": int(qs.get("total_negative") or 0),
            "h_median_min": statistics.median(hours) if hours else None,
            "h_sample": len(hours)}, False


def update_cache(appids_by_priority, cache: dict, budget_minutes: float,
                 cache_path: Path, excluded_types: set) -> int:
    """Check as many un-checked games as fit in the time budget."""
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + budget_minutes * 60
    todo = [a for a in appids_by_priority if _needs_check(cache.get(a), now)]
    print(f"  Steam lookups: {len(todo)} games still to check, budget {budget_minutes:.0f} min")
    done = 0
    for appid in todo:
        if time.monotonic() > deadline:
            break
        det, limited = _details(appid)
        time.sleep(SLEEP_DETAILS)
        if limited:
            print("  Steam rate limit hit, pausing 5 minutes")
            time.sleep(BACKOFF_ON_429)
            continue
        if det is None:
            continue  # network hiccup; try again next run
        entry = {**det, "checked": now.isoformat()}
        if not det["ok"] or det["type"] in excluded_types:
            entry.update(pos=None, neg=None, h_median_min=None, h_sample=0)
        else:
            rev, limited = _reviews(appid)
            time.sleep(SLEEP_REVIEWS)
            if limited:
                print("  Steam rate limit hit, pausing 5 minutes")
                time.sleep(BACKOFF_ON_429)
                continue
            if rev is None:
                continue
            entry.update(rev)
        cache[appid] = entry
        done += 1
        if done % 250 == 0:
            save_cache(cache, cache_path)  # checkpoint
            print(f"  Steam lookups: checked {done}")
    save_cache(cache, cache_path)
    print(f"  Steam lookups: checked {done} this run")
    return done

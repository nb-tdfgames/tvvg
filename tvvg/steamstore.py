"""
Critic score (Pc) fetcher using the Steam Store's appdetails endpoint.

Source: https://store.steampowered.com/api/appdetails  (public, no key)
Steam includes the Metacritic score for games that have one.

This endpoint is rate-limited (roughly 200 requests per 5 minutes), so a
full pass over ~100k games takes many days. Instead of trying to do it all
at once, each run spends a fixed time budget checking games it hasn't
checked yet (most-reviewed first), and saves results to a cache file.
Critic scores almost never change, so cached results are re-checked
only every RECHECK_DAYS.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

URL = "https://store.steampowered.com/api/appdetails"
HEADERS = {"User-Agent": "TVVG-TrueValueBot/0.1 (personal research project)"}
SECONDS_BETWEEN_CALLS = 1.6   # ~187 calls / 5 min, just under Steam's limit
BACKOFF_ON_429 = 300          # if Steam says "slow down", wait 5 minutes
RECHECK_DAYS = 90


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")


def _needs_check(entry, now) -> bool:
    if entry is None:
        return True
    checked = datetime.fromisoformat(entry["checked"])
    return now - checked > timedelta(days=RECHECK_DAYS)


def _lookup(appid: str):
    """Return (entry, rate_limited)."""
    try:
        r = requests.get(URL, params={"appids": appid, "cc": "us", "l": "en"},
                         headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None, False
    if r.status_code == 429:
        return None, True
    if r.status_code != 200:
        return None, False
    try:
        body = r.json().get(appid) or {}
    except ValueError:
        return None, False
    data = body.get("data") or {}
    mc = data.get("metacritic") or {}
    return {
        "metacritic": mc.get("score"),        # None if the game has no score
        "type": data.get("type"),             # "game", "dlc", "demo", ...
        "ok": bool(body.get("success")),
    }, False


def update_cache(appids_by_priority, cache: dict, budget_minutes: float,
                 cache_path: Path) -> int:
    """Check as many un-checked games as fit in the time budget."""
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + budget_minutes * 60
    todo = [a for a in appids_by_priority if _needs_check(cache.get(a), now)]
    print(f"  Critic scores: {len(todo)} games still to check, "
          f"budget {budget_minutes:.0f} min")
    done = 0
    for appid in todo:
        if time.monotonic() > deadline:
            break
        entry, limited = _lookup(appid)
        if limited:
            print("  Steam rate limit hit, pausing 5 minutes")
            time.sleep(BACKOFF_ON_429)
            continue
        if entry is not None:
            entry["checked"] = now.isoformat()
            cache[appid] = entry
            done += 1
            if done % 500 == 0:
                save_cache(cache, cache_path)  # checkpoint
                print(f"  Critic scores: checked {done}")
        time.sleep(SECONDS_BETWEEN_CALLS)
    save_cache(cache, cache_path)
    print(f"  Critic scores: checked {done} this run")
    return done

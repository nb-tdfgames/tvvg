"""
SteamSpy bulk catalog fetcher.

Source: https://steamspy.com/api.php  (public, no key required)
Rules from SteamSpy's docs: the "all" request is limited to 1 call per 60
seconds and returns 1,000 games per page. Data refreshes once a day.

Gives us, for every game:
  positive, negative        -> Pu (user %) and n (review count)
  median_forever (minutes)  -> H (gameplay hours) proxy
  average_forever (minutes) -> alternate H proxy
"""

import time
import requests

URL = "https://steamspy.com/api.php"
HEADERS = {"User-Agent": "TVVG-TrueValueBot/0.1 (personal research project)"}
SECONDS_BETWEEN_PAGES = 62  # SteamSpy allows 1 "all" request per 60s
MAX_PAGES = 400             # safety stop; the real catalog ends well before this


def _get_page(page: int, retries: int = 4):
    for attempt in range(retries):
        try:
            r = requests.get(URL, params={"request": "all", "page": page},
                             headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.json()
            print(f"  SteamSpy page {page}: HTTP {r.status_code}, retrying")
        except (requests.RequestException, ValueError) as e:
            print(f"  SteamSpy page {page}: {e}, retrying")
        time.sleep(SECONDS_BETWEEN_PAGES)
    return None


def fetch_all(max_pages: int = MAX_PAGES) -> dict:
    """Return {appid(str): record} for the whole SteamSpy catalog."""
    games = {}
    for page in range(max_pages):
        data = _get_page(page)
        if not data:  # empty page (or repeated failure) = end of catalog
            print(f"  SteamSpy: stopped at page {page}")
            break
        for appid, rec in data.items():
            games[str(appid)] = {
                "name": rec.get("name") or "",
                "positive": int(rec.get("positive") or 0),
                "negative": int(rec.get("negative") or 0),
                "median_forever": int(rec.get("median_forever") or 0),
                "average_forever": int(rec.get("average_forever") or 0),
            }
        print(f"  SteamSpy page {page}: +{len(data)} (total {len(games)})")
        if len(data) < 1000:  # a short page is the last page
            break
        time.sleep(SECONDS_BETWEEN_PAGES)
    return games

"""
Demystify Price daily build.

  1. Pull the list of Steam games from SteamSpy.
  2. Get today's Steam prices (including sales) for every game we can score.
  3. Spend a time budget looking up playtime, reviews and critic scores
     from the Steam store, most-reviewed games first (cached between runs).
  4. Run every game through the frozen v0.1 formula (tvvg/formula.py).
  5. Write docs/games.json (the website) and docs/games.csv (spreadsheet).

Only what the website displays is published. The formula's internal values
never leave this script.

Quick local test:  python -m tvvg.build --max-pages 1 --critic-minutes 3
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import formula, prices, steamspy, steamstore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs"
CRITIC_CACHE = ROOT / "data" / "critic_cache.json"

# ---------------------------------------------------------------------------
# DATA DECISIONS: choices about inputs, not changes to the formula.
# ---------------------------------------------------------------------------

# H (gameplay hours) = median hours played by up to 100 Steam reviewers.
# Games whose median comes from fewer reviewers than this get a note.
SMALL_SAMPLE_FLAG = 20

# What to do when a game has no critic score (most indie games don't).
#   "use_user" = treat Pc as equal to Pu, so Q = Pu
#   "skip"     = don't score the game at all
MISSING_CRITIC_RULE = "use_user"

# Games with fewer reviews than this get a note on the site.
LOW_REVIEW_FLAG = 50

EXCLUDED_TYPES = {"dlc", "demo", "music", "video", "episode", "series",
                  "mod", "advertising", "hardware"}

FIELDS = ["appid", "name", "fair", "price", "was", "off", "free",
          "content", "quality", "H", "Pc", "Pu", "n", "notes", "img"]


def scoreable(info) -> bool:
    return bool(info and info.get("ok") and info.get("h_median_min")
                and info.get("type") not in EXCLUDED_TYPES)


def score_game(appid, rec, info, price=None):
    """Return (row, None) or (None, reason) if the game can't be scored."""
    if info is None or "h_sample" not in info:
        return None, "not_checked_yet"
    if info.get("type") in EXCLUDED_TYPES:
        return None, "not_a_game"
    if not info.get("ok"):
        return None, "not_on_store"
    if not info.get("h_median_min"):
        return None, "no_playtime"

    hours = info["h_median_min"] / 60.0
    n = info["pos"] + info["neg"]
    pu = (info["pos"] / n * 100.0) if n > 0 else None
    pc = info.get("metacritic")

    notes = []
    if pc is None:
        if MISSING_CRITIC_RULE == "skip" or pu is None:
            return None, "no_quality_data"
        pc_used = pu
        notes.append("No critic score yet, so player reviews carry the quality rating.")
    else:
        pc_used = float(pc)
    if pu is None:
        pu = 0.0  # carries no weight when there are no reviews
    if n < LOW_REVIEW_FLAG:
        notes.append("Only a handful of player reviews so far, so this value may shift.")
    if info["h_sample"] < SMALL_SAMPLE_FLAG:
        notes.append("Playtime is based on only a few players.")

    r = formula.true_value(hours, pc_used, pu, n)
    row = {
        "appid": int(appid),
        "name": rec["name"],
        "fair": round(r["TV"], 2),
        "price": None, "was": None, "off": 0,
        "free": bool(info.get("free")),
        # plain 1-10 ratings for display only
        "content": max(1, min(10, round(r["C"] / 10))),
        "quality": max(1, min(10, round(r["Q"] / 10))),
        "H": round(hours, 1),
        "Pc": pc,
        "Pu": round(pu, 1) if n > 0 else None,
        "n": n,
        "notes": " ".join(notes),
        "img": info.get("img"),
    }
    if price and price["final"] > 0:
        row["price"] = round(price["final"] / 100, 2)
        row["off"] = price["discount"]
        if price["discount"] > 0:
            row["was"] = round(price["initial"] / 100, 2)
        row["free"] = False
    return row, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=steamspy.MAX_PAGES,
                    help="limit SteamSpy pages (1 page = 1,000 games)")
    ap.add_argument("--critic-minutes", type=float, default=180,
                    help="minutes to spend on Steam store lookups this run")
    ap.add_argument("--price-minutes", type=float, default=50,
                    help="minutes to spend fetching today's prices")
    args = ap.parse_args()

    print("Step 1/5: downloading the Steam game list from SteamSpy")
    catalog = steamspy.fetch_all(max_pages=args.max_pages)
    if not catalog:
        raise SystemExit("SteamSpy returned nothing; keeping yesterday's data.")
    by_reviews = sorted(catalog, key=lambda a: -(catalog[a]["positive"] + catalog[a]["negative"]))
    cache = steamstore.load_cache(CRITIC_CACHE)

    print("Step 2/5: getting today's Steam prices")
    priceable = [a for a in by_reviews if scoreable(cache.get(a))]
    todays = prices.fetch_prices(priceable, args.price_minutes)

    print("Step 3/5: looking up playtime, reviews and critic scores on Steam")
    steamstore.update_cache(by_reviews, cache, args.critic_minutes, CRITIC_CACHE, EXCLUDED_TYPES)

    print("Step 4/5: running the v0.1 formula")
    today = datetime.now(timezone.utc).date().isoformat()
    rows, skipped = [], {}
    for appid, rec in catalog.items():
        info = cache.get(appid)
        price = todays.get(appid)
        if price is None and info and info.get("checked", "").startswith(today):
            price = info.get("price")  # looked up today in step 3
        row, reason = score_game(appid, rec, info, price)
        if row:
            rows.append(row)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
    rows.sort(key=lambda r: -r["n"])

    print("Step 5/5: writing results")
    write_outputs(rows, len(catalog))
    print(f"Done: {len(rows)} games scored, {sum(1 for r in rows if r['price'])} with prices, skipped {skipped}")


def write_outputs(rows, catalog_size):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": len(rows),
        "catalog_size": catalog_size,
    }
    payload = {"meta": meta, "fields": FIELDS,
               "rows": [[r[f] for f in FIELDS] for r in rows]}
    (OUT_DIR / "games.json").write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    cols = ["appid", "name", "price", "was", "off", "free", "fair",
            "content", "quality", "H", "Pc", "Pu", "n", "notes"]
    with open(OUT_DIR / "games.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()

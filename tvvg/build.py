"""
TVVG daily build.

  1. Pull the list of Steam games from SteamSpy.
  2. Spend a time budget looking up playtime, reviews and critic scores
     from the Steam store, most-reviewed games first (cached between runs).
  3. Run every game through the frozen v0.1 formula.
  4. Write docs/games.json (for the search page) and docs/games.csv (for Excel).

Run locally for a quick test:
    python -m tvvg.build --max-pages 1 --critic-minutes 3
Full run (what the daily automation does):
    python -m tvvg.build
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import formula, steamspy, steamstore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs"
CRITIC_CACHE = ROOT / "data" / "critic_cache.json"

# ---------------------------------------------------------------------------
# DATA DECISIONS — these are choices about INPUTS, not changes to the formula.
# Each one is a knob you can change after looking at the results.
# ---------------------------------------------------------------------------

# H (gameplay hours) = median hours played by up to 100 Steam reviewers.
# Games whose median comes from fewer reviewers than this get a flag.
SMALL_SAMPLE_FLAG = 20

# What to do when a game has no critic score (most indie games don't).
#   "use_user" = treat Pc as equal to Pu, so Q = Pu
#   "skip"     = don't score the game at all
MISSING_CRITIC_RULE = "use_user"

# Games with fewer reviews than this get a "low reviews" flag on the site.
LOW_REVIEW_FLAG = 50

# Steam store types we exclude once we know them (unknown type is kept).
EXCLUDED_TYPES = {"dlc", "demo", "music", "video", "episode", "series",
                  "mod", "advertising", "hardware"}


def score_game(appid, rec, info):
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

    flags = []
    if pc is None:
        if MISSING_CRITIC_RULE == "skip" or pu is None:
            return None, "no_quality_data"
        pc_used = pu
        flags.append("no critic score")
    else:
        pc_used = float(pc)
    if pu is None:
        pu = 0.0  # weight is zero anyway: with n=0, Cf=0 so Q = Pc
    if n < LOW_REVIEW_FLAG:
        flags.append("low reviews")
    if info["h_sample"] < SMALL_SAMPLE_FLAG:
        flags.append(f"hours from only {info['h_sample']} reviewers")

    r = formula.true_value(hours, pc_used, pu, n)
    return {
        "appid": int(appid),
        "name": rec["name"],
        "TV": round(r["TV"], 2),
        "C": round(r["C"], 2),
        "QM": round(r["QM"], 4),
        "Q": round(r["Q"], 2),
        "H": round(hours, 1),
        "Pc": pc,
        "Pu": round(pu, 1) if n > 0 else None,
        "n": n,
        "flags": ", ".join(flags),
        "img": info.get("img"),
    }, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=steamspy.MAX_PAGES,
                    help="limit SteamSpy pages (1 page = 1,000 games)")
    ap.add_argument("--critic-minutes", type=float, default=180,
                    help="minutes to spend on Steam store lookups this run")
    args = ap.parse_args()

    print("Step 1/4: downloading Steam catalog from SteamSpy")
    catalog = steamspy.fetch_all(max_pages=args.max_pages)
    if not catalog:
        raise SystemExit("SteamSpy returned nothing; keeping yesterday's data.")

    print("Step 2/4: looking up playtime, reviews and critic scores on Steam")
    cache = steamstore.load_cache(CRITIC_CACHE)
    # most-reviewed first; ties keep SteamSpy's order (most owners first)
    by_reviews = sorted(catalog, key=lambda a: -(catalog[a]["positive"] + catalog[a]["negative"]))
    steamstore.update_cache(by_reviews, cache, args.critic_minutes, CRITIC_CACHE, EXCLUDED_TYPES)

    print("Step 3/4: running the v0.1 formula")
    rows, skipped = [], {}
    for appid, rec in catalog.items():
        row, reason = score_game(appid, rec, cache.get(appid))
        if row:
            rows.append(row)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
    rows.sort(key=lambda r: -r["n"])

    print("Step 4/4: writing results")
    write_outputs(rows, skipped, len(catalog), cache)
    print(f"Done: {len(rows)} games scored, skipped {skipped}")


def write_outputs(rows, skipped, catalog_size, cache):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = ["appid", "name", "TV", "C", "QM", "Q", "H", "Pc", "Pu", "n", "flags", "img"]

    meta = {
        "updated": now,
        "algorithm_version": formula.ALGORITHM_VERSION,
        "catalog_size": catalog_size,
        "scored": len(rows),
        "skipped": skipped,
        "critic_checked": len(cache),
        "critic_found": sum(1 for v in cache.values() if v.get("metacritic") is not None),
        "settings": {"H": "median hours of Steam reviewers", "MISSING_CRITIC_RULE": MISSING_CRITIC_RULE},
    }
    payload = {"meta": meta, "fields": fields,
               "rows": [[r[f] for f in fields] for r in rows]}
    (OUT_DIR / "games.json").write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    with open(OUT_DIR / "games.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()

import math
from tvvg import formula as f
from tvvg import build


def close(a, b, tol=1e-6):
    return math.isclose(a, b, abs_tol=tol)


def test_modifier_endpoints_match_spec():
    assert close(f.quality_modifier(70), 1.00)    # baseline
    assert close(f.quality_modifier(100), 1.15)   # max bonus +15%
    assert close(f.quality_modifier(0), 0.50)     # max penalty -50%


def test_confidence_factor():
    assert close(f.confidence_factor(0), 0.0)     # max(n,1) guard
    assert close(f.confidence_factor(1), 0.0)
    assert close(f.confidence_factor(10), 0.5)
    assert close(f.confidence_factor(10_000), 0.8)


def test_content_curve():
    assert close(f.content_score(0), 0.0)
    assert f.content_score(10) < f.content_score(50) < f.content_score(200) < 100
    # diminishing returns: 0->50h gains more than 50->100h
    assert (f.content_score(50) - f.content_score(0)) > (f.content_score(100) - f.content_score(50))


def test_worked_example():
    # H=50, Pc=90, Pu=85, n=10,000  ->  Cf=0.8, Q=86
    r = f.true_value(50, 90, 85, 10_000)
    assert close(r["Cf"], 0.8)
    assert close(r["Q"], 86.0)
    assert close(r["QM"], 1 + 0.15 * (16 / 30) ** 1.5)
    assert close(r["C"], 100 * (1 - math.exp(-((50 / 85) ** 0.65))))
    assert close(r["TV"], r["C"] * r["QM"])


def test_score_game_rules():
    rec = {"name": "X", "positive": 0, "negative": 0}
    info = {"ok": True, "type": "game", "metacritic": 80, "pos": 900, "neg": 100,
            "h_median_min": 600, "h_sample": 100, "free": False,
            "checked": "2026-01-01T00:00:00+00:00"}
    row, _ = build.score_game("1", rec, info)
    expect = f.true_value(10, 80, 90, 1000)["TV"]
    assert row["H"] == 10.0 and row["Pc"] == 80 and row["n"] == 1000
    assert close(row["fair"], round(expect, 2), 0.001)
    assert row["price"] is None and 1 <= row["content"] <= 10 and 1 <= row["quality"] <= 10
    # formula internals are never published
    assert not {"TV", "C", "Q", "QM", "Cf"} & set(row)
    # sale price is carried through
    row, _ = build.score_game("1", rec, info, {"final": 1499, "initial": 2999, "discount": 50})
    assert row["price"] == 14.99 and row["was"] == 29.99 and row["off"] == 50
    # no critic score -> uses player reviews, with a note
    row, _ = build.score_game("1", rec, {**info, "metacritic": None})
    assert close(row["fair"], round(f.true_value(10, 90, 90, 1000)["TV"], 2), 0.001)
    assert "No critic score" in row["notes"]
    # small playtime sample gets a note
    row, _ = build.score_game("1", rec, {**info, "h_sample": 5})
    assert "only a few players" in row["notes"]
    # can't score
    assert build.score_game("1", rec, {**info, "h_median_min": None, "h_sample": 0}) == (None, "no_playtime")
    assert build.score_game("1", rec, None) == (None, "not_checked_yet")
    assert build.score_game("1", rec, {**info, "type": "dlc"}) == (None, "not_a_game")


def test_price_parsing():
    from tvvg.prices import parse
    item = {"success": True, "data": {"price_overview": {"currency": "USD", "initial": 5999, "final": 3599, "discount_percent": 40}}}
    assert parse(item) == {"final": 3599, "initial": 5999, "discount": 40}
    assert parse({"success": True, "data": []}) is None      # free game in batch mode
    assert parse({"success": False}) is None

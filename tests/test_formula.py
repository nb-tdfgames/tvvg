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
            "h_median_min": 600, "h_sample": 100, "checked": "2026-01-01T00:00:00+00:00"}
    row, _ = build.score_game("1", rec, info)
    assert row["H"] == 10.0 and row["Pc"] == 80 and row["n"] == 1000
    # no critic score -> Q equals Pu under the "use_user" rule
    row, _ = build.score_game("1", rec, {**info, "metacritic": None})
    assert close(row["Q"], 90.0, 0.01) and "no critic score" in row["flags"]
    # small playtime sample is flagged
    row, _ = build.score_game("1", rec, {**info, "h_sample": 5})
    assert "only 5 reviewers" in row["flags"]
    # no playtime -> not scored
    row, why = build.score_game("1", rec, {**info, "h_median_min": None, "h_sample": 0})
    assert row is None and why == "no_playtime"
    # not looked up yet -> not scored
    row, why = build.score_game("1", rec, None)
    assert row is None and why == "not_checked_yet"
    # DLC -> not scored
    row, why = build.score_game("1", rec, {**info, "type": "dlc"})
    assert row is None and why == "not_a_game"

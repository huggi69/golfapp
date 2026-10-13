from fractions import Fraction

from golfapp.scoring import evaluate_round, format_points, match_status

A, B = 1, 2


def make_holes(pars, ntp=None):
    ntp = ntp or {}
    return [{"hole": i + 1, "par": p, "ntp_player_id": ntp.get(i + 1)} for i, p in enumerate(pars)]


def make_scores(data):
    """data: player -> list of (strokes, putts, net)"""
    return {
        (pid, i + 1): {"strokes": s, "putts": p, "net_points": n}
        for pid, rows in data.items()
        for i, (s, p, n) in enumerate(rows)
    }


def cat(result, key):
    return next(c for c in result.categories if c.key == key)


def test_incomplete_round_is_not_scored():
    holes = make_holes([4, 3])
    scores = make_scores({A: [(4, 2, 2), (3, 1, 2)], B: [(5, 2, 1)]})
    result = evaluate_round([A, B], holes, scores)
    assert not result.complete
    assert result.missing == 3


def test_each_category_awards_one_point():
    holes = make_holes([4, 3, 5], ntp={2: B})
    scores = make_scores({
        A: [(4, 2, 2), (3, 2, 2), (5, 2, 2)],   # 12 Schläge, 6 Putts, 6 Netto
        B: [(5, 1, 2), (4, 1, 1), (6, 1, 2)],   # 15 Schläge, 3 Putts, 5 Netto
    })
    r = evaluate_round([A, B], holes, scores, "net")
    assert r.complete
    assert cat(r, "match").values == {A: 1, B: 0}
    assert cat(r, "match").winners == [A]
    assert cat(r, "gross").winners == [A]
    assert cat(r, "net").winners == [A]
    assert cat(r, "putts").winners == [B]
    assert cat(r, "ntp").winners == [B]
    assert r.points == {A: 3, B: 2}


def test_tie_awards_no_point():
    holes = make_holes([4, 4])
    scores = make_scores({A: [(4, 2, 2), (5, 2, 1)], B: [(5, 2, 1), (4, 2, 2)]})
    r = evaluate_round([A, B], holes, scores)
    for key in ("match", "gross", "net", "putts"):
        assert cat(r, key).winners == []
        assert cat(r, key).tied
        assert cat(r, key).points == {A: 0, B: 0}
    # Kein Par 3 -> kein NTP-Punkt
    assert cat(r, "ntp").winners == []
    assert not cat(r, "ntp").tied
    assert r.points == {A: 0, B: 0}


def test_tie_for_first_among_three_players():
    C = 3
    holes = make_holes([4])
    scores = make_scores({A: [(4, 2, 2)], B: [(4, 1, 2)], C: [(6, 2, 0)]})
    r = evaluate_round([A, B, C], holes, scores)
    assert cat(r, "gross").winners == [] and cat(r, "gross").tied
    assert cat(r, "putts").winners == [B]


def test_gross_match_play_basis():
    holes = make_holes([4, 4])
    # A gewinnt netto beide Löcher (Handicap), B ist brutto besser
    scores = make_scores({A: [(5, 2, 2), (5, 2, 2)], B: [(4, 2, 1), (4, 2, 1)]})
    assert cat(evaluate_round([A, B], holes, scores, "net"), "match").winners == [A]
    assert cat(evaluate_round([A, B], holes, scores, "gross"), "match").winners == [B]


def test_match_status_and_formatting():
    assert match_status({A: 5, B: 2}, {A: "Anna", B: "Ben"}) == "Anna 3 auf"
    assert match_status({A: 2, B: 2}, {A: "Anna", B: "Ben"}) == "All Square"
    assert format_points(Fraction(5, 2)) == "2½"
    assert format_points(Fraction(1, 2)) == "½"
    assert format_points(Fraction(3)) == "3"

from golfapp.handicap import playing_handicap, stableford_points, strokes_received

SI_18 = dict(zip(range(1, 19), [7, 11, 15, 1, 3, 13, 17, 9, 5, 8, 12, 16, 2, 4, 14, 18, 10, 6]))


def test_playing_handicap_18_holes():
    # 18,4 × 136/113 + (71,9 − 72) = 22,04 -> 22
    assert playing_handicap(18.4, 71.9, 136, 72) == 22
    # x,5 wird aufgerundet: 0 × … + (72,5 − 72) = 0,5 -> 1
    assert playing_handicap(0, 72.5, 113, 72) == 1
    assert playing_handicap(None, 71.9, 136, 72) is None


def test_playing_handicap_9_holes_uses_half_index():
    # 20,0 / 2 × 120/113 + (35,5 − 36) = 10,12 -> 10
    assert playing_handicap(20.0, 35.5, 120, 36, holes=9) == 10


def test_plus_handicap():
    # −2,0 × 130/113 + (73,0 − 72) = −1,30 -> −1
    assert playing_handicap(-2.0, 73.0, 130, 72) == -1


def test_strokes_received_distribution():
    recv = strokes_received(22, SI_18)
    assert sum(recv.values()) == 22
    # Die vier schwersten Löcher (Hcp 1–4) bekommen zwei Schläge
    assert {h for h, n in recv.items() if n == 2} == {4, 13, 5, 14}
    assert min(recv.values()) == 1


def test_strokes_received_plus_handicap_gives_back_on_easiest_holes():
    recv = strokes_received(-2, SI_18)
    assert {h for h, n in recv.items() if n == -1} == {16, 7}  # Hcp 18 und 17
    assert sum(recv.values()) == -2


def test_strokes_received_nine_holes_with_18_hole_index():
    si = {1: 7, 2: 11, 3: 15, 4: 1, 5: 3, 6: 13, 7: 17, 8: 9, 9: 5}
    recv = strokes_received(5, si)
    assert {h for h, n in recv.items() if n == 1} == {4, 5, 9, 1, 8}  # Hcp 1, 3, 5, 7, 9


def test_stableford_points():
    assert stableford_points(4, 1, 5) == 2   # Netto-Par
    assert stableford_points(4, 1, 4) == 3   # Netto-Birdie
    assert stableford_points(4, 0, 7) == 0   # nie negativ
    assert stableford_points(4, 0, None) is None

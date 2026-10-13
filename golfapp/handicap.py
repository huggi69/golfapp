"""Spielvorgabe und Nettopunkte nach World Handicap System (WHS/DGV).

Reine Funktionen ohne Datenbankzugriff.
"""

import math


def round_half_up(value):
    """Kaufmännisch runden (x,5 wird aufgerundet) – wie im WHS vorgesehen."""
    return math.floor(value + 0.5)


def playing_handicap(hcp_index, course_rating, slope, par, holes=18):
    """Spielvorgabe für Einzel-Stableford (100 %).

    Spielvorgabe = Handicap-Index × (Slope / 113) + (Course Rating − Par)

    Bei 9-Loch-Runden wird der halbe Handicap-Index verwendet; Course Rating,
    Slope und Par müssen dann die 9-Loch-Werte sein.
    """
    if None in (hcp_index, course_rating, slope, par):
        return None
    if holes == 9:
        hcp_index = hcp_index / 2
    return round_half_up(hcp_index * slope / 113 + (course_rating - par))


def strokes_received(phcp, stroke_indexes):
    """Verteilt die Vorgabeschläge auf die Löcher.

    stroke_indexes: dict hole -> Handicap-Reihenfolge (1 = schwerstes Loch).
    Bei 9-Loch-Runden mit 18-Loch-Reihenfolge (z.B. 1, 3, 5, …) wird nach der
    Reihenfolge innerhalb der gespielten Löcher verteilt.

    Eine negative Spielvorgabe (Plus-Handicap) gibt Schläge an den leichtesten
    Löchern zurück.

    Rückgabe: dict hole -> Anzahl Vorgabeschläge (negativ bei Plus-Handicap).
    """
    holes = sorted(stroke_indexes, key=lambda h: (stroke_indexes[h], h))
    n = len(holes)
    if n == 0 or phcp is None:
        return {}
    base, rest = divmod(abs(phcp), n)
    result = {}
    for rank, hole in enumerate(holes):  # rank 0 = schwerstes Loch
        if phcp >= 0:
            result[hole] = base + (1 if rank < rest else 0)
        else:
            result[hole] = -(base + (1 if rank >= n - rest else 0))
    return result


def stableford_points(par, received, strokes):
    """Nettopunkte (Stableford) eines Lochs: 2 Punkte für Netto-Par."""
    if strokes is None:
        return None
    return max(0, 2 + par + received - strokes)

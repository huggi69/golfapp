"""Auswertung einer Golfrunde.

Reine Funktionen ohne Datenbankzugriff, damit sie sich leicht testen lassen.

Pro Runde gibt es fünf Kategorien. Der Gewinner einer Kategorie bekommt einen
Punkt. Teilen sich mehrere Spieler den ersten Platz, bekommt keiner einen Punkt.
"""

from dataclasses import dataclass, field
from fractions import Fraction

CATEGORIES = [
    # key, Anzeigename, besser ist ("low" | "high")
    ("match", "Lochspiel", "high"),
    ("gross", "Score (Schläge)", "low"),
    ("net", "Nettopunkte", "high"),
    ("putts", "Putts", "low"),
    ("ntp", "Nearest to the Pin", "high"),
]
CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES}


@dataclass
class CategoryResult:
    key: str
    label: str
    values: dict  # player_id -> Wert (Summe bzw. Anzahl gewonnener Löcher)
    winners: list  # player_ids, leer wenn kein Punkt vergeben wird
    points: dict  # player_id -> Fraction
    tied: bool = False  # Gleichstand an der Spitze -> kein Punkt


@dataclass
class RoundResult:
    complete: bool
    categories: list = field(default_factory=list)
    points: dict = field(default_factory=dict)  # player_id -> Fraction
    missing: int = 0  # Anzahl fehlender Eingaben


def _award(values, better, award_zero=True):
    """Ermittelt den Gewinner. Rückgabe: (winners, points, tied).

    Nur ein alleiniger Bestplatzierter bekommt den Punkt; bei Gleichstand an der
    Spitze geht der Punkt an niemanden.
    """
    points = {pid: Fraction(0) for pid in values}
    if not values:
        return [], points, False
    pick = min if better == "low" else max
    best = pick(values.values())
    if not award_zero and best == 0:
        return [], points, False
    leaders = [pid for pid, v in values.items() if v == best]
    if len(leaders) > 1:
        return [], points, True
    points[leaders[0]] = Fraction(1)
    return leaders, points, False


def hole_winner(hole_scores, basis):
    """Gewinner eines einzelnen Lochs im Lochspiel oder None bei Teilung.

    hole_scores: player_id -> (strokes, net_points)
    basis: 'gross' (wenigste Schläge) oder 'net' (meiste Nettopunkte)
    """
    if basis == "gross":
        vals = {pid: s for pid, (s, _) in hole_scores.items()}
        best = min(vals.values())
    else:
        vals = {pid: n for pid, (_, n) in hole_scores.items()}
        best = max(vals.values())
    leaders = [pid for pid, v in vals.items() if v == best]
    return leaders[0] if len(leaders) == 1 else None


def evaluate_round(player_ids, holes, scores, match_basis="net"):
    """Wertet eine Runde aus.

    player_ids: Liste der teilnehmenden Spieler
    holes: Liste von dicts mit 'hole', 'par', 'ntp_player_id'
    scores: dict (player_id, hole) -> dict mit 'strokes', 'putts', 'net_points'
    """
    missing = 0
    for pid in player_ids:
        for h in holes:
            s = scores.get((pid, h["hole"]))
            for k in ("strokes", "putts", "net_points"):
                if s is None or s.get(k) is None:
                    missing += 1

    if missing or len(player_ids) < 2 or not holes:
        return RoundResult(complete=False, missing=missing)

    def total(key):
        return {pid: sum(scores[(pid, h["hole"])][key] for h in holes) for pid in player_ids}

    holes_won = {pid: 0 for pid in player_ids}
    for h in holes:
        hs = {
            pid: (scores[(pid, h["hole"])]["strokes"], scores[(pid, h["hole"])]["net_points"])
            for pid in player_ids
        }
        w = hole_winner(hs, match_basis)
        if w is not None:
            holes_won[w] += 1

    ntp_wins = {pid: 0 for pid in player_ids}
    for h in holes:
        if h["par"] == 3 and h.get("ntp_player_id") in ntp_wins:
            ntp_wins[h["ntp_player_id"]] += 1

    values = {
        "match": holes_won,
        "gross": total("strokes"),
        "net": total("net_points"),
        "putts": total("putts"),
        "ntp": ntp_wins,
    }

    result = RoundResult(complete=True, points={pid: Fraction(0) for pid in player_ids})
    for key, label, better in CATEGORIES:
        # Nearest to the Pin: Hat niemand ein Par 3 gewonnen, gibt es keinen Punkt.
        winners, pts, tied = _award(values[key], better, award_zero=(key != "ntp"))
        result.categories.append(CategoryResult(key, label, values[key], winners, pts, tied))
        for pid, p in pts.items():
            result.points[pid] += p
    return result


def match_status(holes_won, names):
    """Lochspiel-Ergebnis als Text, z.B. 'Anna 3 auf' (nur sinnvoll bei 2 Spielern)."""
    if len(holes_won) != 2:
        return None
    (a, wa), (b, wb) = holes_won.items()
    if wa == wb:
        return "All Square"
    leader = a if wa > wb else b
    return f"{names[leader]} {abs(wa - wb)} auf"


def format_points(value):
    """Fraction -> '1½', '½', '3' usw."""
    value = Fraction(value)
    whole = value.numerator // value.denominator
    rest = value - whole
    if rest == 0:
        return str(whole)
    if rest == Fraction(1, 2):
        return f"{whole}½" if whole else "½"
    return f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")

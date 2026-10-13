"""Import der Historie aus der alten Golf-App (MySQL-Dump, z.B. aus TablePlus).

Aufruf:
    python -m golfapp.legacy_import golf.sql [--db /pfad/zur/golf.sqlite]

Ohne --db wird DATABASE_PATH bzw. der Standardpfad der App verwendet.
Bereits importierte Spiele werden übersprungen – der Import kann also gefahrlos
erneut laufen.

Zuordnung alte -> neue App:
  golf_players            -> players (über den Namen)
  golf_games              -> rounds (finalfour -> Rundentyp)
  golf_holes  score/puts/netto/pin je Loch -> scores bzw. NTP-Sieger
  golf_season.ffintotal   -> seasons.ff_in_annual
  golf_season.lochberechnung ('score' = brutto, sonst netto) -> Lochspiel-Wertung

Die alte App kennt kein Par: Löcher mit gewonnenem Pin werden Par 3, alle anderen
bleiben unbekannt und können später in der Runde nachgetragen werden.
Löcher mit 0 Schlägen bei allen Spielern gelten als nicht gespielt.
"""

import argparse
import re
import sqlite3
import sys
from collections import defaultdict

NOTE_PREFIX = "Import alte App, Spiel "


# --------------------------------------------------------------------------
# Dump einlesen
# --------------------------------------------------------------------------

_INSERT = re.compile(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES\s*(.*?);\s*$", re.S | re.M)


def _parse_values(text):
    """Zerlegt '(1, 'a', NULL), (2, 'b\\'c', 3)' in Tupel."""
    rows, row, i, n = [], None, 0, len(text)
    while i < n:
        c = text[i]
        if c == "(" and row is None:
            row, i = [], i + 1
            continue
        if row is None or c in " ,\n\r\t":
            i += 1
            continue
        if c == ")":
            rows.append(tuple(row))
            row, i = None, i + 1
            continue
        if c == "'":
            j, buf = i + 1, []
            while text[j] != "'" or text[j + 1 : j + 2] == "'":
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == "'":  # '' = maskiertes '
                    buf.append("'")
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            row.append("".join(buf))
            i = j + 1
            continue
        m = re.match(r"[^,)\s]+", text[i:])
        token = m.group(0)
        if token.upper() == "NULL":
            row.append(None)
        else:
            try:
                row.append(int(token))
            except ValueError:
                row.append(float(token))
        i += len(token)
    return rows


def parse_dump(text):
    """Rückgabe: {tabelle: [dict, ...]}"""
    tables = defaultdict(list)
    for table, cols, values in _INSERT.findall(text):
        names = [c.strip().strip("`") for c in cols.split(",")]
        for row in _parse_values(values):
            tables[table].append(dict(zip(names, row)))
    return tables


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

def _clean_name(name):
    return " ".join((name or "").split())


def import_legacy(conn, tables):
    """Importiert in eine bestehende (initialisierte) Datenbank. Gibt einen Bericht zurück."""
    report = {"rounds": 0, "skipped_existing": 0, "skipped_empty": [], "notes": []}
    conn.execute("PRAGMA foreign_keys = ON")

    # Spieler über den Namen zuordnen bzw. anlegen
    player_map = {}
    for p in tables.get("golf_players", []):
        name = _clean_name(p["name"])
        row = conn.execute("SELECT id FROM players WHERE name = ?", (name,)).fetchone()
        player_map[p["id"]] = row[0] if row else conn.execute(
            "INSERT INTO players (name) VALUES (?)", (name,)
        ).lastrowid

    # Saison-Einstellungen
    match_basis = {}
    for s in tables.get("golf_season", []):
        conn.execute(
            "INSERT INTO seasons (year, ff_in_annual) VALUES (?, ?) "
            "ON CONFLICT(year) DO UPDATE SET ff_in_annual = excluded.ff_in_annual",
            (s["season"], 1 if s["ffintotal"] else 0),
        )
        match_basis[s["season"]] = "gross" if s.get("lochberechnung") == "score" else "net"

    # Lochwerte je Spiel: (spieler, kategorie) -> 18 Werte
    holes_by_game = defaultdict(dict)
    for h in tables.get("golf_holes", []):
        values = [h[f"hole{i}"] for i in range(1, 19)]
        holes_by_game[h["game_id"]][(h["player_id"], h["challenge"])] = values

    games = sorted(tables.get("golf_games", []), key=lambda g: (str(g["date"]), g["id"]))
    for g in games:
        note = f"{NOTE_PREFIX}{g['id']}"
        if conn.execute("SELECT 1 FROM rounds WHERE notes = ?", (note,)).fetchone():
            report["skipped_existing"] += 1
            continue
        data = holes_by_game.get(g["id"], {})
        old_players = sorted({pid for pid, _ in data if pid in player_map})
        scores = {pid: data.get((pid, "score")) for pid in old_players}
        played = [
            i for i in range(18)
            if any(scores[pid] and scores[pid][i] > 0 for pid in old_players)
        ]
        label = f"{g['date']} {_clean_name(g['course'])} (Spiel {g['id']})"
        if not old_players or not played:
            report["skipped_empty"].append(label)
            continue

        year = int(str(g["date"])[:4])
        round_id = conn.execute(
            "INSERT INTO rounds (played_on, course_name, round_type, match_basis, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(g["date"]),
                _clean_name(g["course"]),
                "final_four" if g["finalfour"] else "normal",
                match_basis.get(year, "net"),
                note,
            ),
        ).lastrowid
        for pid in old_players:
            conn.execute(
                "INSERT INTO round_players (round_id, player_id) VALUES (?, ?)",
                (round_id, player_map[pid]),
            )

        if len(played) < 18:
            report["notes"].append(f"{label}: nur {len(played)} Löcher gespielt")
        if len(old_players) < 2:
            report["notes"].append(f"{label}: nur ein Spieler erfasst")
        missing = sorted(
            {c for pid in old_players for c in ("score", "puts", "netto") if (pid, c) not in data}
        )
        if missing:
            report["notes"].append(f"{label}: keine Daten für {', '.join(missing)}")

        for i in played:
            hole = i + 1
            pin_winners = [pid for pid in old_players if (data.get((pid, "pin")) or [0] * 18)[i]]
            if len(pin_winners) > 1:
                report["notes"].append(f"{label}: Loch {hole} Pin bei mehreren Spielern – kein NTP-Sieger")
            ntp = player_map[pin_winners[0]] if len(pin_winners) == 1 else None
            conn.execute(
                "INSERT INTO round_holes (round_id, hole, par, ntp_player_id) VALUES (?, ?, ?, ?)",
                (round_id, hole, 3 if pin_winners else None, ntp),
            )
            for pid in old_players:
                def value(challenge):
                    v = data.get((pid, challenge))
                    return None if v is None else v[i]

                strokes = value("score")
                conn.execute(
                    "INSERT INTO scores (round_id, player_id, hole, strokes, putts, net_points) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (round_id, player_map[pid], hole, strokes or None, value("puts"), value("netto")),
                )
        report["rounds"] += 1
    conn.commit()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Historie aus der alten Golf-App importieren")
    parser.add_argument("dump", help="MySQL-Dump der alten App (.sql)")
    parser.add_argument("--db", help="Ziel-Datenbank (Standard: DATABASE_PATH bzw. Pfad der App)")
    args = parser.parse_args(argv)

    from . import create_app

    app = create_app({"DATABASE": args.db} if args.db else None)  # legt Schema an, migriert
    with open(args.dump, encoding="utf-8") as f:
        tables = parse_dump(f.read())
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        report = import_legacy(conn, tables)
    finally:
        conn.close()

    print(f"Datenbank: {app.config['DATABASE']}")
    print(f"Importierte Runden: {report['rounds']}")
    if report["skipped_existing"]:
        print(f"Bereits vorhanden, übersprungen: {report['skipped_existing']}")
    for label in report["skipped_empty"]:
        print(f"Ohne Daten, übersprungen: {label}")
    for line in report["notes"]:
        print(f"Hinweis: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

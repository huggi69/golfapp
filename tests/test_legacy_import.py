import sqlite3

from golfapp import create_app
from golfapp.legacy_import import import_legacy, parse_dump

DUMP = """
INSERT INTO `golf_players` (`id`, `name`) VALUES
(1, 'Huggi'),
(2, 'Fran\\'ky');

INSERT INTO `golf_season` (`id`, `season`, `ffintotal`, `aktuell`, `lochberechnung`) VALUES
(5, 2022, 1, 0, 'score'),
(9, 2026, 0, 1, 'netto');

INSERT INTO `golf_games` (`id`, `course`, `date`, `finalfour`) VALUES
(1, 'GC  Velbert ', '2022-05-30', 0),
(2, 'GC Ahaus', '2026-07-18', 1),
(3, 'Leer', '2026-07-19', 0);

INSERT INTO `golf_holes` (`id`, `game_id`, `player_id`, `challenge`, `hole1`, `hole2`, `hole3`, `hole4`, `hole5`, `hole6`, `hole7`, `hole8`, `hole9`, `hole10`, `hole11`, `hole12`, `hole13`, `hole14`, `hole15`, `hole16`, `hole17`, `hole18`) VALUES
(1, 1, 1, 'score', 5, 4, 4, 5, 5, 8, 4, 5, 5, 7, 3, 6, 6, 4, 5, 6, 5, 7),
(2, 1, 2, 'score', 6, 5, 7, 5, 6, 7, 7, 3, 6, 6, 7, 6, 6, 3, 5, 3, 5, 9),
(3, 1, 1, 'puts', 3, 1, 1, 2, 1, 2, 2, 1, 1, 3, 1, 2, 2, 3, 2, 2, 2, 2),
(4, 1, 2, 'puts', 2, 2, 2, 2, 2, 1, 3, 1, 2, 3, 2, 2, 2, 2, 2, 2, 1, 2),
(5, 1, 1, 'netto', 3, 4, 2, 2, 2, 1, 4, 1, 3, 1, 4, 2, 2, 2, 3, 0, 2, 1),
(6, 1, 2, 'netto', 2, 3, 0, 2, 1, 2, 0, 3, 2, 2, 0, 2, 2, 3, 3, 3, 2, 0),
(7, 1, 1, 'pin', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
(8, 1, 2, 'pin', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0),
(9, 2, 1, 'score', 6, 3, 8, 8, 6, 6, 5, 5, 4, 10, 0, 0, 0, 0, 0, 0, 0, 0),
(10, 2, 2, 'score', 10, 4, 7, 6, 6, 5, 4, 5, 4, 8, 0, 0, 0, 0, 0, 0, 0, 0),
(11, 2, 1, 'puts', 2, 2, 2, 2, 1, 1, 2, 1, 2, 4, 0, 0, 0, 0, 0, 0, 0, 0),
(12, 2, 2, 'puts', 3, 2, 1, 2, 1, 1, 1, 1, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0),
(13, 2, 1, 'netto', 1, 3, 0, 0, 1, 2, 2, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0),
(14, 2, 2, 'netto', 0, 2, 1, 2, 1, 4, 3, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0),
(15, 2, 1, 'pin', 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
"""


def make_db(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "golf.sqlite")})
    return app, sqlite3.connect(app.config["DATABASE"])


def test_parse_dump():
    tables = parse_dump(DUMP)
    assert tables["golf_players"][1] == {"id": 2, "name": "Fran'ky"}
    assert len(tables["golf_holes"]) == 15
    assert tables["golf_holes"][0]["hole18"] == 7


def test_import(tmp_path):
    app, conn = make_db(tmp_path)
    report = import_legacy(conn, parse_dump(DUMP))
    assert report["rounds"] == 2
    assert report["skipped_empty"] == ["2026-07-19 Leer (Spiel 3)"]
    assert any("Loch 14 Pin bei mehreren Spielern" in n for n in report["notes"])
    assert any("nur 10 Löcher" in n for n in report["notes"])

    rounds = conn.execute(
        "SELECT played_on, course_name, round_type, match_basis FROM rounds ORDER BY played_on"
    ).fetchall()
    assert rounds == [("2022-05-30", "GC Velbert", "normal", "gross"),
                      ("2026-07-18", "GC Ahaus", "final_four", "net")]
    assert conn.execute("SELECT year, ff_in_annual FROM seasons ORDER BY year").fetchall() == [
        (2022, 1), (2026, 0)]
    # Pin-Löcher werden Par 3; Doppel-Pin -> kein Sieger; Loch 16 -> Franky
    holes = dict(conn.execute(
        "SELECT hole, ntp_player_id FROM round_holes WHERE round_id = 1 AND par = 3").fetchall())
    assert holes == {14: None, 16: 2}
    assert conn.execute("SELECT COUNT(*) FROM round_holes WHERE round_id = 1 AND par IS NULL").fetchone()[0] == 16
    # Verkürzte Runde: nur gespielte Löcher
    assert conn.execute("SELECT COUNT(*) FROM round_holes WHERE round_id = 2").fetchone()[0] == 10

    # Runden werden ausgewertet und erscheinen im Dashboard
    c = app.test_client()
    assert "GC Velbert" in c.get("/?year=2022").get_data(as_text=True)
    page = c.get("/rounds/1").get_data(as_text=True)
    assert "Auswertung" in page and "noch nicht vollständig" not in page

    # Erneuter Import legt nichts doppelt an
    again = import_legacy(conn, parse_dump(DUMP))
    assert again["rounds"] == 0 and again["skipped_existing"] == 2


def test_par_not_null_is_relaxed(tmp_path):
    path = tmp_path / "alt.sqlite"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE round_holes (round_id INTEGER NOT NULL, hole INTEGER NOT NULL,
            par INTEGER NOT NULL CHECK (par BETWEEN 3 AND 6), ntp_player_id INTEGER,
            PRIMARY KEY (round_id, hole));
        INSERT INTO round_holes VALUES (1, 1, 4, NULL);
    """)
    db.commit()
    db.close()
    create_app({"DATABASE": str(path)})
    db = sqlite3.connect(path)
    assert db.execute("SELECT round_id, hole, par, stroke_index FROM round_holes").fetchall() == [(1, 1, 4, None)]
    db.execute("INSERT INTO round_holes (round_id, hole, par) VALUES (1, 2, NULL)")


def test_season_setting(client):
    client.post("/seasons/2026", data={"ff_in_annual": "1"})
    assert 'name="ff_in_annual" value="1" checked' in client.get("/?year=2026").get_data(as_text=True)
    client.post("/seasons/2026", data={})
    assert 'value="1" checked' not in client.get("/?year=2026").get_data(as_text=True)

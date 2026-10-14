from golfapp import create_app


def create_round(client, played_on="2026-05-01", round_type="normal"):
    resp = client.post("/rounds/new", data={
        "played_on": played_on, "course_name": "Testplatz", "pars": "4,3,5,4,4,3,4,5,4",
        "round_type": round_type, "match_basis": "net", "players": ["1", "2"],
    })
    assert resp.status_code == 302
    return int(resp.headers["Location"].split("/")[2])


def fill_round(client, round_id, anna_better=True):
    data = {"played_on": "2026-05-01", "course_name": "Testplatz",
            "round_type": "normal", "match_basis": "net", "notes": ""}
    rid = client.get(f"/rounds/{round_id}")  # noqa: F841 – Seite muss rendern
    for hole in range(1, 10):
        good, bad = ("1", "2") if anna_better else ("2", "1")
        data.update({f"s_{good}_{hole}": "4", f"p_{good}_{hole}": "1", f"n_{good}_{hole}": "3",
                     f"s_{bad}_{hole}": "6", f"p_{bad}_{hole}": "2", f"n_{bad}_{hole}": "1"})
    data["ntp_2"] = "1" if anna_better else "2"
    return data


def test_full_flow(client):
    rid = create_round(client)
    data = fill_round(client, rid)
    resp = client.post(f"/rounds/{rid}/edit", data=data)
    assert resp.status_code == 302
    page = client.get(f"/rounds/{rid}").get_data(as_text=True)
    assert "Anna 9 auf" in page

    ff = create_round(client, "2026-09-12", "final_four")
    data = fill_round(client, ff, anna_better=False)
    data["round_type"] = "final_four"
    data["played_on"] = "2026-09-12"
    client.post(f"/rounds/{ff}/edit", data=data)

    dash = client.get("/?year=2026").get_data(as_text=True)
    assert "Jahreswertung" in dash and "Final Four" in dash
    assert "1 / 4 Runden" in dash



def test_net_points_are_calculated_from_handicap(client):
    resp = client.post("/rounds/new", data={
        "played_on": "2026-06-01", "course_name": "Neun", "pars": "4,4,4,4,4,4,4,4,4",
        "stroke_index": "1,2,3,4,5,6,7,8,9", "round_type": "normal", "match_basis": "net",
        "players": ["1", "2"],
        # Anna: 9 × 113/113 / 2 + (36 − 36) = 4,5 -> 5 Vorgabeschläge
        "hcp_1": "9,0", "cr_1": "36,0", "slope_1": "113", "tee_1": "Gelb",
        # Ben: Spielvorgabe 0
        "hcp_2": "0", "cr_2": "36", "slope_2": "113",
    })
    rid = int(resp.headers["Location"].split("/")[2])
    data = {"played_on": "2026-06-01", "course_name": "Neun", "round_type": "normal",
            "match_basis": "net", "notes": "",
            "hcp_1": "9,0", "cr_1": "36,0", "slope_1": "113", "tee_1": "Gelb",
            "hcp_2": "0", "cr_2": "36", "slope_2": "113", "tee_2": ""}
    for hole in range(1, 10):
        data.update({f"par_{hole}": "4", f"si_{hole}": str(hole),
                     f"s_1_{hole}": "5", f"p_1_{hole}": "2", f"n_1_{hole}": "",
                     f"s_2_{hole}": "4", f"p_2_{hole}": "2", f"n_2_{hole}": "99"})
    assert client.post(f"/rounds/{rid}/edit", data=data).status_code == 302

    from golfapp.views import load_round
    with client.application.test_request_context():
        r = load_round(rid)
    assert r["auto_net"]
    assert r["handicaps"][1]["phcp"] == 5
    net = r["result"].categories[2].values
    # Anna: Löcher 1–5 netto Par (2), 6–9 netto Bogey (1) = 14; Ben: 9 × 2 = 18
    assert net == {1: 14, 2: 18}
    # Eingegebene Nettopunkte (99) werden ignoriert, berechnete gespeichert
    import sqlite3
    db = sqlite3.connect(client.application.config["DATABASE"])
    assert db.execute("SELECT SUM(net_points) FROM scores WHERE round_id = ?", (rid,)).fetchone()[0] == 32


def test_course_with_tees(client):
    resp = client.post("/courses", data={"name": "GC Test", "pars": "4,4,3,5,4,4,3,4,5",
                                          "stroke_index": "1,3,5,7,9,11,13,15,17"})
    assert resp.status_code == 302
    cid = int(resp.headers["Location"].rstrip("/").split("/")[-1])
    client.post(f"/courses/{cid}", data={"action": "add_tee", "tee_name": "Gelb Herren",
                                         "course_rating": "35,4", "slope": "128"})
    page = client.get(f"/courses/{cid}").get_data(as_text=True)
    assert "Gelb Herren" in page and "35,4" in page
    assert "Gelb Herren" in client.get("/rounds/new").get_data(as_text=True)

    import sqlite3
    db = sqlite3.connect(client.application.config["DATABASE"])
    tee_id = db.execute("SELECT id FROM course_tees").fetchone()[0]
    client.post(f"/courses/{cid}", data={"action": "update_tee", "tee_id": tee_id,
                                         "tee_name": "Gelb", "course_rating": "35.0", "slope": "125"})
    assert db.execute("SELECT name, course_rating, slope FROM course_tees").fetchone() == ("Gelb", 35.0, 125)
    client.post(f"/courses/{cid}", data={"action": "delete_tee", "tee_id": tee_id})
    assert db.execute("SELECT COUNT(*) FROM course_tees").fetchone()[0] == 0


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    path = tmp_path / "alt.sqlite"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE players (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                              active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                              pars TEXT NOT NULL);
        INSERT INTO players (name) VALUES ('Anna');
    """)
    db.commit()
    db.close()
    app = create_app({"DATABASE": str(path)})
    db = sqlite3.connect(path)
    assert "hcp_index" in {r[1] for r in db.execute("PRAGMA table_info(players)")}
    assert "stroke_index" in {r[1] for r in db.execute("PRAGMA table_info(courses)")}
    assert db.execute("SELECT name FROM players").fetchall() == [("Anna",)]
    assert "password_hash" in {r[1] for r in db.execute("PRAGMA table_info(players)")}
    # Alte Datenbank ohne Passwörter -> Ersteinrichtung
    assert "Zugang anlegen" in app.test_client().get("/login").get_data(as_text=True)


def test_play_mode_saves_hole_by_hole(client):
    resp = client.post("/rounds/new", data={
        "played_on": "2026-06-01", "course_name": "Neun", "pars": "4,3,4,4,4,4,4,4,4",
        "stroke_index": "1,2,3,4,5,6,7,8,9", "round_type": "normal", "match_basis": "net",
        "players": ["1", "2"],
        "hcp_1": "9,0", "cr_1": "36", "slope_1": "113",
        "hcp_2": "0", "cr_2": "36", "slope_2": "113",
    })
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/play")
    rid = int(resp.headers["Location"].split("/")[2])

    page = client.get(f"/rounds/{rid}/play").get_data(as_text=True)
    assert "Loch für Loch" in page and "const SAVE_URL" in page

    # Loch 1: Anna (Spielvorgabe 6) 5 Schläge mit 1 Vorgabeschlag -> 2 Punkte (wird berechnet, 9 ignoriert)
    r = client.post(f"/rounds/{rid}/holes/1", json={
        "par": 4, "ntp": None,
        "scores": {"1": {"strokes": 5, "putts": 2, "net_points": 9},
                   "2": {"strokes": 4, "putts": 1, "net_points": None}},
    })
    assert r.status_code == 200
    state = r.get_json()["state"]
    assert state["scores"]["1"]["1"] == {"strokes": 5, "putts": 2, "net_points": 2}
    # Ben: Spielvorgabe 0 + (36 − Par 35) = 1 -> ein Vorgabeschlag auf Hcp 1 -> 3 Punkte
    assert state["scores"]["2"]["1"]["net_points"] == 3
    assert state["round"]["auto_net"] is True

    # Loch 2 ist Par 3: NTP wird gespeichert; Putts >= Schläge gibt eine Warnung
    r = client.post(f"/rounds/{rid}/holes/2", json={
        "ntp": 2, "scores": {"1": {"strokes": 3, "putts": 3}, "2": {"strokes": 3, "putts": 2}}})
    data = r.get_json()
    assert data["state"]["holes"][1]["ntp"] == 2
    assert data["warnings"] == ["Loch 2, Anna: mehr Putts als Schläge?"]

    # Ohne Lochangabe startet die Maske beim ersten offenen Loch
    assert "let current = 3;" in client.get(f"/rounds/{rid}/play").get_data(as_text=True)
    assert client.post(f"/rounds/{rid}/holes/99", json={}).status_code == 404


def test_courses_export_and_import(client, tmp_path):
    import io
    import json

    from conftest import make_app

    client.post("/courses", data={"name": "GC Grevenmühle", "pars": "4,4,3,5,4,4,3,4,5",
                                  "stroke_index": "1,3,5,7,9,11,13,15,17"})
    client.post("/courses/1", data={"action": "add_tee", "tee_name": "Gelb Herren",
                                    "course_rating": "35,4", "slope": "128"})
    r = client.get("/courses/export")
    assert "attachment" in r.headers["Content-Disposition"]
    exported = r.get_json()
    assert exported["courses"][0]["tees"] == [{"name": "Gelb Herren", "course_rating": 35.4, "slope": 128}]

    # Zweite Installation ("Server"): ein gleichnamiger Platz mit alten Werten existiert schon
    other = make_app(tmp_path / "server").test_client()
    other.post("/login", data={"name": "Huggi", "password": "geheim1", "password2": "geheim1"})
    other.post("/courses", data={"name": "gc grevenmühle", "pars": "4,4,4,4,4,4,4,4,4"})
    exported["courses"].append({"name": "Kaputt", "pars": [9]})
    r = other.post("/courses/import", data={
        "file": (io.BytesIO(json.dumps(exported).encode()), "plaetze.json")}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "0 Platz/Plätze neu, 1 aktualisiert" in page
    assert "„Kaputt“: Name oder Par-Werte ungültig" in page
    again = other.get("/courses/export").get_json()["courses"]
    assert again == [{"name": "gc grevenmühle", "pars": [4, 4, 3, 5, 4, 4, 3, 4, 5],
                      "stroke_index": [1, 3, 5, 7, 9, 11, 13, 15, 17],
                      "tees": [{"name": "Gelb Herren", "course_rating": 35.4, "slope": 128}]}]

    r = other.post("/courses/import", data={"file": (io.BytesIO(b"kein json"), "x.json")},
                   follow_redirects=True)
    assert "keine gültige Plätze-Datei" in r.get_data(as_text=True)

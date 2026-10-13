import sqlite3

from conftest import make_app


def login(c, name, password):
    return c.post("/login", data={"name": name, "password": password})


def test_everything_requires_login(tmp_path):
    c = make_app(tmp_path).test_client()
    for url in ("/", "/rounds/new", "/players", "/courses", "/rounds/1", "/rounds/1/play"):
        r = c.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url
    assert c.post("/players", data={"action": "add", "name": "X"}).status_code == 302
    assert c.post("/rounds/1/holes/1", json={}).status_code == 401
    assert c.get("/healthz").status_code == 200
    assert c.get("/static/style.css").status_code == 200


def test_setup_creates_first_login(tmp_path):
    c = make_app(tmp_path).test_client()
    assert "Zugang anlegen" in c.get("/login").get_data(as_text=True)
    r = c.post("/login", data={"name": "Huggi", "password": "kurz", "password2": "kurz"})
    assert "mindestens 6 Zeichen" in r.get_data(as_text=True)
    r = c.post("/login", data={"name": "Huggi", "password": "geheim1", "password2": "geheim1"})
    assert r.status_code == 302
    assert "Huggi" in c.get("/").get_data(as_text=True)
    # Danach gibt es keine Ersteinrichtung mehr
    c.post("/logout")
    assert "Zugang anlegen" not in c.get("/login").get_data(as_text=True)


def test_login_logout_and_wrong_password(client):
    client.post("/logout")
    assert client.get("/").status_code == 302
    r = login(client, "anna", "falsch!")
    assert "Name oder Passwort falsch" in r.get_data(as_text=True)
    # Ben hat noch kein Passwort -> kein Login möglich
    assert "Name oder Passwort falsch" in login(client, "Ben", "").get_data(as_text=True)
    r = client.post("/login?next=/players", data={"name": "anna", "password": "geheim1"})
    assert r.headers["Location"] == "/players"
    # Keine Weiterleitung auf fremde Seiten
    client.post("/logout")
    r = client.post("/login?next=//evil.example", data={"name": "Anna", "password": "geheim1"})
    assert r.headers["Location"] == "/"


def test_set_password_for_other_player_and_change_own(client):
    db = sqlite3.connect(client.application.config["DATABASE"])
    ben = db.execute("SELECT id FROM players WHERE name = 'Ben'").fetchone()[0]
    r = client.post("/players", data={"action": "password", "id": ben, "password": "kurz"},
                    follow_redirects=True)
    assert "mindestens 6 Zeichen" in r.get_data(as_text=True)
    client.post("/players", data={"action": "password", "id": ben, "password": "benpass"})
    client.post("/logout")
    assert login(client, "Ben", "benpass").status_code == 302

    r = client.post("/account", data={"old_password": "falsch", "new_password": "neuespw",
                                      "new_password2": "neuespw"})
    assert "bisherige Passwort ist falsch" in r.get_data(as_text=True)
    client.post("/account", data={"old_password": "benpass", "new_password": "neuespw",
                                  "new_password2": "neuespw"})
    client.post("/logout")
    assert login(client, "Ben", "neuespw").status_code == 302


def test_inactive_player_is_logged_out(client):
    db = sqlite3.connect(client.application.config["DATABASE"])
    anna = db.execute("SELECT id FROM players WHERE name = 'Anna'").fetchone()[0]
    # Man kann sich nicht selbst deaktivieren
    client.post("/players", data={"action": "toggle", "id": anna})
    assert db.execute("SELECT active FROM players WHERE id = ?", (anna,)).fetchone()[0] == 1
    db.execute("UPDATE players SET active = 0 WHERE id = ?", (anna,))
    db.commit()
    assert client.get("/").status_code == 302


def test_secret_key_is_persisted(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from golfapp import create_app
    a = create_app({"DATABASE": str(tmp_path / "db.sqlite")})
    b = create_app({"DATABASE": str(tmp_path / "db.sqlite")})
    assert a.config["SECRET_KEY"] == b.config["SECRET_KEY"]
    assert (tmp_path / "secret_key").exists()

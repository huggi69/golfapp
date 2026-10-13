import pytest

from golfapp import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "test.sqlite"), "TESTING": True,
                      "APP_PASSWORD": "", "FINAL_FOUR_IN_ANNUAL": False})
    with app.test_client() as c:
        c.post("/players", data={"action": "add", "name": "Anna"})
        c.post("/players", data={"action": "add", "name": "Ben"})
        yield c


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


def test_password_protects_writes(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "t.sqlite"), "APP_PASSWORD": "geheim"})
    c = app.test_client()
    assert c.get("/").status_code == 200
    assert c.get("/rounds/new").status_code == 401
    assert c.post("/players", data={"action": "add", "name": "X"}).status_code == 401
    ok = c.get("/rounds/new", headers={"Authorization": "Basic dTpnZWhlaW0="})  # u:geheim
    assert ok.status_code == 200

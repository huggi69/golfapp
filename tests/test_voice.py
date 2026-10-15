"""Spracheingabe: die Auswertung in static/voice.js wird mit Node geprüft (falls installiert)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

VOICE_JS = Path(__file__).resolve().parent.parent / "golfapp" / "static" / "voice.js"
PLAYERS = [{"id": 1, "name": "Huggi"}, {"id": 2, "name": "Franky"}]

CASES = [
    ("Franky 5 1, Huggi 4 2", [["Franky", 5, 1], ["Huggi", 4, 2]]),
    ("franky fünf eins hugi vier zwei", [["Franky", 5, 1], ["Huggi", 4, 2]]),  # Zahlwörter, verhört
    ("Frank 51 Huggi 42", [["Franky", 5, 1], ["Huggi", 4, 2]]),  # zusammengezogen
    ("Franky 10 2 Huggi 3", [["Franky", 10, 2], ["Huggi", 3, None]]),  # Putts fehlen
    ("Huggi 13", [["Huggi", 13, None]]),  # 13 Schläge, nicht 1/3
    ("Huggi 102", [["Huggi", 10, 2]]),
    ("Huggi 3 3", [["Huggi", 3, None]]),  # Putts >= Schläge werden verworfen
    ("Franky 5 1 und Huggi 4 2 Franky 6 2", [["Franky", 6, 2], ["Huggi", 4, 2]]),  # Korrektur
    ("irgendwas ganz anderes", []),
    ("Franky 5 1 2 Huggi 4 2 3", [["Franky", 5, 1, 2], ["Huggi", 4, 2, 3]]),  # mit Nettopunkten
]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js nicht installiert")
def test_parse_voice():
    script = f"""
        const {{ parseVoice }} = require({json.dumps(str(VOICE_JS))});
        const cases = {json.dumps([c for c, _ in CASES])};
        const players = {json.dumps(PLAYERS)};
        console.log(JSON.stringify(cases.map(c => parseVoice(c, players).results
            .map(r => [r.player.name, r.strokes, r.putts === undefined ? null : r.putts]
                 .concat(r.net === undefined ? [] : [r.net])))));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    for (text, expected), got in zip(CASES, json.loads(out)):
        assert got == expected, text


def test_play_page_includes_voice(client):
    resp = client.post("/rounds/new", data={
        "played_on": "2026-06-01", "course_name": "X", "pars": "4,4,4,4,4,4,4,4,4",
        "round_type": "normal", "match_basis": "gross", "players": ["1", "2"]})
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "voice.js" in page and 'id="voice-btn"' in page
    assert "„Ben 5 1, Anna 4 2“" in page

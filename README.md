# ⛳ Golf Duell

Webanwendung für einen jährlichen Golfwettbewerb zwischen zwei (oder mehr) Spielern –
mit Jahreswertung und der Sonderwertung **Final Four**. Läuft in einem einzigen Container
mit SQLite-Datenbank.

## Wertung

Jede Runde wird in fünf Kategorien ausgewertet. Der Sieger einer Kategorie bekommt **1 Punkt**:

| Kategorie            | Sieger                                                                 |
|----------------------|------------------------------------------------------------------------|
| Lochspiel            | meiste gewonnene Löcher (je Runde wählbar: Netto = Nettopunkte je Loch, Brutto = Schläge je Loch) |
| Score (Schläge)      | wenigste Schläge gesamt                                                |
| Nettopunkte          | meiste Nettopunkte (Stableford) gesamt                                 |
| Putts                | wenigste Putts gesamt                                                  |
| Nearest to the Pin   | die meisten gewonnenen Par-3-Löcher (NTP wird je Par 3 erfasst)        |

* **Gleichstand:** Teilen sich mehrere Spieler den ersten Platz, bekommt keiner einen Punkt.
* **Nearest to the Pin:** Gewinnt niemand ein Par 3, wird kein Punkt vergeben.
* Eine Runde zählt erst, wenn für alle Spieler und Löcher Schläge, Putts und Nettopunkte erfasst sind.
  Zwischenstände können gespeichert werden.

### Nettopunkte & Spielvorgabe

Sind für eine Runde Handicap-Index, Course Rating und Slope je Spieler sowie die
Handicap-Reihenfolge der Löcher bekannt, berechnet die App die Nettopunkte automatisch:

* **Spielvorgabe** = Handicap-Index × (Slope / 113) + (Course Rating − Par), kaufmännisch gerundet
  (World Handicap System, 100 % für Einzel-Stableford). Bei 9-Loch-Runden zählt der halbe
  Handicap-Index; Course Rating, Slope und Par sind dann die 9-Loch-Werte.
* Die Vorgabeschläge werden nach der Handicap-Reihenfolge verteilt (Hcp 1 = schwerstes Loch).
  Plus-Handicaps geben an den leichtesten Löchern Schläge zurück.
* **Nettopunkte je Loch** = max(0, 2 + Par + Vorgabeschläge − Schläge).

Fehlt eine dieser Angaben, werden die Nettopunkte wie bisher von Hand eingetragen.

Course Rating, Slope und Handicap-Reihenfolge stehen auf der Scorekarte bzw. der Vorgabentabelle
des Clubs. Eine frei nutzbare Datenbank für deutsche Plätze gibt es nicht – die Werte werden
deshalb einmal je Platz unter **Plätze** eingetragen.

### Saison & Final Four

* Eine Saison läuft vom 01.01. bis 31.12. – das Jahr ergibt sich aus dem Rundendatum.
* Beim Anlegen einer Runde wählt man **Normale Runde** oder **Final Four**.
* Final-Four-Runden (vier Runden an einem Wochenende) bilden eine eigene Sonderwertung.
  Standardmäßig zählen sie **nicht** zur Jahreswertung – umstellbar mit `FINAL_FOUR_IN_ANNUAL=true`.

## Starten

### Projekt lokal einrichten

Das Projekt liegt lokal unter `~/Projekte/golfapp`:

```bash
mkdir -p ~/Projekte
cd ~/Projekte
git clone https://github.com/huggi69/golfapp.git
cd golfapp
git checkout main
```

### Mit Docker Compose

```bash
docker compose up -d --build
```

Danach läuft die App unter <http://localhost:8000>. Die Datenbank liegt im Volume `golf-data`
(`/data/golf.sqlite` im Container).

### Nur Docker

```bash
docker build -t golfapp .
docker run -d -p 8000:8000 -v golf-data:/data --name golfapp golfapp
```

### Konfiguration (Umgebungsvariablen)

| Variable               | Standard              | Bedeutung                                                             |
|------------------------|-----------------------|-----------------------------------------------------------------------|
| `DATABASE_PATH`        | `/data/golf.sqlite`   | Pfad der SQLite-Datei                                                 |
| `APP_PASSWORD`         | leer                  | Wenn gesetzt, verlangen alle Eingabe-/Änderungsseiten dieses Passwort (Benutzername beliebig). Das Dashboard bleibt öffentlich. |
| `FINAL_FOUR_IN_ANNUAL` | `false`               | Final-Four-Runden zusätzlich in der Jahreswertung zählen               |
| `SECRET_KEY`           | zufällig              | Schlüssel für Session-Cookies (Hinweis-Meldungen)                     |

### Backup

```bash
docker compose exec golfapp python -c "import sqlite3; s=sqlite3.connect('/data/golf.sqlite'); s.backup(sqlite3.connect('/data/backup.sqlite'))"
docker compose cp golfapp:/data/backup.sqlite ./backup.sqlite
```

## Bedienung

1. Unter **Spieler** die Spieler mit ihrem aktuellen Handicap-Index anlegen.
2. Unter **Plätze** Plätze mit Par, Handicap-Reihenfolge und den Abschlägen
   (Course Rating, Slope) speichern.
3. **Neue Runde**: Datum, Rundentyp (Normal / Final Four), Platz, Spieler, Handicap-Index und
   Abschlag wählen – die Spielvorgabe wird gleich angezeigt.
4. Je Loch Schläge und Putts eintragen (Nettopunkte nur, wenn sie nicht automatisch berechnet
   werden) und bei Par 3 den NTP-Sieger wählen.
5. Das **Dashboard** zeigt Jahres- und Final-Four-Stand sowie die Ergebnisse jeder Runde.

## Entwicklung

Ohne Docker, im Ordner `~/Projekte/golfapp` (Python 3 erforderlich):

```bash
cd ~/Projekte/golfapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python wsgi.py          # Entwicklungsserver auf http://localhost:8000
pytest                  # Tests
```

Die Datenbank liegt dann unter `instance/golf.sqlite` (von Git ignoriert).

Aufbau: Flask (`golfapp/`), Auswertungslogik in `golfapp/scoring.py`, Spielvorgabe und
Nettopunkte in `golfapp/handicap.py`, Schema in `golfapp/schema.sql`. Neue Spalten werden beim
Start automatisch in bestehende Datenbanken übernommen (`MIGRATIONS` in `golfapp/db.py`).

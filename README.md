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

1. Unter **Spieler** die Spieler anlegen.
2. Optional unter **Plätze** Plätze mit Par-Werten speichern.
3. **Neue Runde**: Datum, Rundentyp (Normal / Final Four), Platz, Spieler wählen.
4. Je Loch Schläge, Putts und Nettopunkte eintragen und bei Par 3 den NTP-Sieger wählen.
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

Aufbau: Flask (`golfapp/`), Auswertungslogik in `golfapp/scoring.py`, Schema in `golfapp/schema.sql`.

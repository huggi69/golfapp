# ⛳ Whisky Torphy

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
  Ob sie zusätzlich zur Jahreswertung zählen, wird je Saison im Dashboard eingestellt.
  Für Jahre ohne eigene Einstellung gilt `FINAL_FOUR_IN_ANNUAL` (Standard: zählen nicht).

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
| `FINAL_FOUR_IN_ANNUAL` | `false`               | Standard für Saisons ohne eigene Einstellung: Final-Four-Runden zusätzlich in der Jahreswertung zählen |
| `SECRET_KEY`           | automatisch           | Schlüssel für die Login-Cookies. Ohne Angabe wird er einmalig erzeugt und als `secret_key` neben der Datenbank gespeichert. |
| `SESSION_COOKIE_SECURE`| `false`               | Auf `true` setzen, wenn die App nur per HTTPS erreichbar ist           |
| `TRUST_PROXY`          | `false`               | `true` hinter einem Reverse Proxy (Traefik): Protokoll und Client-IP aus `X-Forwarded-*` übernehmen. Nur setzen, wenn ein Proxy davor sitzt. |

### Login

Ohne Anmeldung ist nichts erreichbar. Jeder Spieler meldet sich mit seinem Namen und Passwort
an und bleibt auf dem Gerät 180 Tage angemeldet. Alle angemeldeten Spieler haben die gleichen Rechte.

* **Ersteinrichtung:** Solange noch niemand ein Passwort hat, legt man auf der Login-Seite den
  ersten Zugang an (Name + Passwort; ein vorhandener Spieler gleichen Namens wird übernommen).
* **Mitspieler:** Unter **Spieler** bekommt jeder Spieler ein Passwort (mind. 6 Zeichen).
  Das eigene Passwort ändert man über den Namen oben rechts.
* **Passwort vergessen:**
  ```bash
  docker compose exec golfapp python -m golfapp.set_password "Name"
  ```

### Backup

```bash
# auf dem Server zusätzlich -f docker-compose.prod.yml angeben
docker compose exec golfapp python -c "import sqlite3; s=sqlite3.connect('/data/golf.sqlite'); s.backup(sqlite3.connect('/data/backup.sqlite'))"
docker compose cp golfapp:/data/backup.sqlite ./backup-$(date +%F).sqlite
```

### Online-Betrieb hinter Traefik

`docker-compose.prod.yml` hängt die App in das Docker-Netzwerk von Traefik (Standard `web`),
veröffentlicht keinen Port, holt per Let's Encrypt ein Zertifikat und leitet HTTP auf HTTPS um.

Voraussetzung: Der DNS-Eintrag (A/AAAA) der Domain zeigt auf den Server.

**Erstinstallation** (Beispiel mit `/opt/docker/golfapp`):

```bash
cd /opt/docker
git clone https://github.com/huggi69/golfapp.git   # privates Repo: Deploy-Key oder Token nötig
cd golfapp
cp .env.example .env
# Namen der Entrypoints und des Certresolvers in der Traefik-Konfiguration nachsehen
# und in .env eintragen, falls sie nicht websecure / web / letsencrypt heißen:
grep -n -A3 -E "entryPoints|certificatesResolvers" /opt/docker/traefik/traefik.y*ml
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f      # Start prüfen, Strg+C beendet die Anzeige
```

Danach `https://<DOMAIN>` aufrufen und den ersten Zugang anlegen. Wer die alte Historie
übernehmen will, importiert sie **vorher** (siehe unten) – dann legt man beim ersten Login
direkt den Zugang für den importierten Spieler an.

**Update:**

```bash
cd /opt/docker/golfapp
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Datenbank und `secret_key` liegen im Volume `golfapp_golf-data` und bleiben bei Updates erhalten.

### Historie aus der alten App importieren

Der MySQL-Dump der alten App (Tabellen `golf_games`, `golf_holes`, `golf_players`,
`golf_season`, z.B. aus TablePlus exportiert) lässt sich direkt importieren:

```bash
# Mit Docker (auf dem Server zusätzlich -f docker-compose.prod.yml angeben)
docker compose cp golf.sql golfapp:/tmp/golf.sql
docker compose exec golfapp python -m golfapp.legacy_import /tmp/golf.sql
docker compose exec -u root golfapp rm -f /tmp/golf.sql   # Dump danach wieder löschen

# Ohne Docker
python -m golfapp.legacy_import golf.sql
```

* Spieler werden über den Namen zugeordnet bzw. angelegt.
* Final Four, „FF zählt zur Jahreswertung“ und die Lochspiel-Wertung („lochberechnung“:
  `score` = Brutto, sonst Netto) werden je Saison übernommen.
* Die alte App kennt kein Par: Löcher mit gewonnenem Pin werden Par 3, alle anderen bleiben
  „unbekannt“ und lassen sich in der Runde nachtragen. Löcher mit 0 Schlägen gelten als nicht gespielt.
* Bereits importierte Spiele (Notiz „Import alte App, Spiel …“) werden übersprungen –
  der Import kann also gefahrlos erneut laufen.

### Plätze übertragen

Unter **Plätze → Übertragen** lassen sich alle Plätze samt Abschlägen als JSON-Datei exportieren
und in einer anderen Installation wieder importieren (z.B. vom eigenen Rechner auf den Server).
Gleichnamige Plätze werden dabei aktualisiert, nicht doppelt angelegt.

## Bedienung

1. Beim ersten Aufruf den eigenen Zugang anlegen, dann unter **Spieler** die Mitspieler mit
   Handicap-Index und Passwort anlegen.
2. Unter **Plätze** Plätze mit Par, Handicap-Reihenfolge und den Abschlägen
   (Course Rating, Slope) speichern.
3. **Neue Runde**: Datum, Rundentyp (Normal / Final Four), Platz, Spieler, Handicap-Index und
   Abschlag wählen – die Spielvorgabe wird gleich angezeigt.
4. Nach dem Anlegen öffnet sich die **Erfassung Loch für Loch** – gedacht fürs Handy während der
   Runde: je Loch und Spieler Schläge und Putts per Tipp (Schnellwahl Birdie/Par/Bogey … oder
   −/+), bei Par 3 den NTP-Sieger wählen. Nettopunkte und Zwischenstand (inkl. Lochspiel)
   rechnen live mit. Jede Eingabe wird sofort gespeichert; ohne Netz bleibt sie auf dem Handy und
   wird automatisch nachgesendet. Die **Tabellenansicht** bleibt für Korrekturen am Rechner.
   **Spracheingabe:** Auf „🎤 Ansagen“ tippen und z.B. „Franky 5 1, Huggi 4 2“ sagen
   (Name, Schläge, Putts; ohne automatische Berechnung optional als dritte Zahl die Nettopunkte).
   Nutzt die Spracherkennung des Browsers (Chrome/Android, Safari/iOS) und braucht HTTPS sowie Netz.
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

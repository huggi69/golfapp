# CLAUDE.md

## Arbeitsweise

- **Sprache:** Die Konversation wird immer auf Deutsch geführt.
- **Pull Requests:** Jeden geöffneten PR immer beobachten (PR-Aktivität abonnieren) und auf Review-Kommentare sowie CI-Fehler reagieren, bis er gemergt oder geschlossen ist.
- **PRs selbst mergen:** Eigene PRs selbst mergen, sobald die Tests (`pytest`) lokal grün sind, der PR konfliktfrei ist und keine offenen Review-Kommentare oder fehlschlagenden Checks vorliegen. Danach PR-Beobachtung und geplante Check-ins beenden.
- **Befehle anzeigen:** Ausgeführte Befehle (Shell, git usw.) immer in der Antwort anzeigen.

## Projekt

Whisky Torphy – Flask-App mit SQLite für einen Jahreswettbewerb inkl. Final Four. Details siehe `README.md`.

- Tests: `pytest`
- Entwicklungsserver: `python wsgi.py`
- Container: `docker compose up -d --build`

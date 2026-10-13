# CLAUDE.md

## Arbeitsweise

- **Sprache:** Die Konversation wird immer auf Deutsch geführt.
- **Pull Requests:** Jeden geöffneten PR immer beobachten (PR-Aktivität abonnieren) und auf Review-Kommentare sowie CI-Fehler reagieren, bis er gemergt oder geschlossen ist.
- **Befehle anzeigen:** Ausgeführte Befehle (Shell, git usw.) immer in der Antwort anzeigen.

## Projekt

Whisky Trophy – Flask-App mit SQLite für einen Jahreswettbewerb inkl. Final Four. Details siehe `README.md`.

- Tests: `pytest`
- Entwicklungsserver: `python wsgi.py`
- Container: `docker compose up -d --build`
